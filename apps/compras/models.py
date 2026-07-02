from django.conf import settings
from django.db import models


class StatusEntradaCompra(models.TextChoices):
    RASCUNHO = "RASCUNHO", "Rascunho"
    FINALIZADA = "FINALIZADA", "Finalizada"
    CANCELADA = "CANCELADA", "Cancelada"


class EntradaCompra(models.Model):
    fornecedor = models.ForeignKey("fornecedores.Fornecedor", on_delete=models.PROTECT, related_name="entradas_compra")
    filial = models.ForeignKey("empresas.Filial", on_delete=models.PROTECT, related_name="entradas_compra")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="entradas_compra")
    numero_documento = models.CharField(max_length=80, blank=True)
    data_emissao = models.DateField(null=True, blank=True)
    vencimento_financeiro = models.DateField(null=True, blank=True)
    gerar_conta_financeira = models.BooleanField(default=True)
    data_recebimento = models.DateTimeField(auto_now_add=True)
    observacoes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=StatusEntradaCompra.choices, default=StatusEntradaCompra.RASCUNHO)
    total_produtos = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-data_recebimento"]

    def __str__(self):
        return f"Entrada {self.id} - {self.fornecedor}"


class ItemEntradaCompra(models.Model):
    entrada = models.ForeignKey(EntradaCompra, on_delete=models.CASCADE, related_name="itens")
    produto = models.ForeignKey("produtos.Produto", on_delete=models.PROTECT, related_name="itens_compra")
    quantidade = models.DecimalField(max_digits=12, decimal_places=3)
    custo_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    atualizar_preco_custo = models.BooleanField(default=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.quantidade} x {self.produto}"

# Create your models here.
