"""Cronjob News: incorporado de news_bot/news_bot.py.

Do original mudou só o envio (agora main.emails.enviar_email) e os destinatários (banco).
"""
import html
import json
import re
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote_plus, urljoin, urlparse

import requests

from main.emails import enviar_email
from main.gemini import GEMINI_MODEL, ask_gemini

# o "lite" não devolve as fontes, e sem elas não há link nem imagem
PASTA = Path(__file__).parent / "imgs"  # capa.png / rodape.png ficam aqui; o que faltar é pulado
DIAS = ["SEGUNDA-FEIRA", "TERÇA-FEIRA", "QUARTA-FEIRA", "QUINTA-FEIRA", "SEXTA-FEIRA", "SÁBADO", "DOMINGO"]
MESES = ["JANEIRO", "FEVEREIRO", "MARÇO", "ABRIL", "MAIO", "JUNHO",
         "JULHO", "AGOSTO", "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO"]
# formato comum a todos os bots: cada bot só explica no prompt o que vai em cada campo
FORMATO_JSON = (
    "Responda somente com JSON, sem comentários antes ou depois, neste formato: "
    '{"abertura": "...", "itens": [{"rotulo": "...", "titulo": "...", "destaque": "...", '
    '"texto": ["parágrafo", "..."], "fonte": "nome do site", "link": "https://..."}], "despedida": "..."}. '
    "Em link, só o endereço exato de uma página que apareceu na busca; se não tiver, deixe vazio. "
    "Destaque números importantes com **asteriscos duplos**."
)


class _Capa(HTMLParser):
    """Lê as tags og:title, og:description e og:image (a prévia que aparece no WhatsApp)."""

    def __init__(self):
        super().__init__()
        self.og = {}

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        nome = a.get("property") or a.get("name")
        if tag == "meta" and nome in ("og:title", "og:description", "og:image") and nome not in self.og:
            self.og[nome] = a.get("content") or ""


def abrir_materia(url: str) -> tuple[str, str, str | None]:
    """Segue o redirecionamento do Google e devolve (link real, título + descrição, imagem de capa)."""
    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        # 1º redirecionamento = link real; lojas que bloqueiam robô (403, captcha) mandam para outra página depois
        link = r.history[0].headers.get("location", r.url) if r.history else r.url
        leitor = _Capa()
        leitor.feed(r.text if r.ok else "")
        og = leitor.og
        imagem = og.get("og:image")
        # o endereço entra na comparação: o nome do produto/matéria costuma estar nele, mesmo se a página bloquear
        descricao = f"{og.get('og:title', '')} {og.get('og:description', '')} {link}"
        return link, descricao, imagem and urljoin(r.url, imagem)
    except requests.RequestException:
        return url, "", None


def e_materia(url: str) -> bool:
    """Endereço de matéria tem um título no fim (".../banco-digital-que-quebrou-no-paraguai.ghtml");
    home, seção e vídeo ("/bom-dia-brasil/", "/ultimas-noticias/") não."""
    # shortcut: regra pelo formato do endereço; site cujo link de matéria é só um número fica de fora
    return urlparse(url).path.rstrip("/").rsplit("/", 1)[-1].count("-") >= 4


def pagina_existe(url: str) -> bool:
    """O link que o Gemini escreve às vezes é inventado (404)."""
    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        return r.ok and e_materia(r.url)
    except requests.RequestException:
        return False


def _palavras(texto: str) -> set[str]:
    return set(re.findall(r"\w{4,}", texto.lower()))


