from django.apps import AppConfig


class FucadorConfig(AppConfig):
    name = "fucador"

    def ready(self):
        from main import agendador

        from . import views

        agendador.registrar("fucador", views.tarefa)
