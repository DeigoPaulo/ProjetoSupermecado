from django.conf import settings
from django.db import models


class StatusVenda(models.TextChoices):
    ABERTA = "ABERTA", "Aberta"
    FINALIZADA = "FINALIZADA", "Finalizada"
    CANCELADA = "CANCELADA", "Cancelada"


class FormaPagamento(models.Model):
    nome = models.CharField(max_length=100)
    tipo = models.CharField(max_length=50)
    ativo = models.BooleanField(default=True)
    permite_troco = models.BooleanField(default=False)
    exige_autorizacao = models.BooleanField(default=False)

    class Meta:
        ordering = ["nome"]

    def __str__(self):
        return self.nome


class Venda(models.Model):
    filial = models.ForeignKey("empresas.Filial", on_delete=models.PROTECT, related_name="vendas")
    caixa = models.ForeignKey("pdv.Caixa", on_delete=models.PROTECT, related_name="vendas")
    cliente = models.ForeignKey("clientes.Cliente", on_delete=models.PROTECT, related_name="vendas", null=True, blank=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="vendas")
    total_bruto = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    desconto = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_liquido = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=StatusVenda.choices, default=StatusVenda.ABERTA)
    data = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-data"]

    def __str__(self):
        return f"Venda {self.id} - {self.total_liquido}"


class ItemVenda(models.Model):
    venda = models.ForeignKey(Venda, on_delete=models.PROTECT, related_name="itens")
    produto = models.ForeignKey("produtos.Produto", on_delete=models.PROTECT)
    quantidade = models.DecimalField(max_digits=12, decimal_places=3)
    preco_unitario_venda = models.DecimalField(max_digits=10, decimal_places=2)
    desconto = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    custo_unitario_no_momento = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    def __str__(self):
        return f"{self.quantidade} x {self.produto}"


class PagamentoVenda(models.Model):
    venda = models.ForeignKey(Venda, on_delete=models.PROTECT, related_name="pagamentos")
    forma_pagamento = models.ForeignKey(FormaPagamento, on_delete=models.PROTECT)
    valor = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=30, default="CONFIRMADO")
    data = models.DateTimeField(auto_now_add=True)

# Create your models here.
