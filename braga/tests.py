import tempfile
import threading
from pathlib import Path
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase

from . import bot
from .models import Conta


class BragaBase(TestCase):
    databases = {"default", "braga"}

    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        for nome, valor in [("USERS_DIR", tmp), ("LOG_FILE", tmp / "execucao.log")]:
            p = mock.patch.object(bot, nome, valor)
            p.start()
            self.addCleanup(p.stop)
        # a view guarda a thread em variável global: zera entre testes
        for nome in ("_execucao",):
            p = mock.patch(f"braga.views.{nome}", None)
            p.start()
            self.addCleanup(p.stop)
        User.objects.create_user("fer", password="senha123")
        self.client.login(username="fer", password="senha123")


class ContasTest(BragaBase):
    def test_adicionar_troca_e_remover(self):
        self.client.post("/braga/adicionar/", {"cpf": "123.456.789-00", "senha": "a:b"})
        self.client.post("/braga/adicionar/", {"cpf": "111", "senha": "x"})
        self.client.post("/braga/adicionar/", {"cpf": "111", "senha": "y"})
        self.assertEqual(
            dict(Conta.objects.values_list("cpf", "senha")),
            {"123.456.789-00": "a:b", "111": "y"},
        )
        self.client.post("/braga/remover/", {"cpf": "111"})
        self.assertEqual(
            list(Conta.objects.values_list("cpf", flat=True)), ["123.456.789-00"]
        )

    def test_conta_fica_no_banco_do_braga(self):
        Conta.objects.create(cpf="111", senha="x")
        self.assertEqual(Conta.objects.db, "braga")
        self.assertEqual(Conta.objects.using("braga").count(), 1)

    def test_entrada_invalida_nao_grava(self):
        r = self.client.post("/braga/adicionar/", {"cpf": "1\n2:3", "senha": ""})
        self.assertContains(r, "getElementById('contas').showModal()</script>")
        self.assertContains(r, "Use só números")
        self.assertFalse(Conta.objects.exists())

    def test_pagina_nao_mostra_senha(self):
        Conta.objects.create(cpf="111", senha="segredo")
        r = self.client.get("/braga/")
        self.assertContains(r, "111")  # só dentro do <dialog>, fechado por padrão
        self.assertNotContains(r, "segredo")
        self.assertNotContains(r, "showModal()</script>")


class RodarTest(BragaBase):
    @mock.patch("braga.views.threading.Thread")
    def test_rodar_inicia_thread(self, Thread):
        Conta.objects.create(cpf="111", senha="x")
        self.assertEqual(
            self.client.post("/braga/rodar/")["Location"], "/braga/#sec-execucao"
        )
        kwargs = Thread.call_args.kwargs
        self.assertEqual(kwargs["args"][0], {"111": "x"})
        from . import views

        self.assertIs(kwargs["target"], views._executar)
        Thread.return_value.start.assert_called_once()

    @mock.patch("braga.views.threading.Thread")
    def test_sem_contas_nao_roda(self, Thread):
        self.client.post("/braga/rodar/")
        Thread.assert_not_called()

    @mock.patch.object(bot, "BragaBot")
    def test_run_grava_log(self, Bot):
        Bot.return_value.run_for_user.side_effect = [
            [("7", "Curso X", "http://x/7")],
            RuntimeError("Login falhou"),
        ]
        with mock.patch("traceback.print_exc"):
            status, resultados = bot.run({"111": "a", "222": "b"})
        self.assertEqual(resultados, {"111": [("7", "Curso X", "http://x/7")]})
        log = bot.LOG_FILE.read_text()
        self.assertIn("[7] Curso X: http://x/7", log)
        self.assertIn("❌ Erro: Login falhou", log)
        self.assertIn("Execução finalizada", log)
        self.assertContains(self.client.get("/braga/status/"), "Curso X")
        Bot.return_value.quit.assert_called_once()
        self.assertContains(self.client.get("/braga/"), "Curso X")

    @mock.patch.object(bot, "BragaBot")
    def test_run_cancelado_nao_processa_contas(self, Bot):
        Bot.return_value.checar_cancelamento.side_effect = bot.Cancelado
        bot.run({"111": "a"})
        Bot.return_value.run_for_user.assert_not_called()
        Bot.return_value.quit.assert_called_once()
        self.assertIn("⛔ Execução cancelada", bot.LOG_FILE.read_text())

    def test_inscricao_para_quando_cancela(self):
        cancelar = threading.Event()
        b = bot.BragaBot(cancelar)
        b.driver = mock.Mock()
        b.wait = mock.Mock()
        cancelar.set()
        with self.assertRaises(bot.Cancelado):
            b.inscrever_em_curso(range(1, 101))
        b.driver.get.assert_not_called()

    def test_cancelar_view(self):
        from . import views

        cancelar, liberar = threading.Event(), threading.Event()
        thread = threading.Thread(target=liberar.wait, daemon=True)
        with (
            mock.patch.object(views, "_execucao", thread),
            mock.patch.object(views, "_cancelar", cancelar),
        ):
            thread.start()
            self.assertContains(self.client.get("/braga/"), "Cancelar execução")
            self.client.post("/braga/cancelar/")
            self.assertTrue(cancelar.is_set())
            self.assertContains(self.client.get("/braga/"), "Cancelando")
            liberar.set()
            thread.join(1)

    def test_log_escreve_na_hora(self):
        bot.log("passo 1")
        self.assertEqual(
            self.client.get("/braga/status/").json(),
            {"log": "passo 1\n", "rodando": False, "cancelando": False},
        )

    def test_status_exige_login(self):
        self.client.logout()
        self.assertEqual(self.client.get("/braga/status/").status_code, 302)


