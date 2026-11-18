"""BragaBot: incorporado de braga_bot/braga.py e ssl_ca.py."""
import os
import re
import tempfile
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path

import certifi
import requests
from selenium import webdriver
from selenium.common.exceptions import (
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

ENROL_ID_MAX = int(os.environ.get("ENROL_ID_MAX", "100"))
USERS_DIR = Path(__file__).resolve().parent / "users"
LOG_FILE = USERS_DIR / "execucao.log"  # progresso da execução atual (página lê ao vivo)


def log(msg):
    """Escreve no execucao.log na hora (a página lê ao vivo) e no terminal."""
    print(msg)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{msg}\n")


def run(users, cancelar=None):
    """Roda o bot para cada conta e devolve (status, {cpf: [(id, nome, url), ...]})."""
    USERS_DIR.mkdir(exist_ok=True)
    LOG_FILE.write_text("", encoding="utf-8")
    log(f"Execução iniciada em {datetime.now():%d/%m/%Y %H:%M:%S}")
    bot = BragaBot(cancelar)
    status = "concluida"
    resultados = {}
    try:
        bot.wait_for_site()
        bot.setup_driver()
        for cpf, senha in users.items():
            bot.checar_cancelamento()
            try:
                incompletos = bot.run_for_user(cpf, senha)
                resultados[cpf] = incompletos
                linhas = [f"  • [{cid}] {nome}: {url}" for cid, nome, url in incompletos]
                log("📋 Cursos incompletos:\n" + ("\n".join(linhas) or "  Nenhum."))
            except Cancelado:
                raise
            except Exception as e:
                traceback.print_exc()
                log(f"  ❌ Erro: {e}")
    except Cancelado:
        status = "cancelada"
        log("\n⛔ Execução cancelada")
    except Exception as e:
        status = "falhou"
        traceback.print_exc()
        log(f"\n❌ Erro geral: {e}")
    finally:
        bot.quit()
        log(f"\nExecução finalizada em {datetime.now():%d/%m/%Y %H:%M:%S}")
    return status, resultados


# O servidor não envia o certificado intermediário da GlobalSign,
# então ele é somado ao bundle padrão do certifi.
INTERMEDIATE_CERT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "ssl",
    "globalsign_atlas_r3_ov_2026q1.pem",
)


def build_ca_bundle():
    bundle = tempfile.NamedTemporaryFile(
        mode="w", suffix=".pem", prefix="braga_ca_", delete=False
    )
    with bundle, open(certifi.where()) as base, open(INTERMEDIATE_CERT) as extra:
        bundle.write(base.read())
        bundle.write("\n")
        bundle.write(extra.read())
    return bundle.name


class Cancelado(Exception):
    pass


