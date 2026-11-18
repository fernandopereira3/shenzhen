from django import forms
from django.core.validators import RegexValidator

from .models import Configuracao, ContatoWhatsApp, Destinatario, Produto


class ProdutoForm(forms.ModelForm):
    class Meta:
        model = Produto
        fields = ["nome"]
        labels = {"nome": "Produto"}


class DestinatarioForm(forms.ModelForm):
    class Meta:
        model = Destinatario
        fields = ["nome", "email"]
        labels = {"nome": "Nome", "email": "E-mail"}


class WhatsAppForm(forms.ModelForm):
    telefone = forms.CharField(
        label="Telefone",
        max_length=20,
        validators=[
            RegexValidator(
                r"^\d{10,15}$", "Só números, com DDI e DDD (ex.: 5518999999999)."
            )
        ],
    )

    class Meta:
        model = ContatoWhatsApp
        fields = ["nome", "telefone", "apikey"]
        labels = {"nome": "Nome", "apikey": "Apikey do CallMeBot"}


class ConfiguracaoForm(forms.ModelForm):
    class Meta:
        model = Configuracao
        fields = ["modelo", "prompt", "por_email", "por_whatsapp"]
        labels = {"modelo": "Modelo", "prompt": "Prompt"}
        widgets = {
            # datalist: sugere os modelos da API, mas aceita digitar se a lista não carregar
            "modelo": forms.TextInput(
                attrs={"list": "modelos-gemini", "autocomplete": "off"}
            ),
            "prompt": forms.Textarea(attrs={"rows": 14}),
        }