class LogTest(BragaBase):
    def test_log_fechado_quando_parado(self):
        bot.log("passo 1")
        r = self.client.get("/braga/")
        self.assertContains(r, '<details class="log-box" id="log-box">')
        self.assertContains(r, "Log da última execução")

    def test_sem_log_nao_mostra_bloco(self):
        self.assertContains(self.client.get("/braga/"), 'id="log-box" hidden')


class HistoricoTest(BragaBase):
    @mock.patch.object(bot, "run")
    def test_execucao_vai_pro_historico(self, run):
        from . import views
        from .models import Execucao

        run.return_value = (
            "cancelada",
            {"111": [("9", "Curso Y", "http://x/9")], "222": []},
        )
        views._executar({"111": "a", "222": "b"}, threading.Event())
        ex = Execucao.objects.get()
        self.assertEqual(ex.status, "cancelada")
        self.assertIsNotNone(ex.fim)
        self.assertEqual(
            list(ex.incompletos.values_list("cpf", "curso_id", "nome", "url")),
            [("111", "9", "Curso Y", "http://x/9")],
        )
        r = self.client.get("/braga/")
        self.assertContains(r, 'href="#sec-historico"')
        self.assertContains(r, "status-cancelada")
        self.assertContains(r, "[9] Curso Y")
        self.assertContains(r, "111 — 1 curso(s) para completar")

    @mock.patch.object(bot, "run", side_effect=RuntimeError("quebrou"))
    def test_erro_inesperado_fica_como_falhou(self, run):
        from . import views
        from .models import Execucao

        with self.assertRaises(RuntimeError):
            views._executar({"111": "a"}, threading.Event())
        self.assertEqual(Execucao.objects.get().status, "falhou")

    def test_execucao_orfa_aparece_interrompida(self):
        from .models import Execucao

        Execucao.objects.create()  # ficou "rodando" porque o servidor reiniciou no meio
        self.assertContains(self.client.get("/braga/"), "Interrompida")

    @mock.patch.object(bot, "BragaBot")
    def test_run_devolve_status(self, Bot):
        Bot.return_value.run_for_user.return_value = []
        self.assertEqual(bot.run({"111": "a"}), ("concluida", {"111": []}))
        Bot.return_value.checar_cancelamento.side_effect = bot.Cancelado
        self.assertEqual(bot.run({"111": "a"}), ("cancelada", {}))


class NomeTest(BragaBase):
    def test_nome_opcional_e_mantido_ao_trocar_senha(self):
        self.client.post("/braga/adicionar/", {"cpf": "111", "senha": "x"})
        self.assertEqual(Conta.objects.get().nome, "")
        self.client.post(
            "/braga/adicionar/", {"nome": "Fulano", "cpf": "111", "senha": "y"}
        )
        self.client.post("/braga/adicionar/", {"nome": "", "cpf": "111", "senha": "z"})
        conta = Conta.objects.get()
        self.assertEqual((conta.nome, conta.senha), ("Fulano", "z"))
        self.assertContains(self.client.get("/braga/"), "<strong>Fulano</strong> · 111")


class EditarContaTest(BragaBase):
    def test_trocar_nome_sem_mexer_na_senha(self):
        Conta.objects.create(cpf="111", senha="certa")
        self.client.post(
            "/braga/adicionar/", {"nome": "Fulano", "cpf": "111", "senha": ""}
        )
        conta = Conta.objects.get()
        self.assertEqual((conta.nome, conta.senha), ("Fulano", "certa"))

    def test_cpf_novo_exige_senha(self):
        r = self.client.post(
            "/braga/adicionar/", {"nome": "Fulano", "cpf": "222", "senha": ""}
        )
        self.assertContains(r, "Informe a senha (CPF novo).")
        self.assertFalse(Conta.objects.exists())
