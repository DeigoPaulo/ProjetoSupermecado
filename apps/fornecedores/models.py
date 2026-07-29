from django.db import models


class Fornecedor(models.Model):
    empresa = models.ForeignKey(
        "empresas.Empresa",
        on_delete=models.PROTECT,
        related_name="fornecedores",
        null=True,
        blank=True,
    )
    razao_social = models.CharField(max_length=255)
    nome_fantasia = models.CharField(max_length=255, blank=True)
    cnpj = models.CharField(max_length=18, blank=True)
    telefone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    endereco = models.TextField(blank=True)
    condicao_pagamento = models.CharField(max_length=120, blank=True)
    prazo_entrega_dias = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["empresa_id", "razao_social"]
        indexes = [
            models.Index(fields=["empresa", "razao_social"], name="fornec_empresa_razao_idx"),
        ]

    def __str__(self):
        return self.nome_fantasia or self.razao_social