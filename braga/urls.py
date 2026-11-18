from django.urls import path

from . import views

urlpatterns = [
    path('', views.index, name='braga'),
    path('adicionar/', views.adicionar, name='braga_adicionar'),
    path('remover/', views.remover, name='braga_remover'),
    path('rodar/', views.rodar, name='braga_rodar'),
    path('cancelar/', views.cancelar, name='braga_cancelar'),
    path('status/', views.status, name='braga_status'),
]
