from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="fucador"),
    path("<str:tipo>/adicionar/", views.adicionar, name="fucador_adicionar"),
    path("<str:tipo>/remover/<int:pk>/", views.remover, name="fucador_remover"),
    path("enviar/", views.enviar, name="fucador_enviar"),
    path("configuracao/", views.configuracao, name="fucador_configuracao"),
]
