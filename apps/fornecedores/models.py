import re

from django.core.exceptions import ValidationError
from django.db import models


class IndicadorInscricaoEstadual(models.TextChoices):
    CONTRIBUINTE = "1", "Contribuinte de ICMS"
    ISENTO = "2", "Contribuinte isento de inscrição"
    NAO_CONTRIBUINTE = "9", "Não contribuinte"


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
    indicador_ie = models.CharField(
        "Indicador de IE",
        max_length=1,
        choices=IndicadorInscricaoEstadual.choices,
        blank=True,
        default="",
    )
    inscricao_estadual = models.CharField("Inscrição estadual", max_length=20, blank=True)
    logradouro = models.CharField("Logradouro fiscal", max_length=120, blank=True)
    numero = models.CharField("Número fiscal", max_length=60, blank=True)
    complemento = models.CharField("Complemento fiscal", max_length=60, blank=True)
    bairro = models.CharField("Bairro fiscal", max_length=60, blank=True)
    codigo_municipio_ibge = models.CharField("Código IBGE do município", max_length=7, blank=True)
    municipio = models.CharField("Município fiscal", max_length=60, blank=True)
    uf = models.CharField("UF fiscal", max_length=2, blank=True)
    cep = models.CharField("CEP fiscal", max_length=9, blank=True)
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

    def clean(self):
        super().clean()
        erros = {}
        indicador = (self.indicador_ie or "").strip()
        inscricao_estadual = (self.inscricao_estadual or "").strip()

        if indicador == IndicadorInscricaoEstadual.CONTRIBUINTE and not inscricao_estadual:
            erros["inscricao_estadual"] = "Informe a inscrição estadual do contribuinte."
        if indicador != IndicadorInscricaoEstadual.CONTRIBUINTE and inscricao_estadual:
            erros["inscricao_estadual"] = "A inscrição estadual só deve ser informada para contribuinte de ICMS."

        endereco_fiscal_iniciado = any(
            str(valor or "").strip()
            for valor in (
                self.logradouro,
                self.numero,
                self.bairro,
                self.codigo_municipio_ibge,
                self.municipio,
                self.uf,
                self.cep,
            )
        )
        if endereco_fiscal_iniciado:
            obrigatorios = {
                "logradouro": self.logradouro,
                "numero": self.numero,
                "bairro": self.bairro,
                "codigo_municipio_ibge": self.codigo_municipio_ibge,
                "municipio": self.municipio,
                "uf": self.uf,
                "cep": self.cep,
            }
            for campo, valor in obrigatorios.items():
                if not str(valor or "").strip():
                    erros[campo] = "Complete o endereço fiscal estruturado."
        if self.codigo_municipio_ibge and not re.fullmatch(r"\d{7}", self.codigo_municipio_ibge.strip()):
            erros["codigo_municipio_ibge"] = "Informe 7 dígitos."
        if self.uf and not re.fullmatch(r"[A-Za-z]{2}", self.uf.strip()):
            erros["uf"] = "Informe a sigla da UF com 2 letras."
        if self.cep and not re.fullmatch(r"\d{5}-?\d{3}", self.cep.strip()):
            erros["cep"] = "Informe o CEP com 8 dígitos."
        if erros:
            raise ValidationError(erros)
