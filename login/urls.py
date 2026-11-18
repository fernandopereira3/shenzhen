from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path

from . import views

urlpatterns = [
    path(
        "",
        LoginView.as_view(
            template_name="login/login.html",
            redirect_authenticated_user=True,
            extra_context={"signup_form": UserCreationForm()},
        ),
        name="login",
    ),
    path("sair/", LogoutView.as_view(), name="logout"),
    path("novo/", views.novo_usuario, name="novo_usuario"),
]
