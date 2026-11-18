from django.contrib.auth import login
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.shortcuts import redirect, render


def novo_usuario(request):
    if request.method != "POST":
        return redirect("login")
    signup_form = UserCreationForm(request.POST)
    if signup_form.is_valid():
        login(request, signup_form.save())
        return redirect("main")
    # Volta pro login com o modal aberto mostrando os erros.
    return render(
        request,
        "login/login.html",
        {
            "form": AuthenticationForm(),
            "signup_form": signup_form,
            "abrir_modal": True,
        },
    )
