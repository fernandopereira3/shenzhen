"""Envio de e-mail compartilhado pelos bots (Gmail configurado em MAILERS no settings)."""

from django.conf import settings
from django.core.mail import EmailMultiAlternatives


class _EmailComImagens(EmailMultiAlternatives):
    """Embute as imagens dentro do HTML (cid:nome): aparecem sem depender de site."""

    def __init__(self, *args, imagens=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.imagens = imagens or {}

    def message(self, *args, **kwargs):
        msg = super().message(*args, **kwargs)
        html = msg.get_body(("html",))
        if html is not None:
            for cid, dados in self.imagens.items():
                html.add_related(dados, "image", "png", cid=f"<{cid}>")
        return msg


def enviar_email(assunto, texto, html=None, para=(), imagens=None):
    """Envia do DEFAULT_FROM_EMAIL pra ele mesmo, com `para` em cópia oculta
    (um destinatário não vê o e-mail dos outros). `imagens` = {cid: bytes do PNG},
    usadas no HTML como <img src="cid:cid">."""
    remetente = settings.DEFAULT_FROM_EMAIL
    msg = _EmailComImagens(
        assunto, texto, remetente, [remetente], bcc=list(para), imagens=imagens
    )
    if html:
        msg.attach_alternative(html, "text/html")
    msg.send()
