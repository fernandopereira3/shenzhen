from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from . import agendador
from .forms import AgendamentoForm
from .models import Agendamento

# icone: caminho em static/ (sem icone, mostra o emoji); pixel: logo em pixel art;
# recorte: logo com fundo transparente (salta do card sem a moldura quadrada)
BOTS = [
    {'url': 'braga', 'nome': 'Braga', 'icone': 'imgs/braga_logo.webp', 'pixel': True, 'recorte': True, 'emoji': '🤖',
     'descricao': 'Inscreve nos cursos do EAD da CECP e lista os incompletos de cada conta.'},
    {'url': 'news_', 'nome': 'Cronjob News', 'icone': 'imgs/news_logo.webp', 'recorte': True, 'emoji': '📰',
     'descricao': 'Monta um resumo diário de notícias com IA e envia por e-mail.'},
    {'url': 'fucador', 'nome': 'Fuçador', 'icone': 'imgs/fucador_logo.webp', 'recorte': True, 'emoji': '🏷️',
     'descricao': 'Procura as melhores ofertas dos produtos nas lojas e envia por e-mail.'},
]


@login_required
def index(request):
    return render(request, 'main/index.html', {'bots': BOTS})


@login_required
@require_POST
def agenda_adicionar(request, bot):
    if not agendador.registrado(bot):
        raise Http404
    form = AgendamentoForm(request.POST)
    if form.is_valid():
        ag = form.save(commit=False)
        ag.bot = bot
        ag.save()
    else:
        for erros in form.errors.values():
            for erro in erros:
                messages.error(request, erro)
    return redirect(reverse(bot) + '#sec-agenda')


@login_required
@require_POST
def agenda_remover(request, pk):
    ag = get_object_or_404(Agendamento, pk=pk)
    ag.delete()
    return redirect(reverse(ag.bot) + '#sec-agenda')


@login_required
@require_POST
def agenda_alternar(request, pk):
    """Pausa ou retoma um horário sem apagá-lo."""
    ag = get_object_or_404(Agendamento, pk=pk)
    ag.ativo = not ag.ativo
    ag.save(update_fields=['ativo'])
    return redirect(reverse(ag.bot) + '#sec-agenda')
