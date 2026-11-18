from django.db import models


class Destinatario(models.Model):
    """Quem recebe o Cronjob News (era a lista DESTINATARIOS do original). Fica no db_news.sqlite3."""

    nome = models.CharField(max_length=100, blank=True)
    email = models.EmailField(unique=True)

    class Meta:
        ordering = ["nome", "email"]

    def __str__(self):
        return self.email


class Envio(models.Model):
    """Histórico: cada vez que a newsletter foi montada e enviada (pelo botão ou pela agenda)."""

    ENVIANDO, ENVIADO, FALHOU = "enviando", "enviado", "falhou"
    STATUS = [(ENVIANDO, "Enviando"), (ENVIADO, "Enviado"), (FALHOU, "Falhou")]

    inicio = models.DateTimeField(auto_now_add=True)
    fim = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default=ENVIANDO)
    destinatarios = models.PositiveIntegerField(default=0)
    erro = models.TextField(blank=True)

    class Meta:
        ordering = ["-inicio"]


class Configuracao(models.Model):
    """Configuração única do Cronjob News (sempre pk=1)."""

    prompt = models.TextField()
    modelo = models.CharField(
        max_length=100, default="gemini-3.8-flash"
    )  # mesmo GEMINI_MODEL do cronjob

    @classmethod
    def atual(cls):
        from .cronjob import GEMINI_MODEL, PROMPT_PADRAO

        return cls.objects.get_or_create(
            pk=1, defaults={"prompt": PROMPT_PADRAO, "modelo": GEMINI_MODEL}
        )[0]
