from django.contrib.auth.decorators import login_required
from django.db import close_old_connections
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from main import agendador, gemini

from . import cronjob
from .cronjob import GEMINI_MODEL, PROMPT_PADRAO
from .forms import DestinatarioForm, PromptForm
from .models import Configuracao, Destinatario, Envio


def tarefa():
    """Monta e envia a newsletter; registrada no agendador (ver apps.py) e usada pelo botão."""
    para = list(Destinatario.objects.values_list('email', flat=True))
    if not para:
        print('📰 Cronjob News: nenhum destinatário, envio pulado')
        return
    envio = Envio.objects.create(destinatarios=len(para))
    try:
        config = Configuracao.atual()
        cronjob.enviar_noticias(para, config.prompt, config.modelo)
        envio.status = Envio.ENVIADO
    except Exception as erro:  # rede, Gemini ou SMTP: registra e deixa os próximos envios seguirem
        envio.status = Envio.FALHOU
        envio.erro = repr(erro)
        raise
    finally:
        envio.fim = timezone.now()
        envio.save()
        close_old_connections()


@login_required
def index(request, form=None, prompt_form=None):
    return render(request, 'news_/index.html', {
        'destinatarios': Destinatario.objects.all(),
        'form': form or DestinatarioForm(),
        'abrir_modal': form is not None,
        'enviando': agendador.rodando('news_'),
        'historico': Envio.objects.all()[:30],
        'prompt_form': prompt_form or PromptForm(instance=Configuracao.atual()),
        'modelos': gemini.modelos_em_cache(),
        'modelo_padrao': GEMINI_MODEL,
    })


@login_required
@require_POST
def adicionar(request):
    form = DestinatarioForm(request.POST)
    if not form.is_valid():
        return index(request, form)
    form.save()
    return redirect('news_')


@login_required
@require_POST
def remover(request, pk):
    get_object_or_404(Destinatario, pk=pk).delete()
    return redirect('news_')


@login_required
@require_POST
def enviar(request):
    agendador.disparar('news_')
    return redirect(reverse('news_') + '#sec-envio')


@login_required
@require_POST
def prompt(request):
    config = Configuracao.atual()
    if 'restaurar' in request.POST:
        config.prompt, config.modelo = PROMPT_PADRAO, GEMINI_MODEL
        config.save()
    else:
        form = PromptForm(request.POST, instance=config)
        if not form.is_valid():
            return index(request, prompt_form=form)
        form.save()
    return redirect(reverse('news_') + '#sec-gemini')
