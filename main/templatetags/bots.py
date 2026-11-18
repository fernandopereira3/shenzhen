from django import template

from main.views import BOTS

register = template.Library()


@register.inclusion_tag('main/_painel_bot.html', takes_context=True)
def painel_bot(context):
    """Logo, nome e descrição do bot da página atual (pelo nome da rota, ex.: 'braga')."""
    rota = context['request'].resolver_match.url_name
    return {'bot': next((b for b in BOTS if b['url'] == rota), None)}
