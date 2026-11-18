"""Agendador do projeto: cada bot registra sua tarefa e os horários ficam em Agendamento."""
import threading
import time
import traceback

from django.db import close_old_connections
from django.utils import timezone

_tarefas = {}   # bot -> função que roda o bot
_threads = {}   # bot -> thread da execução atual


def registrar(bot, funcao):
    """Chamado no AppConfig.ready() de cada bot."""
    _tarefas[bot] = funcao


def registrado(bot):
    return bot in _tarefas


def _executar(bot, funcao):
    try:
        funcao()
    except Exception:
        traceback.print_exc()
    finally:
        close_old_connections()


def rodando(bot):
    atual = _threads.get(bot)
    return bool(atual and atual.is_alive())


def disparar(bot):
    """Roda a tarefa do bot em segundo plano; não sobrepõe uma execução em andamento."""
    funcao = _tarefas.get(bot)
    if funcao is None or rodando(bot):
        return False
    _threads[bot] = threading.Thread(target=_executar, args=(bot, funcao), daemon=True,
                                     name=f'bot-{bot}')
    _threads[bot].start()
    return True


def checar(agora=None):
    from .models import Agendamento
    close_old_connections()
    agora = agora or timezone.localtime()
    for ag in Agendamento.objects.filter(ativo=True):
        if registrado(ag.bot) and ag.deve_rodar(agora):
            ag.ultima_execucao = agora
            ag.save(update_fields=['ultima_execucao'])
            disparar(ag.bot)


def loop():
    # shortcut: roda no processo do runserver (ver main/apps.py); com vários workers
    # dispararia em cada um. Trocar por cron/Celery beat se for pra produção.
    while True:
        time.sleep(20)  # espera antes: dá tempo de todos os apps registrarem suas tarefas
        try:
            checar()
        except Exception:
            traceback.print_exc()
