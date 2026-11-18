import threading

from django.contrib.auth.decorators import login_required
from django.db import close_old_connections
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import bot
from .forms import ContaForm
from .models import Conta, Execucao, Incompleto

# shortcut: thread dentro do processo do Django; some se o servidor reiniciar
# e não funciona com vários workers. Trocar por Celery/RQ se for pra produção.
_execucao = None
_cancelar = threading.Event()


def _rodando():
    return _execucao is not None and _execucao.is_alive()


def _contas():
    return dict(Conta.objects.values_list("cpf", "senha"))


def _executar(users, cancelar):
    """Roda o bot e guarda no histórico o status e os cursos incompletos de cada conta."""
    execucao = Execucao.objects.create()
    status, resultados = Execucao.FALHOU, {}
    try:
        status, resultados = bot.run(users, cancelar)
    finally:
        execucao.status = status
        execucao.fim = timezone.now()
        execucao.save()
        Incompleto.objects.bulk_create(
            Incompleto(execucao=execucao, cpf=cpf, curso_id=cid, nome=nome, url=url)
            for cpf, cursos in resultados.items()
            for cid, nome, url in cursos
        )
        close_old_connections()  # thread própria: fecha a conexão com o banco


def iniciar():
    """Inicia o bot em segundo plano. Devolve False se não há contas ou já está rodando."""
    global _execucao, _cancelar
    users = _contas()
    if not users or _rodando():
        return False
    _cancelar = threading.Event()
    _execucao = threading.Thread(target=_executar, args=(users, _cancelar), daemon=True)
    _execucao.start()
    return True


def _ler_log():
    return bot.LOG_FILE.read_text(encoding="utf-8") if bot.LOG_FILE.exists() else ""


@login_required
def index(request, form=None):
    log = _ler_log()
    return render(
        request,
        "braga/index.html",
        {
            "contas": Conta.objects.all(),
            "form": form or ContaForm(),
            "rodando": _rodando(),
            "cancelando": _rodando() and _cancelar.is_set(),
            "log": log,
            "historico": Execucao.objects.prefetch_related("incompletos")[:30],
            "abrir_modal": form is not None,  # erro ao adicionar: reabre o modal
        },
    )


@login_required
@require_POST
def adicionar(request):
    form = ContaForm(request.POST)
    if not form.is_valid():
        return index(request, form)
    # em CPF existente, campo em branco mantém o valor atual
    dados = {
        campo: form.cleaned_data[campo]
        for campo in ("nome", "senha")
        if form.cleaned_data[campo]
    }
    Conta.objects.update_or_create(cpf=form.cleaned_data["cpf"], defaults=dados)
    return redirect("braga")


@login_required
@require_POST
def remover(request):
    Conta.objects.filter(cpf=request.POST.get("cpf")).delete()
    return redirect("braga")


@login_required
@require_POST
def rodar(request):
    iniciar()
    return redirect(reverse("braga") + "#sec-execucao")


@login_required
@require_POST
def cancelar(request):
    if _rodando():
        _cancelar.set()
    return redirect(reverse("braga") + "#sec-execucao")


@login_required
def status(request):
    """Lido pela página a cada 2s enquanto o bot roda."""
    return JsonResponse(
        {
            "log": _ler_log(),
            "rodando": _rodando(),
            "cancelando": _rodando() and _cancelar.is_set(),
        }
    )
