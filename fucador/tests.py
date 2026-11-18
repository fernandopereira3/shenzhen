import json
from unittest import mock

from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase

from main import agendador

from . import ofertas, views
from .models import Configuracao, ContatoWhatsApp, Destinatario, Envio, Produto

EDICAO = {
    "abertura": "Olá!",
    "itens": [
        {
            "rotulo": "Kabum",
            "titulo": "Robô X 🤖",
            "destaque": "**R$ 999,90**",
            "texto": ["Boa oferta."],
            "fonte": "Kabum",
        }
    ],
    "despedida": "Fuçador",
}


class EnviarProdutoTest(TestCase):
    @mock.patch.object(ofertas.requests, "get")
    @mock.patch.object(ofertas, "abrir_materia", return_value=("", "", None))
    @mock.patch.object(ofertas, "ask_gemini", return_value=(json.dumps(EDICAO), []))
    def test_email_e_whatsapp(self, ask, abrir, get):
        ofertas.enviar_produto("Robô X", ["a@x.com"], [("5518999999999", "k1")])
        self.assertIn("Robô X", ask.call_args.args[0])  # {produto} trocado no prompt
        m = mail.outbox[0]
        self.assertEqual(m.subject, "Fuçador: Robô X")
        self.assertEqual(m.bcc, ["a@x.com"])
        html = m.alternatives[0].content
        self.assertIn(
            "https://www.kabum.com.br/busca/", html
        )  # sem fonte: link de busca da loja
        self.assertIn("cid:capa", html)
        params = get.call_args.kwargs["params"]
        self.assertEqual((params["phone"], params["apikey"]), ("5518999999999", "k1"))
        self.assertIn("*R$ 999,90*", params["text"])  # negrito do WhatsApp

    @mock.patch.object(ofertas.requests, "get")
    @mock.patch.object(ofertas, "abrir_materia", return_value=("", "", None))
    @mock.patch.object(ofertas, "ask_gemini", return_value=(json.dumps(EDICAO), []))
    def test_canal_vazio_e_pulado(self, ask, abrir, get):
        ofertas.enviar_produto("Robô X", ["a@x.com"], [])
        get.assert_not_called()
        self.assertEqual(len(mail.outbox), 1)

    def test_prompt_troca_hoje_e_produto(self):
        texto = ofertas.ofertas_prompt(
            "TV 50", 'Ofertas de {produto} em {hoje} {"x": 1}'
        )
        self.assertIn("Ofertas de TV 50 em ", texto)
        self.assertNotIn("{hoje}", texto)
        self.assertIn('{"x": 1}', texto)


class TarefaTest(TestCase):
    databases = {"default", "fucador"}

    @mock.patch.object(ofertas, "enviar_produto")
    def test_um_envio_por_produto_e_falha_nao_para_os_outros(self, enviar):
        Produto.objects.create(nome="A")
        Produto.objects.create(nome="B")
        Destinatario.objects.create(email="a@x.com")
        ContatoWhatsApp.objects.create(telefone="5518999999999", apikey="k")
        enviar.side_effect = [RuntimeError("Gemini fora"), None]
        views.tarefa()
        self.assertEqual(enviar.call_count, 2)
        status = dict(Envio.objects.values_list("produto", "status"))
        self.assertEqual(status, {"A": "falhou", "B": "enviado"})
        self.assertIn("Gemini fora", Envio.objects.get(produto="A").erro)

    @mock.patch.object(ofertas, "enviar_produto")
    def test_canal_desligado_nao_recebe(self, enviar):
        Produto.objects.create(nome="A")
        Destinatario.objects.create(email="a@x.com")
        ContatoWhatsApp.objects.create(telefone="5518999999999", apikey="k")
        config = Configuracao.atual()
        config.por_whatsapp = False
        config.save()
        views.tarefa()
        args = enviar.call_args.args
        self.assertEqual((args[1], args[2]), (["a@x.com"], []))

    @mock.patch.object(ofertas, "enviar_produto")
    def test_sem_destinatarios_nao_envia(self, enviar):
        Produto.objects.create(nome="A")
        views.tarefa()
        enviar.assert_not_called()

    def test_registrada_no_agendador(self):
        self.assertTrue(agendador.registrado("fucador"))


@mock.patch(
    "main.gemini.modelos_em_cache", new=lambda: []
)  # sem chamar a API do Google nos testes
class PaginaTest(TestCase):
    databases = {"default", "fucador"}

    def setUp(self):
        User.objects.create_user("fer", password="senha123")
        self.client.login(username="fer", password="senha123")

    def test_listas_adicionar_e_remover(self):
        self.client.post("/fucador/produto/adicionar/", {"nome": "TV 50"})
        r = self.client.post(
            "/fucador/email/adicionar/", {"nome": "Fulano", "email": "f@x.com"}
        )
        self.assertEqual(r["Location"], "/fucador/#sec-destinatarios")
        self.client.post(
            "/fucador/whatsapp/adicionar/", {"telefone": "5518999999999", "apikey": "k"}
        )
        self.assertEqual(Produto.objects.db, "fucador")
        pagina = self.client.get("/fucador/")
        self.assertContains(pagina, "TV 50")
        self.assertContains(pagina, "<strong>Fulano</strong> · f@x.com")
        self.assertContains(pagina, "5518999999999")
        self.assertNotContains(pagina, ">k<")
        p = Produto.objects.get()
        self.client.post(f"/fucador/produto/remover/{p.pk}/")
        self.assertFalse(Produto.objects.exists())

    def test_telefone_invalido_reabre_modal(self):
        r = self.client.post(
            "/fucador/whatsapp/adicionar/", {"telefone": "(18) 9999", "apikey": "k"}
        )
        self.assertContains(r, "getElementById('modal-whatsapp').showModal()</script>")
        self.assertFalse(ContatoWhatsApp.objects.exists())

    def test_tipo_desconhecido_404(self):
        self.assertEqual(
            self.client.post("/fucador/nada/adicionar/", {}).status_code, 404
        )

    def test_configuracao_e_restaurar(self):
        self.client.post(
            "/fucador/configuracao/",
            {
                "modelo": "gemini-2.5-pro",
                "prompt": "Ofertas de {produto}",
                "por_email": "on",
            },
        )
        c = Configuracao.atual()
        self.assertEqual(
            (c.modelo, c.prompt, c.por_email, c.por_whatsapp),
            ("gemini-2.5-pro", "Ofertas de {produto}", True, False),
        )
        self.assertContains(self.client.get("/fucador/"), "(canal desligado)")
        self.client.post("/fucador/configuracao/", {"restaurar": ""})
        c = Configuracao.atual()
        self.assertEqual(
            (c.modelo, c.prompt), ("gemini-3.8-flash", ofertas.PROMPT_PADRAO)
        )

    @mock.patch.object(agendador, "disparar")
    def test_enviar_dispara_tarefa(self, disparar):
        r = self.client.post("/fucador/enviar/")
        disparar.assert_called_once_with("fucador")
        self.assertEqual(r["Location"], "/fucador/#sec-envio")
