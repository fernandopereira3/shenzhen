# Shenzhen

Shenzhen é uma "cidade de bots": um site Django em que cada bot é um morador com casa própria (um app Django), banco de dados próprio e página própria. A cidade cuida do que todos usam: login, painel inicial, agendador de horários, envio de e-mail e acesso ao Gemini.

Hoje moram na cidade três bots:

| Bot | Rota | O que faz |
|---|---|---|
| 🤖 **Braga** | `/braga/` | Entra no EAD da Polícia Penal de SP com cada conta cadastrada, se inscreve nos cursos e lista os que estão incompletos. |
| 📰 **Cronjob News** | `/news/` | Pede ao Gemini um resumo das notícias do dia (com busca no Google) e envia uma newsletter por e-mail. |
| 🏷️ **Fuçador** | `/fucador/` | Para cada produto cadastrado, pede ao Gemini as melhores ofertas nas lojas e envia por e-mail e/ou WhatsApp. |

A cidade foi feita para crescer: adicionar um bot novo é criar um app e ligá-lo em quatro lugares (veja [Como adicionar um bot novo](#como-adicionar-um-bot-novo)).

---

## Sumário

- [Como a cidade funciona](#como-a-cidade-funciona)
- [Os bots](#os-bots)
- [Rodando o projeto](#rodando-o-projeto)
- [Como adicionar um bot novo](#como-adicionar-um-bot-novo)
- [Limitações conhecidas](#limitações-conhecidas)

---

## Como a cidade funciona

```
                 ┌──────────── navegador ────────────┐
                 │ /login → /main (painel com cards) │
                 └──────┬───────────┬───────────┬────┘
                        │           │           │
                    /braga/      /news/     /fucador/      ← página de cada bot
                        │           │           │
   ┌────────────────────┼───────────┼───────────┼─────────────────────┐
   │ main (prefeitura)  │           │           │                     │
   │  • agendador ──────┴── dispara a tarefa ───┘  (thread, a cada 20s)│
   │  • emails.enviar_email  (Gmail)                                   │
   │  • gemini.ask_gemini    (Gemini + busca do Google)                │
   └───────────────────────────────────────────────────────────────────┘
                        │           │           │
              db_braga.sqlite3  db_news.sqlite3  db_fucador.sqlite3
                       (+ db.sqlite3: usuários, sessões, agenda)
```

### Estrutura de pastas

```
shenzhen/        configuração do Django: settings, urls, roteador de bancos
login/           login e cadastro de usuário
main/            a "prefeitura": painel, agendador, e-mail, Gemini, templatetags
braga/           bot Braga (Selenium)
news_/           bot Cronjob News
fucador/         bot Fuçador
templates/       base.html e bot_base.html (layout comum das páginas de bot)
static/          CSS, JS e logos dos bots
```

### Login

[login/](login/) usa o login padrão do Django. Na tela de login dá para criar usuário (modal "novo usuário"). Todas as páginas dos bots exigem login.

### Painel (`/main/`)

[main/views.py](main/views.py) tem a lista `BOTS`, com nome, logo, emoji e descrição de cada bot. O painel desenha um card para cada item dessa lista. A mesma lista alimenta o cabeçalho lateral das páginas de bot (`{% painel_bot %}`, em [main/templatetags/bots.py](main/templatetags/bots.py)).

### Um banco por bot

Cada bot guarda seus dados num arquivo SQLite separado:

- `db.sqlite3` (alias `default`): usuários, sessões e a agenda de horários (`main.Agendamento`)
- `db_braga.sqlite3`, `db_news.sqlite3`, `db_fucador.sqlite3`: os dados de cada bot

Quem decide o banco é o [shenzhen/routers.py](shenzhen/routers.py) (`BotRouter`): se o app está na lista `BOTS_COM_BANCO` do [settings](shenzhen/settings.py), os models dele vão para o banco com o nome do app; senão, vão para o `default`. Por isso um bot **não pode ter chave estrangeira** para models de outro banco (SQLite não liga arquivos diferentes).

A pasta dos bancos vem da variável `DB_DIR` (no Docker é `/data`, um volume).

### Agendador

[main/agendador.py](main/agendador.py) é o relógio da cidade:

1. No `ready()` do seu `AppConfig`, cada bot se registra com `agendador.registrar('<bot>', funcao)`.
2. Quando o servidor sobe com `runserver`, [main/apps.py](main/apps.py) inicia uma thread que, a cada 20 segundos, olha os `Agendamento` ativos.
3. Se um horário venceu (`Agendamento.deve_rodar`), o agendador roda a função do bot numa thread em segundo plano. Se o bot ainda está rodando, ele não começa outra execução por cima.

Cada horário pode ser **"Todo dia às HH:MM"** (com 2 minutos de tolerância) ou **"A cada N minutos"**, e pode ser pausado sem ser apagado. A página de cada bot mostra o card de agenda com `{% agenda_card '<bot>' %}` ([main/templatetags/agenda.py](main/templatetags/agenda.py)); as rotas de agenda ficam em `/agenda/`.

> O nome do bot é a mesma chave em todo lugar: no `registrar`, no `Agendamento.bot`, no `name` da rota da página e no `url` da lista `BOTS`. Depois de mexer na agenda, a view volta para `reverse(bot)`, então os quatro precisam ser iguais.

### Serviços compartilhados

- **E-mail** — [main/emails.py](main/emails.py), `enviar_email(assunto, texto, html, para, imagens)`. Envia pelo Gmail configurado em `MAILERS` no settings. Os destinatários vão em cópia oculta, e as imagens podem ser embutidas no HTML (`<img src="cid:nome">`).
- **Gemini** — [main/gemini.py](main/gemini.py), `ask_gemini(prompt, modelo)` devolve `(texto, links das fontes)`. Sempre liga a busca do Google, para o modelo procurar coisas de hoje em vez de inventar. `listar_modelos` e `modelos_em_cache` alimentam a escolha de modelo nas páginas dos bots.

### Layout das páginas de bot

[templates/bot_base.html](templates/bot_base.html) dá a todas as páginas de bot o mesmo formato: um painel lateral (logo, nome, descrição e links das seções) e o conteúdo dividido em seções `id="sec-..."`, que viram abas com JavaScript. A página do bot estende esse template e preenche os blocos `secoes` e `bot_conteudo`.

---

## Os bots

### 🤖 Braga — `braga/`

Automatiza o EAD (Moodle) da Polícia Penal de SP com Selenium e Chromium headless.

**Para cada conta cadastrada (CPF + senha):**
1. faz login em `ead.policiapenal.sp.gov.br`;
2. abre `enrol/index.php?id=N` para os cursos de 1 até `ENROL_ID_MAX` (padrão 100) e clica em "Inscreva-me" onde aparecer;
3. abre "Meus cursos", confere o progresso de cada um e guarda os incompletos.

**Na página:**
- abas de contas (adicionar e remover), log ao vivo, histórico e agenda;
- botões **Rodar** e **Cancelar**; o cancelamento é checado entre um passo e outro;
- o log ao vivo vem de `braga/users/execucao.log`, que a página lê pela rota `/braga/status/`;
- o histórico guarda cada `Execucao` (rodando, concluída, cancelada ou falhou) com seus `Incompleto`.

**Arquivos:** [braga/bot.py](braga/bot.py) (o robô em si), [braga/views.py](braga/views.py) (thread de execução e páginas), [braga/models.py](braga/models.py).

**Detalhes:**
- O servidor do EAD não manda o certificado intermediário da GlobalSign; ele fica em [braga/ssl/](braga/ssl/) e é somado ao bundle do `certifi`.
- `CHROME_BIN` e `CHROMEDRIVER_PATH` apontam para o Chromium e o chromedriver do sistema. No Docker (ARM64) isso é obrigatório, porque o Selenium Manager não baixa driver para linux/aarch64.
- A senha das contas fica em texto puro no banco, porque o bot precisa dela para logar.

### 📰 Cronjob News — `news_/`

Monta e envia uma newsletter diária.

1. Manda ao Gemini o prompt configurado. O prompt pede uma resposta em JSON (`abertura`, `itens` e `despedida`).
2. Para cada item, abre o link da notícia, segue o redirecionamento do Google e pega título, descrição e imagem de capa (`og:image`).
3. Monta o e-mail em HTML (com `imgs/capa.png` e `imgs/rodape.png` embutidas) e em texto puro, e envia para todos os destinatários.

**Na página:** destinatários, prompt e modelo do Gemini (com botão para voltar ao prompt padrão), botão **Enviar agora**, histórico de envios (`Envio`, com o erro quando falha) e agenda.

**Arquivos:** [news_/cronjob.py](news_/cronjob.py) (montagem da newsletter), [news_/views.py](news_/views.py) (`tarefa()` é o que o agendador roda).

> O app se chama `news_` (com sublinhado), mas a rota é `/news/` e o banco é `db_news.sqlite3`.

### 🏷️ Fuçador — `fucador/`

Caçador de ofertas. Para **cada produto** cadastrado:

1. pede ao Gemini as melhores ofertas do produto (mesmo formato JSON do News);
2. troca o link de cada oferta pelo link da busca da loja (Mercado Livre, Magalu, Casas Bahia, Amazon, KaBuM, Zoom, Buscapé), porque o Gemini quase nunca devolve a página exata da oferta;
3. envia por **e-mail** (com `imgs/fucador_banner.png` e `imgs/fucador_rodape.png`) e/ou por **WhatsApp** via [CallMeBot](https://www.callmebot.com/).

Se um produto falha, os outros continuam; cada produto vira uma linha no histórico.

**WhatsApp:** cada contato precisa da própria apikey do CallMeBot. Para conseguir a sua, a pessoa manda `I allow callmebot to send me messages` para +34 644 71 81 99. O telefone vai só com dígitos (DDI + DDD + número).

**Na página:** produtos, destinatários (e-mail e WhatsApp), configuração (prompt, modelo e quais canais ligar), botão **Enviar agora**, histórico e agenda.

**Arquivos:** [fucador/ofertas.py](fucador/ofertas.py), [fucador/views.py](fucador/views.py).

---

## Rodando o projeto

### Variáveis de ambiente

Copie o [.env.example](.env.example) para `.env` e preencha:

| Variável | Obrigatória | Para quê |
|---|---|---|
| `SECRET_KEY` | sim | chave do Django |
| `EMAIL_PASSWORD` | sim | senha de app do Gmail do remetente |
| `GEMINI_KEY` | para News e Fuçador | chave da API do Gemini |
| `DEBUG` | não | `1` liga o modo debug |
| `DB_DIR` | não | pasta dos `.sqlite3` (padrão: raiz do projeto) |
| `CHROME_BIN`, `CHROMEDRIVER_PATH` | não | Chromium e chromedriver do sistema, para o Braga |
| `ENROL_ID_MAX` | não | até qual id de curso o Braga tenta se inscrever (padrão 100) |

O `.env` está no `.gitignore` e **nunca** deve ir para o git.

### Localmente (com [uv](https://docs.astral.sh/uv/))

Precisa de Python 3.14. Para usar o Braga, também precisa do Chromium instalado.

```bash
uv sync

# cada banco migra separado
for db in default braga news_ fucador; do
  uv run --env-file .env python manage.py migrate --database $db
done

uv run --env-file .env python manage.py runserver
```

Abra http://localhost:8000, crie um usuário na tela de login e entre.

> O agendador só sobe com `runserver`. Comandos como `migrate`, `test` e `shell` não disparam bots.

### Testes

```bash
uv run --env-file .env python manage.py test
```

### Docker

O [Dockerfile](Dockerfile) instala Chromium e chromedriver, migra os quatro bancos e sobe o `runserver` na porta 8000. O [compose.yaml](compose.yaml) usa a imagem `fernandopereira3/shenzhen:latest` (ARM64), lê o `.env` e guarda os bancos no volume `/data`.

```bash
docker compose up -d
```

> No compose, o volume aponta para `/srv/samba/programas/Volumes/shenzhen`. Troque esse caminho se for rodar em outra máquina.

---

## Como adicionar um bot novo

Exemplo: um bot chamado `clima`.

**1. Crie o app**

```bash
uv run python manage.py startapp clima
```

**2. Escreva a tarefa e registre no agendador.** A tarefa é a função que o agendador vai rodar: uma função sem argumentos, que faz o trabalho do bot e fecha a conexão com o banco no fim (ela roda numa thread própria).

```python
# clima/views.py
from django.db import close_old_connections

def tarefa():
    try:
        ...  # o trabalho do bot
    finally:
        close_old_connections()
```

```python
# clima/apps.py
from django.apps import AppConfig

class ClimaConfig(AppConfig):
    name = 'clima'

    def ready(self):
        from main import agendador
        from . import views
        agendador.registrar('clima', views.tarefa)
```

**3. Ligue o bot na cidade:**

- [shenzhen/settings.py](shenzhen/settings.py): coloque `'clima'` em `INSTALLED_APPS` e em `BOTS_COM_BANCO` (se o bot tiver models; isso cria o `db_clima.sqlite3`).
- [shenzhen/urls.py](shenzhen/urls.py): `path('clima/', include('clima.urls'))`.
- `clima/urls.py`: a página principal precisa ter `name='clima'`, o mesmo nome do registro.
- [main/views.py](main/views.py): adicione um item na lista `BOTS` com `url`, `nome`, `emoji`, `descricao` e, se quiser, `icone` (logo em `static/imgs/`).
- [Dockerfile](Dockerfile): acrescente `clima` no `for db in ...` do `CMD`, para o banco novo ser migrado.

**4. Monte a página** estendendo o layout comum:

```django
{% extends 'bot_base.html' %}
{% load agenda %}

{% block secoes %}
  <li><a href="#sec-principal">Principal</a></li>
  <li><a href="#sec-agenda">Agenda</a></li>
{% endblock %}

{% block bot_conteudo %}
  <section id="sec-principal">...</section>
  {% agenda_card 'clima' %}
{% endblock %}
```

**5. Migre e teste**

```bash
uv run --env-file .env python manage.py makemigrations clima
uv run --env-file .env python manage.py migrate --database clima
```

**Para reaproveitar:**
- Envia e-mail? Use `main.emails.enviar_email`.
- Usa IA? Use `main.gemini.ask_gemini`. O News e o Fuçador mostram o padrão de prompt com resposta em JSON (`FORMATO_JSON`) e de configuração editável na página (`Configuracao.atual()`, sempre `pk=1`).
- Guarde um histórico de execuções (`Envio` ou `Execucao`, com status e erro), como os bots atuais, para a página mostrar o que aconteceu.

**Regras da casa:**
- O nome do bot é o mesmo em todo lugar: app, `registrar`, `name` da rota e `url` em `BOTS`.
- Nada de chave estrangeira entre bots, nem para `User`: cada bot vive no seu próprio arquivo de banco.
- Segredos vão no `.env` e são lidos com `os.environ`, nunca escritos no código.
- A tarefa não deve deixar exceção derrubar nada: registre o erro no histórico e deixe a próxima execução acontecer.

---

## Limitações conhecidas

- **Agendador e execuções rodam em threads dentro do `runserver`.** Se o servidor reinicia, a execução em andamento se perde. Com vários workers (gunicorn), cada worker dispararia os bots. Para produção séria, o caminho é trocar por cron, Celery beat ou RQ.
- **Senhas do Braga em texto puro** no `db_braga.sqlite3`. Proteja o volume `/data`.
- **`ALLOWED_HOSTS = ['*']`** e qualquer pessoa que abra a tela de login pode criar um usuário. Não exponha o site direto na internet sem limitar isso.
- O remetente de e-mail (`shenzhenbot@gmail.com` / `DEFAULT_FROM_EMAIL`) está fixo no settings.
