from unittest import mock
from django.contrib.auth.models import User
from django.test import TestCase


@mock.patch('main.gemini.modelos_em_cache', new=lambda: [])  # sem chamar a API do Google nos testes
class LoginTest(TestCase):
    databases = {'default', 'braga', 'news_', 'fucador'}  # abre as páginas dos bots

    def test_raiz_vai_pro_login(self):
        self.assertRedirects(self.client.get('/'), '/login/')

    def test_main_exige_login(self):
        self.assertRedirects(self.client.get('/main/'), '/login/?next=/main/')

    def test_login_leva_ao_main(self):
        User.objects.create_user('fer', password='senha123')
        r = self.client.post('/login/', {'username': 'fer', 'password': 'senha123'})
        self.assertRedirects(r, '/main/')
        self.assertContains(self.client.get('/main/'), '<span>fer</span>')

    def test_logado_no_login_vai_pro_main(self):
        User.objects.create_user('fer', password='senha123')
        self.client.login(username='fer', password='senha123')
        self.assertRedirects(self.client.get('/login/'), '/main/')

    def test_sair(self):
        User.objects.create_user('fer', password='senha123')
        self.client.login(username='fer', password='senha123')
        self.assertRedirects(self.client.post('/login/sair/'), '/login/')
        self.assertRedirects(self.client.get('/main/'), '/login/?next=/main/')

    def test_novo_usuario(self):
        dados = {'username': 'novo', 'password1': 'Xk9!senhaforte', 'password2': 'Xk9!senhaforte'}
        self.assertRedirects(self.client.post('/login/novo/', dados), '/main/')
        self.assertTrue(User.objects.filter(username='novo').exists())

    def test_novo_usuario_invalido_reabre_modal(self):
        r = self.client.post('/login/novo/', {'username': 'x', 'password1': 'a', 'password2': 'b'})
        self.assertContains(r, 'showModal()</script>')
        self.assertFalse(User.objects.filter(username='x').exists())

    def test_modulos(self):
        for url in ('/braga/', '/news/', '/fucador/'):
            self.assertRedirects(self.client.get(url), f'/login/?next={url}')
        User.objects.create_user('fer', password='senha123')
        self.client.login(username='fer', password='senha123')
        for url in ('/braga/', '/news/', '/fucador/'):
            self.assertContains(self.client.get(url), '<span>fer</span>')

    def test_cards_dos_bots(self):
        User.objects.create_user('fer', password='senha123')
        self.client.login(username='fer', password='senha123')
        r = self.client.get('/main/')
        for url, nome in (('/braga/', 'Braga'), ('/news/', 'Cronjob News'), ('/fucador/', 'Fuçador')):
            self.assertContains(r, f'href="{url}"')
            self.assertContains(r, f'<h2>{nome}</h2>')
        self.assertContains(r, 'js/bot-cards.js')

    def test_navbar_so_tem_marca_usuario_e_sair(self):
        User.objects.create_user('fer', password='senha123')
        self.client.login(username='fer', password='senha123')
        nav = self.client.get('/main/').content.decode().split('</nav>')[0]
        self.assertNotIn('>Braga</a>', nav)
        self.assertNotIn('>Início</a>', nav)
        self.assertIn('<span>fer</span>', nav)
        self.assertIn('Sair', nav)
        for url in ('/main/', '/braga/', '/news/', '/fucador/'):
            nav = self.client.get(url).content.decode().split('</nav>')[0]
            self.assertNotIn('Voltar', nav)
            self.assertIn('class="brand" href="/main/"', nav)  # a marca leva de volta ao início
            self.assertIn('<span>fer</span>', nav)

    def test_painel_lateral_dos_bots(self):
        User.objects.create_user('fer', password='senha123')
        self.client.login(username='fer', password='senha123')
        r = self.client.get('/braga/')
        self.assertContains(r, '<aside class="bot-lateral">')
        self.assertContains(r, '<h1>Braga</h1>')
        for secao in ('sec-contas', 'sec-agenda', 'sec-execucao'):
            self.assertContains(r, f'href="#{secao}"')
            self.assertContains(r, f'id="{secao}"')
        for url, nome in (('/news/', 'Cronjob News'), ('/fucador/', 'Fuçador')):
            r = self.client.get(url)
            self.assertContains(r, f'<h1>{nome}</h1>')
            self.assertContains(r, '<aside class="bot-lateral">')
