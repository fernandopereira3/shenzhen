from django import forms

from .models import Configuracao, Destinatario


class DestinatarioForm(forms.ModelForm):
    class Meta:
        model = Destinatario
        fields = ['nome', 'email']
        labels = {'nome': 'Nome', 'email': 'E-mail'}


class PromptForm(forms.ModelForm):
    class Meta:
        model = Configuracao
        fields = ['modelo', 'prompt']
        labels = {'modelo': 'Modelo', 'prompt': 'Prompt'}
        widgets = {
            # datalist: sugere os modelos da API, mas aceita digitar se a lista não carregar
            'modelo': forms.TextInput(attrs={'list': 'modelos-gemini', 'autocomplete': 'off'}),
            'prompt': forms.Textarea(attrs={'rows': 12}),
        }
