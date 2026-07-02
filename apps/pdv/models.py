from django.conf import settings
from django.db import models


class StatusCaixa(models.TextChoices):
    ABERTO = "ABERTO", "Aberto"
    FECHADO = "FECHADO", "Fechado"
    CONFERIDO = "CONFERIDO", "Conferido"
    CANCELADO = "CANCELADO", "Cancelado"


class StatusAcessoPdvNuvem(models.TextChoices):
    PENDENTE = "PENDENTE", "Pendente"
    APROVADO = "APROVADO", "Aprovado"
    RECUSADO = "RECUSADO", "Recusado"
    EXPIRADO = "EXPIRADO", "Expirado"


class Caixa(models.Model):
    filial = models.ForeignKey("empresas.Filial", on_delete=models.PROTECT, related_name="caixas")
    usuario_abertura = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="caixas_abertos")
    data_abertura = models.DateTimeField(auto_now_add=True)
    valor_inicial = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    usuario_fechamento = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="caixas_fechados", null=True, blank=True)
    data_fechamento = models.DateTimeField(null=True, blank=True)
    valor_final = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    usuario_conferencia = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="caixas_conferidos", null=True, blank=True)
    data_conferencia = models.DateTimeField(null=True, blank=True)
    valor_conferido = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    observacao_conferencia = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=StatusCaixa.choices, default=StatusCaixa.ABERTO)

    class Meta:
        ordering = ["-data_abertura"]

    def __str__(self):
        return f"Caixa {self.id} - {self.filial} - {self.status}"


class Sangria(models.Model):
    caixa = models.ForeignKey(Caixa, on_delete=models.PROTECT, related_name="sangrias")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    valor = models.DecimalField(max_digits=12, decimal_places=2)
    motivo = models.CharField(max_length=255)
    data = models.DateTimeField(auto_now_add=True)


class Suprimento(models.Model):
    caixa = models.ForeignKey(Caixa, on_delete=models.PROTECT, related_name="suprimentos")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    valor = models.DecimalField(max_digits=12, decimal_places=2)
    motivo = models.CharField(max_length=255)
    data = models.DateTimeField(auto_now_add=True)


class AcessoPdvNuvem(models.Model):
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="solicitacoes_pdv_nuvem")
    filial = models.ForeignKey("empresas.Filial", on_delete=models.PROTECT, related_name="solicitacoes_pdv_nuvem", null=True, blank=True)
    status = models.CharField(max_length=20, choices=StatusAcessoPdvNuvem.choices, default=StatusAcessoPdvNuvem.PENDENTE)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    justificativa = models.CharField(max_length=255, blank=True)
    decidido_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="decisoes_pdv_nuvem", null=True, blank=True)
    decidido_em = models.DateTimeField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-criado_em"]
        indexes = [
            models.Index(fields=["usuario", "status"]),
            models.Index(fields=["filial", "status"]),
        ]

    def __str__(self):
        return f"Acesso PDV nuvem {self.usuario} - {self.status}"

# Create your models here.
