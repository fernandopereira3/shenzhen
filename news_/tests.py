import json
from unittest import mock

from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase

from main import agendador

from . import cronjob, views
from .models import Configuracao, Destinatario, Envio

EDICAO = {
    "abertura": "Bom dia!",
    "itens": [
        {
            "rotulo": "Mundo",
            "titulo": "Título 🌍",
            "destaque": "Algo **grande**",
            "texto": ["Parágrafo 1."],
            "fonte": "G1",
            "link": "",
        }
    ],
    "despedida": "Até amanhã, Cronjob News",
}


class EnviarNoticiasTest(TestCase):
    @mock.patch.object(cronjob, "abrir_materia", return_value=("", "", None))
    @mock.patch.object(
        cronjob,
        "ask_gemini",
        return_value=("```json\n" + json.dumps(EDICAO) + "\n```", ["u"]),
    )
    def test_monta_e_envia_com_capa_e_rodape(self, ask, abrir):
        cronjob.enviar_noticias(["a@x.com", "b@x.com"])
        m = mail.outbox[0]
        self.assertTrue(m.subject.startswith("🤖 Cronjob News "))
        self.assertEqual(m.bcc, ["a@x.com", "b@x.com"])
        self.assertIn("Algo grande", m.body)  # versão texto, sem os **
        html = m.alternatives[0].content
        self.assertIn("<b>grande</b>", html)
        self.assertIn("cid:capa", html)
        tipos = [p.get_content_type() for p in m.message().walk()]
        self.assertEqual(tipos.count("image/png"), 2)

    @mock.patch.object(cronjob, "abrir_materia", return_value=("", "", None))
    @mock.patch.object(cronjob, "ask_gemini", return_value=(json.dumps(EDICAO), []))
    def test_tenta_3_vezes_quando_vem_sem_fontes(self, ask, abrir):
        cronjob.enviar_noticias(["a@x.com"])
        self.assertEqual(ask.call_count, 3)
        self.assertEqual(len(mail.outbox), 1)


class TarefaTest(TestCase):
    databases = {"default", "news_"}

    @mock.patch.object(cronjob, "enviar_noticias")
    def test_registra_envio(self, enviar):
        Destinatario.objects.create(email="a@x.com")
        views.tarefa()
        enviar.assert_called_once_with(
            ["a@x.com"], cronjob.PROMPT_PADRAO, cronjob.GEMINI_MODEL
        )
        e = Envio.objects.get()
        self.assertEqual((e.status, e.destinatarios), ("enviado", 1))

    @mock.patch.object(
        cronjob, "enviar_noticias", side_effect=RuntimeError("SMTP fora")
    )
    def test_falha_fica_no_historico(self, enviar):
        Destinatario.objects.create(email="a@x.com")
        with self.assertRaises(RuntimeError):
            views.tarefa()
        e = Envio.objects.get()
        self.assertEqual(e.status, "falhou")
        self.assertIn("SMTP fora", e.erro)

    @mock.patch.object(cronjob, "enviar_noticias")
    def test_sem_destinatarios_nao_envia(self, enviar):
        views.tarefa()
        enviar.assert_not_called()
        self.assertFalse(Envio.objects.exists())

    def test_registrada_no_agendador(self):
        self.assertTrue(agendador.registrado("news_"))


@mock.patch(
    "main.gemini.modelos_em_cache", new=lambda: []
)  # sem chamar a API do Google nos testes
class PaginaTest(TestCase):
    databases = {"default", "news_"}

    def setUp(self):
        User.objects.create_user("fer", password="senha123")
        self.client.login(username="fer", password="senha123")

    def test_adicionar_remover_e_listar(self):
        self.client.post("/news/adicionar/", {"nome": "Fulano", "email": "f@x.com"})
        d = Destinatario.objects.get()
        self.assertEqual(Destinatario.objects.db, "news_")
        r = self.client.get("/news/")
        self.assertContains(r, "<strong>Fulano</strong> · f@x.com")
        self.assertContains(r, "Enviar agora")
        self.client.post(f"/news/remover/{d.pk}/")
        self.assertFalse(Destinatario.objects.exists())

    def test_email_invalido_reabre_modal(self):
        r = self.client.post("/news/adicionar/", {"email": "nao-e-email"})
        self.assertContains(r, "getElementById('destinatarios').showModal()</script>")
        self.assertFalse(Destinatario.objects.exists())

    @mock.patch.object(agendador, "disparar")
    def test_enviar_dispara_tarefa(self, disparar):
        r = self.client.post("/news/enviar/")
        disparar.assert_called_once_with("news_")
        self.assertEqual(r["Location"], "/news/#sec-envio")