def materia_da_linha(linha: str, materias: list[tuple[str, str, str | None]]):
    """Matéria que mais combina com a linha; None se nenhuma bater de verdade.

    Palavras presentes em mais da metade das fontes ("placa", "radeon") são ignoradas; das restantes
    precisa bater pelo menos 2, e as mais raras (marca, modelo, nome próprio) valem mais.
    """
    textos = [_palavras(m[1]) for m in materias]
    frequencia = {}
    for t in textos:
        for w in t:
            frequencia[w] = frequencia.get(w, 0) + 1
    # palavras em mais da metade das fontes não distinguem nada
    palavras = {w for w in _palavras(linha) if frequencia.get(w, 0) <= max(1, len(materias) / 2)}

    def pontos(t):
        comuns = palavras & t
        return sum(1 / frequencia[w] for w in comuns) if len(comuns) >= 2 else 0

    notas = [pontos(t) for t in textos]
    # shortcut: casamento por palavras; se ainda errar muito, pedir ao Gemini um JSON com o índice da fonte
    melhor = max(range(len(materias)), key=notas.__getitem__, default=None)
    return materias[melhor] if melhor is not None and notas[melhor] > 0 else None


def ler_json(texto: str) -> dict:
    # com google_search a API não aceita resposta só-JSON, então às vezes vem embrulhado em ```json
    return json.loads(texto[texto.find("{"): texto.rfind("}") + 1])


def _rico(texto: str) -> str:
    """Escapa o HTML e transforma **x** em negrito."""
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", html.escape(texto))


ROTULO = "font-size:12px;letter-spacing:2px;color:#888;margin:36px 0 6px;font-weight:bold"
TITULO = "font-size:24px;line-height:1.25;margin:0 0 16px;padding-bottom:10px;border-bottom:3px solid #111"
FOTO = "width:100%;height:auto;display:block;margin:0 0 16px;border-radius:4px"


def montar_html(edicao: dict, fontes: list[str], pngs: dict) -> str:
    """Página no estilo newsletter: data, abertura, um bloco por item e rodapé. pngs = {cid: bytes}."""
    materias = [abrir_materia(u) for u in fontes]
    hoje = datetime.now()
    e = html.escape
    p = []
    if "capa" in pngs:
        p.append(f'<img src="cid:capa" alt="" width="600" style="{FOTO};border-radius:0">')
    p.append(f'<p style="font-size:12px;letter-spacing:2px;color:#888;margin:16px 0 0">'
             f"{DIAS[hoje.weekday()]}, {hoje.day} DE {MESES[hoje.month - 1]} DE {hoje.year}</p>")
    p.append(f'<h1 style="font-size:36px;margin:4px 0 16px">{hoje:%d/%m/%Y}</h1>')
    if edicao.get("abertura"):
        p.append(f'<p style="font-style:italic;color:#444">{_rico(edicao["abertura"])}</p>')
    for item in edicao.get("itens", []):
        texto = item.get("texto") or []
        escrito = item.get("link") or ""
        resumo = f"{item.get('titulo', '')} {item.get('destaque', '')} {' '.join(texto)}"
        # 1º o link que o Gemini escreveu, se a página existe e fala do mesmo assunto (ele às vezes troca os links)
        # 2º a fonte da busca que casar; 3º busca no Google
        escrita = abrir_materia(escrito) if escrito.startswith("http") and pagina_existe(escrito) else None
        materia = (escrita and materia_da_linha(resumo, [escrita])) or materia_da_linha(resumo, materias)
        link, _, imagem = materia if materia and e_materia(materia[0]) else (None, None, None)
        # shortcut: a busca usa o destaque reescrito pelo Gemini; se trouxer matéria errada, pedir a manchete original no JSON
        link = link or "https://www.google.com/search?q=" + quote_plus(f"{item.get('destaque', '')} {item.get('fonte', '')}")
        p.append(f'<p style="{ROTULO}">{e(item.get("rotulo", "").upper())}</p>')
        p.append(f'<h2 style="{TITULO}">{e(item.get("titulo", ""))}</h2>')
        if imagem:
            p.append(f'<img src="{e(imagem)}" alt="" width="600" style="{FOTO}">')
        if item.get("destaque"):
            p.append(f'<p><b>{_rico(item["destaque"])}</b></p>')
        p += [f"<p>{_rico(t)}</p>" for t in texto]
        fonte = e(item.get("fonte", ""))
        p.append(f'<p><a href="{e(link)}" style="color:#111;font-weight:bold">Leia no {fonte or "site"} →</a></p>'
                 if link else f'<p style="color:#888">Fonte: {fonte}</p>' if fonte else "")
    if edicao.get("despedida"):
        p.append(f'<p style="margin-top:40px">{_rico(edicao["despedida"])}</p>')
    if "rodape" in pngs:
        p.append(f'<img src="cid:rodape" alt="" width="600" style="{FOTO};border-radius:0;margin-top:24px">')
    return ('<html><body style="margin:0;background:#f2f2f2">'
            '<div style="max-width:600px;margin:0 auto;background:#fff;padding:24px;'
            'font-family:Helvetica,Arial,sans-serif;font-size:16px;line-height:1.6;color:#111">'
            + "\n".join(p) + "</div></body></html>")


