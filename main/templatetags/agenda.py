from django import template
from django.utils import timezone

from main.forms import AgendamentoForm
from main.models import Agendamento

register = template.Library()


@register.inclusion_tag("main/_agenda.html", takes_context=True)
def agenda_card(context, bot):
    """Card de agenda reaproveitado nas páginas dos bots: {% agenda_card 'braga' %}."""
    agora = timezone.localtime()
    agendamentos = list(Agendamento.objects.filter(bot=bot))
    proxima = min((a.proxima(agora) for a in agendamentos if a.ativo), default=None)
    return {
        "bot": bot,
        "agendamentos": agendamentos,
        "proxima": proxima,
        "form": AgendamentoForm(),
        "csrf_token": context.get("csrf_token"),
    }
