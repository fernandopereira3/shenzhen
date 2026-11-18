from django.apps import AppConfig


class BragaConfig(AppConfig):
    name = "braga"

    def ready(self):
        from main import agendador

        from . import views

        agendador.registrar("braga", views.iniciar)
