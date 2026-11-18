from django import forms

from .models import Agendamento


class AgendamentoForm(forms.ModelForm):
    class Meta:
        model = Agendamento
        fields = ['tipo', 'horario', 'intervalo']
        labels = {'tipo': 'Quando', 'horario': 'Horário', 'intervalo': 'Minutos'}
        widgets = {'horario': forms.TimeInput(attrs={'type': 'time'}, format='%H:%M')}

    def clean(self):
        dados = super().clean()
        if dados.get('tipo') == Agendamento.DIARIO:
            if not dados.get('horario'):
                self.add_error('horario', 'Informe o horário.')
            dados['intervalo'] = None
        elif dados.get('tipo') == Agendamento.INTERVALO:
            if not dados.get('intervalo'):
                self.add_error('intervalo', 'Informe de quantos em quantos minutos.')
            dados['horario'] = None
        return dados
