from datetime import timedelta

from django.core.validators import MinValueValidator
from django.db import models


class Agendamento(models.Model):
    DIARIO = "diario"
    INTERVALO = "intervalo"
    TIPOS = [(DIARIO, "Todo dia às"), (INTERVALO, "A cada N minutos")]
    JANELA = timedelta(
        minutes=2
    )  # tolerância pro agendador (que olha a cada 20s) não perder o horário

    bot = models.CharField(max_length=30)  # mesmo nome da rota da página do bot
    tipo = models.CharField(max_length=10, choices=TIPOS, default=DIARIO)
    horario = models.TimeField(null=True, blank=True)
    intervalo = models.PositiveIntegerField(
        "minutos", null=True, blank=True, validators=[MinValueValidator(1)]
    )
    ativo = models.BooleanField(default=True)
    ultima_execucao = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["tipo", "horario", "intervalo"]

    def __str__(self):
        if self.tipo == self.DIARIO:
            return f"Todo dia às {self.horario:%H:%M}"
        return f"A cada {self.intervalo} min"

    def _alvo_de_hoje(self, agora):
        return agora.replace(
            hour=self.horario.hour, minute=self.horario.minute, second=0, microsecond=0
        )

    def deve_rodar(self, agora):
        ultima = self.ultima_execucao
        if self.tipo == self.DIARIO:
            alvo = self._alvo_de_hoje(agora)
            return alvo <= agora < alvo + self.JANELA and (
                ultima is None or ultima < alvo
            )
        return ultima is None or agora >= ultima + timedelta(minutes=self.intervalo)

    def proxima(self, agora):
        if self.tipo == self.DIARIO:
            alvo = self._alvo_de_hoje(agora)
            ja_foi = alvo + self.JANELA <= agora or (
                self.ultima_execucao and self.ultima_execucao >= alvo
            )
            return alvo + timedelta(days=1) if ja_foi else alvo
        if self.ultima_execucao is None:
            return agora
        return max(agora, self.ultima_execucao + timedelta(minutes=self.intervalo))
