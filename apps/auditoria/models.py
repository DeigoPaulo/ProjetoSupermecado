from django.conf import settings
from django.db import models


class LogAuditoria(models.Model):
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)
    modulo = models.CharField(max_length=80)
    acao = models.CharField(max_length=80)
    descricao = models.TextField(blank=True)
    objeto_tipo = models.CharField(max_length=120, blank=True)
    objeto_id = models.CharField(max_length=80, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em"]

    def __str__(self):
        return f"{self.modulo}:{self.acao}"

# Create your models here.