class PromptTest(TestCase):
    databases = {"default", "news_"}

    def setUp(self):
        p = mock.patch(
            "main.gemini.modelos_em_cache",
            return_value=[("gemini-2.5-pro", "Gemini 2.5 Pro")],
        )
        p.start()
        self.addCleanup(p.stop)
        User.objects.create_user("fer", password="senha123")
        self.client.login(username="fer", password="senha123")

    def test_hoje_vira_data_e_chaves_nao_quebram(self):
        texto = cronjob.noticias_prompt('Notícias de {hoje} em JSON {"a": 1}')
        self.assertNotIn("{hoje}", texto)
        self.assertIn('{"a": 1}', texto)
        self.assertIn("Hoje é", cronjob.noticias_prompt())

    def test_editar_e_restaurar(self):
        self.assertContains(self.client.get("/news/"), "grandes portais de notícias")
        r = self.client.post(
            "/news/prompt/",
            {"modelo": "gemini-2.5-pro", "prompt": "Só tecnologia de {hoje}"},
        )
        self.assertEqual(r["Location"], "/news/#sec-gemini")
        config = Configuracao.atual()
        self.assertEqual(
            (config.modelo, config.prompt),
            ("gemini-2.5-pro", "Só tecnologia de {hoje}"),
        )
        self.client.post("/news/prompt/", {"restaurar": ""})
        config = Configuracao.atual()
        self.assertEqual(
            (config.modelo, config.prompt),
            (cronjob.GEMINI_MODEL, cronjob.PROMPT_PADRAO),
        )

    def test_prompt_vazio_nao_salva(self):
        self.client.post("/news/prompt/", {"modelo": "x", "prompt": "   "})
        self.assertEqual(Configuracao.atual().prompt, cronjob.PROMPT_PADRAO)

    @mock.patch.object(cronjob, "enviar_noticias")
    def test_envio_usa_prompt_editado(self, enviar):
        Destinatario.objects.create(email="a@x.com")
        self.client.post(
            "/news/prompt/", {"modelo": "gemini-2.5-pro", "prompt": "Meu prompt {hoje}"}
        )
        views.tarefa()
        enviar.assert_called_once_with(
            ["a@x.com"], "Meu prompt {hoje}", "gemini-2.5-pro"
        )


class ListarModelosTest(TestCase):
    @mock.patch("main.gemini.requests.get")
    def test_filtra_so_gemini_de_texto(self, get):
        get.return_value.json.return_value = {
            "models": [
                {
                    "name": "models/gemini-3.8-flash",
                    "displayName": "Gemini 3.8 Flash",
                    "supportedGenerationMethods": ["generateContent"],
                },
                {
                    "name": "models/gemini-3.8-flash-tts",
                    "supportedGenerationMethods": ["generateContent"],
                },
                {
                    "name": "models/gemini-3-pro-image",
                    "supportedGenerationMethods": ["generateContent"],
                },
                {
                    "name": "models/gemma-4-31b-it",
                    "supportedGenerationMethods": ["generateContent"],
                },
                {
                    "name": "models/text-embedding",
                    "supportedGenerationMethods": ["embedContent"],
                },
            ]
        }
        from main import gemini

        self.assertEqual(
            gemini.listar_modelos(), [("gemini-3.8-flash", "Gemini 3.8 Flash")]
        )

    @mock.patch("main.gemini.listar_modelos", side_effect=RuntimeError("sem rede"))
    def test_api_fora_lista_vazia(self, listar):
        from django.core.cache import cache

        from main import gemini

        cache.delete("gemini_modelos")
        self.assertEqual(gemini.modelos_em_cache(), [])