def montar_texto(edicao: dict) -> str:
    """Versão texto para quem não abre HTML."""
    linhas = [edicao.get("abertura", "")]
    for i in edicao.get("itens", []):
        linhas += ["", f"{i.get('rotulo', '')} | {i.get('titulo', '')}", i.get("destaque", ""),
                   *(i.get("texto") or []), f"Fonte: {i.get('fonte', '')}"]
    linhas += ["", edicao.get("despedida", "")]
    return "\n".join(linhas).replace("**", "")


# {hoje} vira a data do dia no envio. Editável na página (aba Prompt); este é o padrão.
PROMPT_PADRAO = (
    "Hoje é {hoje} (a data está correta; não a questione). Use a busca para encontrar as notícias mais importantes publicadas hoje "
    "em grandes portais de notícias do Brasil (ex.: G1, Folha, Estadão, UOL, CNN Brasil). "
    "Escolha uma notícia por rótulo, nesta ordem: MUNDO, BRASIL, NEGÓCIOS, TECNOLOGIA, "
    "SEGURANÇA DE DADOS, ECONOMIA. Em cada item: titulo = curto e criativo, terminado em um emoji; "
    "destaque = uma frase de abertura que fisgue o leitor; texto = 2 ou 3 parágrafos curtos "
    "explicando o que aconteceu e por que importa; fonte = nome do site (ex.: G1, Folha); link = endereço da matéria. "
    "Use apenas notícias encontradas na busca. abertura = uma reflexão curta do dia; "
    "despedida = curta, assinada pelo 'Cronjob News'. Tom leve e divertido, de newsletter matinal."
)


def noticias_prompt(modelo: str | None = None) -> str:
    # replace e não format: chaves digitadas no prompt editado não quebram nada
    return (modelo or PROMPT_PADRAO).replace("{hoje}", datetime.now().strftime("%d/%m/%Y"))


def imagens(capa: str = "capa.png", rodape: str = "rodape.png") -> dict:
    return {cid: (PASTA / nome).read_bytes() for cid, nome in {"capa": capa, "rodape": rodape}.items()
            if (PASTA / nome).exists()}


def enviar_noticias(para: list[str], prompt: str | None = None, modelo: str | None = None) -> None:
    """Pergunta ao Gemini (em JSON), monta a newsletter e manda o e-mail (era o enviar() do original)."""
    print("📰 Cronjob News: buscando notícias...")
    for tentativa in range(3):  # a busca às vezes volta sem fontes, e sem elas a notícia fica sem link
        resposta, fontes = ask_gemini(f"{noticias_prompt(prompt)} {FORMATO_JSON}", modelo or GEMINI_MODEL)
        if fontes or tentativa == 2:
            break
        print(f"📰 Sem fontes, tentativa {tentativa + 2}...")
    edicao = ler_json(resposta)
    print("📰 Montando e-mail...")
    pngs = imagens()
    enviar_email(f"🤖 Cronjob News {datetime.now():%d/%m/%Y}", montar_texto(edicao),
                 montar_html(edicao, fontes, pngs), para, pngs)
    print(f"📰 E-mail enviado para {len(para)} destinatário(s)")
