from django.conf import settings
from django.db import models, transaction
from django.utils import timezone


class AmbienteFiscal(models.TextChoices):
    HOMOLOGACAO = "HOMOLOGACAO", "Homologacao"
    PRODUCAO = "PRODUCAO", "Producao"


class TipoDocumentoFiscal(models.TextChoices):
    NFCE = "NFCE", "NFC-e"
    NFE = "NFE", "NF-e"


class CodigoRegimeTributario(models.TextChoices):
    SIMPLES_NACIONAL = "1", "1 - Simples Nacional"
    SIMPLES_EXCESSO_SUBLIMITE = "2", "2 - Simples Nacional, excesso de sublimite"
    REGIME_NORMAL = "3", "3 - Regime Normal"
    MEI = "4", "4 - Simples Nacional, MEI"


class StatusDocumentoFiscal(models.TextChoices):
    RASCUNHO = "RASCUNHO", "Rascunho"
    PRONTO = "PRONTO", "Pronto para transmissao"
    EMITIDO = "EMITIDO", "Emitido"
    REJEITADO = "REJEITADO", "Rejeitado"
    CONTINGENCIA = "CONTINGENCIA", "Contingencia offline"
    CANCELADO = "CANCELADO", "Cancelado"
    DENEGADO = "DENEGADO", "Denegado"
    INUTILIZADO = "INUTILIZADO", "Inutilizado"


class StatusInutilizacaoFiscal(models.TextChoices):
    PENDENTE = "PENDENTE", "Pendente"
    AUTORIZADA = "AUTORIZADA", "Autorizada"
    REJEITADA = "REJEITADA", "Rejeitada"


class ConfiguracaoFiscal(models.Model):
    filial = models.OneToOneField("empresas.Filial", on_delete=models.PROTECT, related_name="configuracao_fiscal")
    ambiente = models.CharField(max_length=20, choices=AmbienteFiscal.choices, default=AmbienteFiscal.HOMOLOGACAO)
    regime_tributario = models.CharField(max_length=80, blank=True)
    crt = models.CharField(
        "Código de Regime Tributário (CRT)",
        max_length=1,
        choices=CodigoRegimeTributario.choices,
        default=CodigoRegimeTributario.REGIME_NORMAL,
    )
    inscricao_estadual = models.CharField(max_length=30, blank=True)
    csc_id = models.CharField("ID CSC", max_length=20, blank=True)
    csc_token = models.CharField("Token CSC", max_length=255, blank=True)
    url_qrcode_nfce = models.URLField(
        "URL do QR Code NFC-e",
        max_length=500,
        blank=True,
        help_text="Endpoint oficial da SEFAZ para o QR Code, conforme a UF e o ambiente.",
    )
    url_consulta_nfce = models.URLField(
        "URL de consulta NFC-e",
        max_length=500,
        blank=True,
        help_text="Pagina oficial de consulta da chave de acesso na SEFAZ.",
    )
    certificado_nome = models.CharField(max_length=255, blank=True)
    certificado_validade = models.DateField(null=True, blank=True)
    certificado_a1_criptografado = models.BinaryField(blank=True, null=True, editable=False)
    certificado_senha_criptografada = models.BinaryField(blank=True, null=True, editable=False)
    certificado_atualizado_em = models.DateTimeField(null=True, blank=True)
    ativo = models.BooleanField(default=True)
    permite_contingencia_offline = models.BooleanField(
        "Permite contingência offline NFC-e",
        default=False,
        help_text="Habilite somente quando a UF e a situação operacional permitirem a contingência offline.",
    )
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["filial__nome"]

    def __str__(self):
        return f"{self.filial} - {self.get_ambiente_display()}"

    @property
    def certificado_configurado(self):
        return bool(self.certificado_a1_criptografado and self.certificado_senha_criptografada)

    @property
    def certificado_dias_para_vencer(self):
        if not self.certificado_validade:
            return None
        return (self.certificado_validade - timezone.localdate()).days

    @property
    def certificado_status(self):
        dias = self.certificado_dias_para_vencer
        if not self.certificado_configurado:
            return "nao_configurado"
        if dias is None:
            return "sem_validade"
        if dias < 0:
            return "vencido"
        if dias <= 30:
            return "vence_em_breve"
        return "valido"


