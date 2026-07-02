from django.db import models


class Empresa(models.Model):
    razao_social = models.CharField(max_length=255)
    nome_fantasia = models.CharField(max_length=255)
    cnpj = models.CharField(max_length=18, unique=True)
    telefone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    endereco = models.TextField(blank=True)
    regime_tributario = models.CharField(max_length=80, blank=True)
    logo = models.ImageField(upload_to="empresas/logos/", blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["nome_fantasia"]

    def __str__(self):
        return self.nome_fantasia


class Filial(models.Model):
    UF_CHOICES = [
        ("AC", "AC"), ("AL", "AL"), ("AP", "AP"), ("AM", "AM"), ("BA", "BA"), ("CE", "CE"), ("DF", "DF"),
        ("ES", "ES"), ("GO", "GO"), ("MA", "MA"), ("MT", "MT"), ("MS", "MS"), ("MG", "MG"), ("PA", "PA"),
        ("PB", "PB"), ("PR", "PR"), ("PE", "PE"), ("PI", "PI"), ("RJ", "RJ"), ("RN", "RN"), ("RS", "RS"),
        ("RO", "RO"), ("RR", "RR"), ("SC", "SC"), ("SP", "SP"), ("SE", "SE"), ("TO", "TO"),
    ]
    empresa = models.ForeignKey(Empresa, on_delete=models.PROTECT, related_name="filiais")
    nome = models.CharField(max_length=255)
    cnpj = models.CharField(max_length=18, blank=True)
    telefone = models.CharField(max_length=30, blank=True)
    endereco = models.TextField(blank=True)
    municipio = models.CharField(max_length=120, blank=True)
    uf = models.CharField(max_length=2, choices=UF_CHOICES, blank=True)
    codigo_municipio_ibge = models.CharField("Codigo municipio IBGE", max_length=7, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["empresa__nome_fantasia", "nome"]
        unique_together = ["empresa", "nome"]

    def __str__(self):
        return f"{self.empresa} - {self.nome}"

# Create your models here.
