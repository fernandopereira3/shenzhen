from django.db import models


class Conta(models.Model):
    """Conta do EAD que o bot usa. Fica no db_braga.sqlite3 (ver shenzhen/routers.py)."""

    nome = models.CharField(
        max_length=100, blank=True
    )  # só pra identificar a pessoa; não é usado no login
    cpf = models.CharField(max_length=14, unique=True)
    # shortcut: senha em texto puro porque o bot precisa dela pra logar no EAD; cifrar depois
    senha = models.CharField(max_length=128)

    class Meta:
        ordering = ["cpf"]

    def __str__(self):
        return self.cpf


class Execucao(models.Model):
    """Uma execução do bot (pelo botão ou pela agenda)."""

    RODANDO, CONCLUIDA, CANCELADA, FALHOU = (
        "rodando",
        "concluida",
        "cancelada",
        "falhou",
    )
    STATUS = [
        (RODANDO, "Rodando"),
        (CONCLUIDA, "Concluída"),
        (CANCELADA, "Cancelada"),
        (FALHOU, "Falhou"),
    ]

    inicio = models.DateTimeField(auto_now_add=True)
    fim = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default=RODANDO)

    class Meta:
        ordering = ["-inicio"]

    def __str__(self):
        return f"{self.inicio:%d/%m/%Y %H:%M} · {self.get_status_display()}"


class Incompleto(models.Model):
    """Curso incompleto de uma conta numa execução: o que o original gravava no incompletos.log."""

    execucao = models.ForeignKey(
        Execucao, on_delete=models.CASCADE, related_name="incompletos"
    )
    cpf = models.CharField(max_length=14)
    curso_id = models.CharField(max_length=20)
    nome = models.CharField(max_length=300)
    url = models.URLField(max_length=300)

    class Meta:
        ordering = ["cpf", "nome"]

    def __str__(self):
        return f"{self.cpf} · [{self.curso_id}] {self.nome}"
