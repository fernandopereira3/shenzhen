from django.db import models


class Produto(models.Model):
    """Cada produto vira um e-mail/WhatsApp de ofertas (era a lista PRODUTOS do original)."""

    nome = models.CharField(max_length=200, unique=True)

    class Meta:
        ordering = ["nome"]

    def __str__(self):
        return self.nome


class Destinatario(models.Model):
    """Quem recebe por e-mail (era DESTINATARIOS do original)."""

    nome = models.CharField(max_length=100, blank=True)
    email = models.EmailField(unique=True)

    class Meta:
        ordering = ["nome", "email"]

    def __str__(self):
        return self.email


class ContatoWhatsApp(models.Model):
    """Quem recebe por WhatsApp via CallMeBot (era DESTINATARIOS_WPP do original).
    A pessoa manda "I allow callmebot to send me messages" para +34 644 71 81 99 e recebe a apikey."""

    nome = models.CharField(max_length=100, blank=True)
    telefone = models.CharField(
        "telefone", max_length=20, unique=True
    )  # DDI + DDD + número, só dígitos
    apikey = models.CharField(max_length=50)

    class Meta:
        ordering = ["nome", "telefone"]

    def __str__(self):
        return self.telefone


class Configuracao(models.Model):
    """Configuração única do Fuçador (sempre pk=1)."""

    prompt = models.TextField()
    modelo = models.CharField(
        max_length=100, default="gemini-3.8-flash"
    )  # mesmo GEMINI_MODEL de main.gemini
    por_email = models.BooleanField("enviar por e-mail", default=True)
    por_whatsapp = models.BooleanField("enviar por WhatsApp", default=True)

    @classmethod
    def atual(cls):
        from main.gemini import GEMINI_MODEL

        from .ofertas import PROMPT_PADRAO

        return cls.objects.get_or_create(
            pk=1, defaults={"prompt": PROMPT_PADRAO, "modelo": GEMINI_MODEL}
        )[0]


class Envio(models.Model):
    """Histórico: cada produto pesquisado e enviado (pelo botão ou pela agenda)."""

    ENVIANDO, ENVIADO, FALHOU = "enviando", "enviado", "falhou"
    STATUS = [(ENVIANDO, "Enviando"), (ENVIADO, "Enviado"), (FALHOU, "Falhou")]

    inicio = models.DateTimeField(auto_now_add=True)
    fim = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default=ENVIANDO)
    produto = models.CharField(max_length=200)
    emails = models.PositiveIntegerField(default=0)
    whatsapps = models.PositiveIntegerField(default=0)
    erro = models.TextField(blank=True)

    class Meta:
        ordering = ["-inicio"]
