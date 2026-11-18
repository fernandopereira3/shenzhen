from datetime import datetime, time, timedelta
from unittest import mock
from zoneinfo import ZoneInfo

from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase

from . import agendador
from .emails import enviar_email
from .models import Agendamento

SP = ZoneInfo('America/Sao_Paulo')


def hora(d, h, m, s=0):
    return datetime(2026, 11, d, h, m, s, tzinfo=SP)


class AgendamentoTest(TestCase):
    def test_diario_roda_uma_vez_no_horario(self):
        ag = Agendamento(bot='x', tipo='diario', horario=time(8, 0))
        self.assertFalse(ag.deve_rodar(hora(14, 7, 59)))
        self.assertTrue(ag.deve_rodar(hora(14, 8, 0, 10)))
        ag.ultima_execucao = hora(14, 8, 0, 10)
        self.assertFalse(ag.deve_rodar(hora(14, 8, 0, 40)))   # mesmo horário: não repete
        self.assertFalse(ag.deve_rodar(hora(14, 15, 0)))      # passou a janela: não recupera
        self.assertTrue(ag.deve_rodar(hora(15, 8, 1)))        # dia seguinte
        self.assertEqual(ag.proxima(hora(14, 9, 0)), hora(15, 8, 0))

    def test_intervalo(self):
        ag = Agendamento(bot='x', tipo='intervalo', intervalo=60)
        self.assertTrue(ag.deve_rodar(hora(14, 9, 0)))        # nunca rodou: roda já
        ag.ultima_execucao = hora(14, 9, 0)
        self.assertFalse(ag.deve_rodar(hora(14, 9, 59)))
        self.assertTrue(ag.deve_rodar(hora(14, 10, 0)))
        self.assertEqual(ag.proxima(hora(14, 9, 30)), hora(14, 10, 0))

    def test_checar_dispara_so_bots_registrados_e_ativos(self):
        Agendamento.objects.create(bot='braga', tipo='diario', horario=time(8, 0))
        Agendamento.objects.create(bot='fantasma', tipo='intervalo', intervalo=5)
        Agendamento.objects.create(bot='braga', tipo='intervalo', intervalo=5, ativo=False)
        with mock.patch.object(agendador, 'disparar') as disparar:
            agendador.checar(hora(14, 8, 0, 5))
            agendador.checar(hora(14, 8, 0, 30))
        disparar.assert_called_once_with('braga')

    def test_disparar_nao_sobrepoe(self):
        import threading
        liberar = threading.Event()
        with mock.patch.dict(agendador._tarefas, {'t': liberar.wait}), \
                mock.patch.dict(agendador._threads, {}):
            self.assertTrue(agendador.disparar('t'))
            self.assertFalse(agendador.disparar('t'))
            liberar.set()
            agendador._threads['t'].join(1)
            self.assertFalse(agendador.disparar('nao-registrado'))


@mock.patch('main.gemini.modelos_em_cache', new=lambda: [])  # sem chamar a API do Google nos testes
class AgendaViewsTest(TestCase):
    databases = {'default', 'braga', 'news_', 'fucador'}  # abre as páginas dos bots

    def setUp(self):
        User.objects.create_user('fer', password='senha123')
        self.client.login(username='fer', password='senha123')

    def test_adicionar_mostrar_e_remover(self):
        r = self.client.post('/agenda/braga/adicionar/', {'tipo': 'diario', 'horario': '08:00'})
        self.assertEqual(r['Location'], '/braga/#sec-agenda')
        self.client.post('/agenda/braga/adicionar/', {'tipo': 'intervalo', 'intervalo': '30', 'horario': '09:00'})
        diario, intervalo = Agendamento.objects.order_by('tipo')
        self.assertEqual(str(diario), 'Todo dia às 08:00')
        self.assertIsNone(intervalo.horario)  # campo do outro tipo é descartado
        pagina = self.client.get('/braga/')
        self.assertContains(pagina, 'Todo dia às 08:00')
        self.assertContains(pagina, 'A cada 30 min')
        self.client.post(f'/agenda/{diario.pk}/remover/')
        self.assertEqual(Agendamento.objects.count(), 1)

    def test_erro_vira_mensagem(self):
        r = self.client.post('/agenda/braga/adicionar/', {'tipo': 'diario'}, follow=True)
        self.assertContains(r, 'Informe o horário.')
        self.assertFalse(Agendamento.objects.exists())

    def test_bot_sem_tarefa_da_404(self):
        r = self.client.post('/agenda/nada/adicionar/', {'tipo': 'diario', 'horario': '08:00'})
        self.assertEqual(r.status_code, 404)

    def test_exige_login(self):
        self.client.logout()
        r = self.client.post('/agenda/braga/adicionar/', {'tipo': 'diario', 'horario': '08:00'})
        self.assertEqual(r.status_code, 302)
        self.assertFalse(Agendamento.objects.exists())


class EnviarEmailTest(TestCase):
    def test_bcc_html_e_imagem_embutida(self):
        enviar_email('Assunto', 'texto puro', '<img src="cid:capa">', ['a@x.com', 'b@x.com'],
                     {'capa': b'\x89PNG-fake'})
        self.assertEqual(len(mail.outbox), 1)
        m = mail.outbox[0]
        self.assertEqual(m.to, ['sap.fernando.pereira@gmail.com'])
        self.assertEqual(m.bcc, ['a@x.com', 'b@x.com'])
        tipos = [p.get_content_type() for p in m.message().walk()]
        self.assertEqual(tipos, ['multipart/alternative', 'text/plain',
                                 'multipart/related', 'text/html', 'image/png'])
        self.assertNotIn('Bcc', m.message())  # cópia oculta não vai no cabeçalho

    def test_so_texto(self):
        enviar_email('A', 'só texto', para=['a@x.com'])
        self.assertEqual(mail.outbox[0].body, 'só texto')


@mock.patch('main.gemini.modelos_em_cache', new=lambda: [])
class PausarTest(TestCase):
    databases = {'default', 'braga', 'news_', 'fucador'}

    def setUp(self):
        User.objects.create_user('fer', password='senha123')
        self.client.login(username='fer', password='senha123')

    def test_pausar_e_retomar(self):
        ag = Agendamento.objects.create(bot='braga', tipo='diario', horario=time(8, 0))
        r = self.client.post(f'/agenda/{ag.pk}/alternar/')
        self.assertEqual(r['Location'], '/braga/#sec-agenda')
        ag.refresh_from_db()
        self.assertFalse(ag.ativo)
        pagina = self.client.get('/braga/')
        self.assertContains(pagina, 'Pausado')
        self.assertContains(pagina, 'Retomar')
        self.assertContains(pagina, 'Todos os horários estão pausados.')
        with mock.patch.object(agendador, 'disparar') as disparar:
            agendador.checar(hora(14, 8, 0, 5))
        disparar.assert_not_called()
        self.client.post(f'/agenda/{ag.pk}/alternar/')
        ag.refresh_from_db()
        self.assertTrue(ag.ativo)