class BragaBot:
    LOGIN_URL = "https://ead.policiapenal.sp.gov.br/login/index.php"
    COURSE_BASE_URL = "https://ead.policiapenal.sp.gov.br/course/view.php?id={}"
    TIMEOUT = 15

    def __init__(self, cancelar=None):
        self.driver = None
        self.wait = None
        self.cancelar = cancelar or threading.Event()
        self.ca_bundle = build_ca_bundle()

    def setup_driver(self):
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        chrome_bin = os.environ.get("CHROME_BIN")
        if chrome_bin:
            options.binary_location = chrome_bin
        # Selenium Manager não suporta linux/aarch64: usar o chromedriver do sistema
        chromedriver = os.environ.get("CHROMEDRIVER_PATH")
        service = Service(executable_path=chromedriver) if chromedriver else Service()
        self.driver = webdriver.Chrome(options=options, service=service)
        self.wait = WebDriverWait(self.driver, self.TIMEOUT)
        log("✅ Driver configurado")

    def quit(self):
        if self.driver:
            self.driver.quit()
            log("🧹 Driver fechado")

    def checar_cancelamento(self):
        if self.cancelar.is_set():
            raise Cancelado()

    def wait_for_site(self):
        while True:
            self.checar_cancelamento()
            try:
                r = requests.get(self.LOGIN_URL, timeout=5, verify=self.ca_bundle)
                if r.status_code == 200:
                    break
            except requests.RequestException:
                pass
            log("⏳ Site não acessível. Aguardando 10s...")
            self.cancelar.wait(10)
        log("✅ Site acessível")

    def _page_ready(self):
        self.wait.until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )

    def _fill_field(self, selector, text):
        # O Moodle re-renderiza #password de forma assíncrona (módulo JS
        # core/togglesensitive), então o elemento pode ficar stale ou perder
        # o valor digitado. Preenche com verificação e tenta de novo se preciso.
        for _ in range(10):
            field = self.wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
            )
            try:
                field.clear()
                field.send_keys(text)
            except StaleElementReferenceException:
                continue
            time.sleep(0.5)
            try:
                current = self.driver.execute_script(
                    "return document.querySelector(arguments[0]).value", selector
                )
            except Exception:
                continue
            if current == text:
                return
        raise RuntimeError(
            f"Não foi possível preencher o campo {selector} de forma estável"
        )

    def login(self, username, password):
        self.driver.delete_all_cookies()
        self.driver.get(self.LOGIN_URL)
        self._page_ready()
        self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "#username")))
        self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "#password")))
        time.sleep(1)  # dá tempo dos módulos AMD (ex: togglesensitive) terminarem

        log(f"🔐 Login: {username}")
        self._fill_field("#username", username)
        self._fill_field("#password", password)
        self.driver.find_element(By.CSS_SELECTOR, "#loginbtn").click()
        try:
            self.wait.until(EC.url_changes(self.LOGIN_URL))
        except TimeoutException:
            raise RuntimeError(
                f"Login falhou para {username}: a página não saiu do login "
                f"após o clique (timeout de {self.TIMEOUT}s)"
            )

        if "login" in self.driver.current_url:
            erro_site = ""
            try:
                erro_site = self.driver.find_element(
                    By.CSS_SELECTOR, "#loginerrormessage, .loginerrors"
                ).text.strip()
            except NoSuchElementException:
                pass
            detalhe = f" | Mensagem do site: {erro_site}" if erro_site else ""
            raise RuntimeError(f"Login falhou para {username}{detalhe}")
        log("✅ Login realizado")

    def scan_courses(self):
        log("🔍 Buscando cursos matriculados em /my/courses.php...")
        self.driver.get("https://ead.policiapenal.sp.gov.br/my/courses.php")
        self._page_ready()
        time.sleep(3)

        ids = list(
            set(re.findall(r"course/view\.php\?id=(\d+)", self.driver.page_source))
        )
        log(f"  {len(ids)} curso(s) encontrado(s): {ids}")

        incompletos = []
        for course_id in ids:
            self.checar_cancelamento()
            url = self.COURSE_BASE_URL.format(course_id)
            self.driver.get(url)
            self._page_ready()
            time.sleep(1)
            html = self.driver.page_source

            nome_match = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.DOTALL)
            nome = (
                re.sub(r"<[^>]+>", "", nome_match.group(1)).strip()
                if nome_match
                else f"Curso {course_id}"
            )

            m_done = re.search(r'data-numcomplete="(\d+)"', html)
            m_total = re.search(r'data-numoutof="(\d+)"', html)
            if m_done and m_total:
                done = int(m_done.group(1))
                total = int(m_total.group(1))
                pct = int(done / total * 100) if total else 0
                if total > 0 and done == total:
                    log(f"  ✅ [{course_id}] {nome} — {done}/{total} (100%)")
                    continue
                log(f"  📝 [{course_id}] {nome} — {done}/{total} ({pct}%)")
            else:
                log(f"  📝 [{course_id}] {nome} — sem progresso registrado")

            incompletos.append((course_id, nome, url))

        log(f"  {len(incompletos)} curso(s) incompleto(s)")
        return incompletos

    def inscrever_em_curso(self, course_ids):
        for course_id in course_ids:
            self.checar_cancelamento()
            log(f"✏️ Inscrevendo no curso {course_id}...")
            self.driver.get(
                f"https://ead.policiapenal.sp.gov.br/enrol/index.php?id={course_id}"
            )
            self._page_ready()
            time.sleep(2)
            try:
                submit_btn = self.driver.find_element(
                    By.CSS_SELECTOR, "#id_submitbutton"
                )
                if submit_btn.get_attribute("value") == "Inscreva-me":
                    submit_btn.click()
                    self._page_ready()
                    log(f"✅ [{course_id}] Inscrição realizada")
            except NoSuchElementException:
                pass
            except Exception as e:
                log(f"❌ [{course_id}] Falha ao inscrever: {e}")

    def run_for_user(self, username, password):
        """Faz login, inscreve nos cursos e devolve os incompletos."""
        log(f"\n{'=' * 50}\n👤 Processando: {username}\n{'=' * 50}")
        self.login(username, password)
        self.inscrever_em_curso(range(1, ENROL_ID_MAX + 1))
        return self.scan_courses()