class SerieFiscal(models.Model):
    filial = models.ForeignKey("empresas.Filial", on_delete=models.PROTECT, related_name="series_fiscais")
    tipo_documento = models.CharField(max_length=10, choices=TipoDocumentoFiscal.choices, default=TipoDocumentoFiscal.NFCE)
    serie = models.PositiveIntegerField(default=1)
    proximo_numero = models.PositiveIntegerField(default=1)
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ["filial__nome", "tipo_documento", "serie"]
        unique_together = ["filial", "tipo_documento", "serie"]

    def __str__(self):
        return f"{self.get_tipo_documento_display()} serie {self.serie} - {self.filial}"


class InutilizacaoNumeracaoFiscal(models.Model):
    filial = models.ForeignKey(
        "empresas.Filial",
        on_delete=models.PROTECT,
        related_name="inutilizacoes_numeracao_fiscal",
    )
    tipo_documento = models.CharField(max_length=10, choices=TipoDocumentoFiscal.choices)
    ambiente = models.CharField(max_length=20, choices=AmbienteFiscal.choices)
    ano = models.PositiveSmallIntegerField()
    serie = models.PositiveIntegerField()
    numero_inicial = models.PositiveIntegerField()
    numero_final = models.PositiveIntegerField()
    justificativa = models.CharField(max_length=255)
    status = models.CharField(
        max_length=20,
        choices=StatusInutilizacaoFiscal.choices,
        default=StatusInutilizacaoFiscal.PENDENTE,
    )
    protocolo = models.CharField(max_length=80, blank=True)
    mensagem_retorno = models.TextField(blank=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="inutilizacoes_numeracao_fiscal",
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-criado_em"]
        indexes = [
            models.Index(
                fields=["filial", "tipo_documento", "ano", "serie"],
                name="fiscal_inut_faixa_idx",
            ),
        ]

    def __str__(self):
        return (
            f"{self.get_tipo_documento_display()} {self.serie}/"
            f"{self.numero_inicial}-{self.numero_final} ({self.ano})"
        )


class NaturezaOperacao(models.Model):
    empresa = models.ForeignKey(
        "empresas.Empresa",
        on_delete=models.PROTECT,
        related_name="naturezas_operacao",
    )
    descricao = models.CharField(max_length=120)
    cfop = models.CharField(max_length=10, blank=True)
    tipo_documento = models.CharField(max_length=10, choices=TipoDocumentoFiscal.choices, default=TipoDocumentoFiscal.NFCE)
    movimenta_estoque = models.BooleanField(default=True)
    padrao = models.BooleanField(
        "Natureza padrão",
        default=False,
        help_text="Usada automaticamente nas emissões deste tipo de documento.",
    )
    ipi_incluso_preco = models.BooleanField(
        "IPI tributado já incluído no preço",
        default=False,
        help_text="Exige validação contábil. Mantém o total cobrado e destaca o IPI no XML.",
    )
    ipi_compoe_base_icms = models.BooleanField(
        "IPI compõe a base do ICMS",
        default=False,
        help_text="Defina conforme a operação e o destinatário.",
    )
    ipi_compoe_base_pis_cofins = models.BooleanField(
        "IPI compõe a base de PIS/COFINS",
        default=False,
        help_text="Defina conforme a orientação contábil da operação.",
    )
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ["empresa__nome_fantasia", "descricao"]
        constraints = [
            models.UniqueConstraint(
                fields=["empresa", "tipo_documento", "descricao"],
                name="fiscal_nat_empresa_tipo_descricao_uniq",
            ),
            models.UniqueConstraint(
                fields=["empresa", "tipo_documento"],
                condition=models.Q(padrao=True),
                name="fiscal_nat_empresa_tipo_padrao_uniq",
            ),
        ]

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        with transaction.atomic():
            anterior = None
            if self.pk:
                anterior = (
                    type(self).objects.select_for_update()
                    .filter(pk=self.pk)
                    .values("empresa_id", "tipo_documento", "padrao")
                    .first()
                )

            grupo = type(self).objects.select_for_update().filter(
                empresa_id=self.empresa_id,
                tipo_documento=self.tipo_documento,
            ).exclude(pk=self.pk)

            if not self.ativo:
                self.padrao = False
            elif not self.padrao and not grupo.filter(ativo=True, padrao=True).exists():
                self.padrao = True

            if self.padrao:
                grupo.filter(padrao=True).update(padrao=False)

            if update_fields is not None:
                kwargs["update_fields"] = set(update_fields) | {"padrao"}
            super().save(*args, **kwargs)

            mudou_grupo = bool(
                anterior
                and (
                    anterior["empresa_id"] != self.empresa_id
                    or anterior["tipo_documento"] != self.tipo_documento
                )
            )
            if anterior and anterior["padrao"] and (mudou_grupo or not self.ativo):
                substituta = (
                    type(self).objects.filter(
                        empresa_id=anterior["empresa_id"],
                        tipo_documento=anterior["tipo_documento"],
                        ativo=True,
                    )
                    .exclude(pk=self.pk)
                    .order_by("pk")
                    .first()
                )
                if substituta:
                    type(self).objects.filter(pk=substituta.pk).update(padrao=True)

    def __str__(self):
        return self.descricao


class DocumentoFiscal(models.Model):
    filial = models.ForeignKey("empresas.Filial", on_delete=models.PROTECT, related_name="documentos_fiscais")
    venda = models.ForeignKey("vendas.Venda", on_delete=models.PROTECT, related_name="documentos_fiscais", null=True, blank=True)
    pedido_online = models.ForeignKey("marketplace.PedidoOnline", on_delete=models.PROTECT, related_name="documentos_fiscais", null=True, blank=True)
    natureza_operacao = models.ForeignKey(NaturezaOperacao, on_delete=models.PROTECT, related_name="documentos_fiscais", null=True, blank=True)
    tipo_documento = models.CharField(max_length=10, choices=TipoDocumentoFiscal.choices, default=TipoDocumentoFiscal.NFCE)
    ambiente = models.CharField(max_length=20, choices=AmbienteFiscal.choices, default=AmbienteFiscal.HOMOLOGACAO)
    serie = models.PositiveIntegerField(default=1)
    numero = models.PositiveIntegerField(null=True, blank=True)
    chave_acesso = models.CharField(max_length=60, blank=True)
    protocolo = models.CharField(max_length=80, blank=True)
    status = models.CharField(max_length=20, choices=StatusDocumentoFiscal.choices, default=StatusDocumentoFiscal.RASCUNHO)
    valor_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    xml_conteudo = models.TextField(blank=True)
    xml_gerado_em = models.DateTimeField(null=True, blank=True)
    xml_assinado_em = models.DateTimeField(null=True, blank=True)
    certificado_serial_assinatura = models.CharField(max_length=128, blank=True)
    mensagem_retorno = models.TextField(blank=True)
    motivo_cancelamento = models.CharField(max_length=255, blank=True)
    protocolo_cancelamento = models.CharField(max_length=80, blank=True)
    cancelamento_em = models.DateTimeField(null=True, blank=True)
    mensagem_cancelamento = models.TextField(blank=True)
    consulta_sefaz_em = models.DateTimeField(null=True, blank=True)
    mensagem_consulta_sefaz = models.TextField(blank=True)
    aguardando_consulta_sefaz = models.BooleanField(default=False)
    tentativas_consulta_sefaz = models.PositiveIntegerField(default=0)
    contingencia_iniciada_em = models.DateTimeField(null=True, blank=True)
    contingencia_justificativa = models.CharField(max_length=256, blank=True)
    transmissao_limite_em = models.DateTimeField(null=True, blank=True)
    tentativas_transmissao = models.PositiveIntegerField(default=0)
    ultima_tentativa_em = models.DateTimeField(null=True, blank=True)
    proxima_tentativa_em = models.DateTimeField(null=True, blank=True)
    transmissao_reservada_em = models.DateTimeField(null=True, blank=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="documentos_fiscais")
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-criado_em"]
        unique_together = ["filial", "tipo_documento", "serie", "numero"]

    def __str__(self):
        numero = self.numero or "sem número"
        return f"{self.get_tipo_documento_display()} {self.serie}/{numero}"
