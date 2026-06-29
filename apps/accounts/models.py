from django.conf import settings
from django.db import models


class TipoPerfil(models.TextChoices):
    ADMINISTRADOR = "ADMINISTRADOR", "Administrador"
    GERENTE = "GERENTE", "Gerente"
    OPERADOR_CAIXA = "OPERADOR_CAIXA", "Operador de caixa"
    ESTOQUISTA = "ESTOQUISTA", "Estoquista"
    COMPRAS = "COMPRAS", "Compras"
    FINANCEIRO = "FINANCEIRO", "Financeiro"


class PerfilUsuario(models.Model):
    usuario = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="perfil_supermercado")
    filial = models.ForeignKey("empresas.Filial", on_delete=models.PROTECT, null=True, blank=True)
    tipo = models.CharField(max_length=30, choices=TipoPerfil.choices, default=TipoPerfil.OPERADOR_CAIXA)
    telefone = models.CharField(max_length=30, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.usuario} - {self.tipo}"

# Create your models here.
