from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="news_"),
    path("adicionar/", views.adicionar, name="news_adicionar"),
    path("remover/<int:pk>/", views.remover, name="news_remover"),
    path("enviar/", views.enviar, name="news_enviar"),
    path("prompt/", views.prompt, name="news_prompt"),
]
