from django.db import models


class Cliente(models.Model):
    empresa = models.ForeignKey(
        "empresas.Empresa",
        on_delete=models.PROTECT,
        related_name="clientes",
        null=True,
        blank=True,
    )
    nome = models.CharField(max_length=255)
    cpf_cnpj = models.CharField(max_length=18, blank=True)
    telefone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    endereco = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["empresa_id", "nome"]
        indexes = [models.Index(fields=["empresa", "nome"], name="clientes_empresa_nome_idx" )]

    def __str__(self):
        return self.nome

# Create your models here.
