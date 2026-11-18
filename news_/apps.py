from django.apps import AppConfig


class NewsConfig(AppConfig):
    name = "news_"

    def ready(self):
        from main import agendador

        from . import views

        agendador.registrar("news_", views.tarefa)
