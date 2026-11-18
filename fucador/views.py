from django.contrib.auth.decorators import login_required
from django.db import close_old_connections
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from main import agendador, gemini

from . import ofertas
from .forms import ConfiguracaoForm, DestinatarioForm, ProdutoForm, WhatsAppForm
from .models import Configuracao, ContatoWhatsApp, Destinatario, Envio, Produto

# tipo na URL -> (model, form, aba onde fica)
LISTAS = {
    'produto': (Produto, ProdutoForm, 'sec-produtos'),
    'email': (Destinatario, DestinatarioForm, 'sec-destinatarios'),
    'whatsapp': (ContatoWhatsApp, WhatsAppForm, 'sec-destinatarios'),
}


def tarefa():
    """Uma busca + envio por produto; a falha de um não impede os outros (como ofertas() do original)."""
    config = Configuracao.atual()
    emails = list(Destinatario.objects.values_list('email', flat=True)) if config.por_email else []
    whatsapps = list(ContatoWhatsApp.objects.values_list('telefone', 'apikey')) if config.por_whatsapp else []
    if not emails and not whatsapps:
        print('🏷️ Fuçador: nenhum destinatário nos canais ligados, envio pulado')
        return
    try:
        for produto in Produto.objects.values_list('nome', flat=True):
            envio = Envio.objects.create(produto=produto, emails=len(emails), whatsapps=len(whatsapps))
            try:
                ofertas.enviar_produto(produto, emails, whatsapps, config.prompt, config.modelo)
                envio.status = Envio.ENVIADO
            except Exception as erro:  # rede, Gemini, SMTP ou CallMeBot: registra e segue pro próximo
                print(f'🏷️ Fuçador: {produto} falhou: {erro!r}')
                envio.status = Envio.FALHOU
                envio.erro = repr(erro)
            envio.fim = timezone.now()
            envio.save()
    finally:
        close_old_connections()


@login_required
def index(request, forms=None, abrir_modal='', config_form=None):
    forms = forms or {}
    return render(request, 'fucador/index.html', {
        'produtos': Produto.objects.all(),
        'emails': Destinatario.objects.all(),
        'whatsapps': ContatoWhatsApp.objects.all(),
        'produto_form': forms.get('produto') or ProdutoForm(),
        'email_form': forms.get('email') or DestinatarioForm(),
        'whatsapp_form': forms.get('whatsapp') or WhatsAppForm(),
        'abrir_modal': abrir_modal,
        'enviando': agendador.rodando('fucador'),
        'config': Configuracao.atual(),
        'config_form': config_form or ConfiguracaoForm(instance=Configuracao.atual()),
        'modelos': gemini.modelos_em_cache(),
        'modelo_padrao': gemini.GEMINI_MODEL,
        'historico': Envio.objects.all()[:30],
    })


@login_required
@require_POST
def adicionar(request, tipo):
    if tipo not in LISTAS:
        raise Http404
    _, form_cls, aba = LISTAS[tipo]
    form = form_cls(request.POST)
    if not form.is_valid():
        return index(request, forms={tipo: form}, abrir_modal=tipo)
    form.save()
    return redirect(reverse('fucador') + '#' + aba)


@login_required
@require_POST
def remover(request, tipo, pk):
    if tipo not in LISTAS:
        raise Http404
    model, _, aba = LISTAS[tipo]
    get_object_or_404(model, pk=pk).delete()
    return redirect(reverse('fucador') + '#' + aba)


@login_required
@require_POST
def enviar(request):
    agendador.disparar('fucador')
    return redirect(reverse('fucador') + '#sec-envio')


@login_required
@require_POST
def configuracao(request):
    config = Configuracao.atual()
    if 'restaurar' in request.POST:
        config.prompt, config.modelo = ofertas.PROMPT_PADRAO, gemini.GEMINI_MODEL
        config.save()
    else:
        form = ConfiguracaoForm(request.POST, instance=config)
        if not form.is_valid():
            return index(request, config_form=form)
        form.save()
    return redirect(reverse('fucador') + '#sec-gemini')
