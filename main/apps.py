import os
import sys
import threading

from django.apps import AppConfig


class MainConfig(AppConfig):
    name = 'main'

    def ready(self):
        # Só no processo que atende o runserver: o autoreload cria um processo pai
        # (sem RUN_MAIN) e testes/migrate não devem disparar bots.
        servidor = 'runserver' in sys.argv and (
            os.environ.get('RUN_MAIN') == 'true' or '--noreload' in sys.argv
        )
        if servidor:
            from . import agendador
            threading.Thread(target=agendador.loop, daemon=True, name='agendador').start()
