from django.urls import path

from . import views

urlpatterns = [
    path("<str:bot>/adicionar/", views.agenda_adicionar, name="agenda_adicionar"),
    path("<int:pk>/remover/", views.agenda_remover, name="agenda_remover"),
    path("<int:pk>/alternar/", views.agenda_alternar, name="agenda_alternar"),
]
