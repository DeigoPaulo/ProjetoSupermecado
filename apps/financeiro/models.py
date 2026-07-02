from django.conf import settings
from django.db import models
from django.utils import timezone


class TipoContaFinanceira(models.TextChoices):
    PAGAR = "PAGAR", "Conta a pagar"
    RECEBER = "RECEBER", "Conta a receber"


class StatusContaFinanceira(models.TextChoices):
    ABERTA = "ABERTA", "Aberta"
    PAGA = "PAGA", "Paga"
    CANCELADA = "CANCELADA", "Cancelada"


class CategoriaFinanceira(models.Model):
    nome = models.CharField(max_length=120, unique=True)
    tipo = models.CharField(max_length=20, choices=TipoContaFinanceira.choices)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["tipo", "nome"]

    def __str__(self):
        return self.nome


class ContaFinanceira(models.Model):
    tipo = models.CharField(max_length=20, choices=TipoContaFinanceira.choices)
    status = models.CharField(max_length=20, choices=StatusContaFinanceira.choices, default=StatusContaFinanceira.ABERTA)
    descricao = models.CharField(max_length=255)
    categoria = models.ForeignKey(CategoriaFinanceira, on_delete=models.PROTECT, null=True, blank=True, related_name="contas")
    filial = models.ForeignKey("empresas.Filial", on_delete=models.PROTECT, related_name="contas_financeiras")
    fornecedor = models.ForeignKey("fornecedores.Fornecedor", on_delete=models.PROTECT, null=True, blank=True, related_name="contas_pagar")
    cliente = models.ForeignKey("clientes.Cliente", on_delete=models.PROTECT, null=True, blank=True, related_name="contas_receber")
    venda = models.ForeignKey("vendas.Venda", on_delete=models.PROTECT, null=True, blank=True, related_name="contas_financeiras")
    entrada_compra = models.ForeignKey("compras.EntradaCompra", on_delete=models.PROTECT, null=True, blank=True, related_name="contas_financeiras")
    valor = models.DecimalField(max_digits=12, decimal_places=2)
    vencimento = models.DateField()
    data_pagamento = models.DateField(null=True, blank=True)
    valor_pago = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    forma_pagamento = models.CharField(max_length=80, blank=True)
    observacoes = models.TextField(blank=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="contas_financeiras")
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["status", "vencimento", "descricao"]

    @property
    def esta_vencida(self):
        return self.status == StatusContaFinanceira.ABERTA and self.vencimento < timezone.localdate()

    @property
    def saldo(self):
        return self.valor - (self.valor_pago or 0)

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.descricao}"
