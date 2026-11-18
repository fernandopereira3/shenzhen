from django import forms
from django.core.validators import RegexValidator

from .models import Conta


class ContaForm(forms.Form):
    nome = forms.CharField(label="Nome", max_length=100, required=False)
    cpf = forms.CharField(
        label="CPF",
        max_length=14,
        validators=[RegexValidator(r"^[\d.\-]+$", "Use só números, pontos e traço.")],
    )
    senha = forms.CharField(
        label="Senha", widget=forms.PasswordInput, strip=False, required=False
    )

    def clean(self):
        dados = super().clean()
        cpf = dados.get("cpf")
        # senha só é obrigatória pra CPF novo: em CPF existente, em branco = manter a atual
        if (
            cpf
            and not dados.get("senha")
            and not Conta.objects.filter(cpf=cpf).exists()
        ):
            self.add_error("senha", "Informe a senha (CPF novo).")
        return dados
