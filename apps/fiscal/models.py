from django.conf import settings
from django.db import models
from django.utils import timezone


class AmbienteFiscal(models.TextChoices):
    HOMOLOGACAO = "HOMOLOGACAO", "Homologacao"
    PRODUCAO = "PRODUCAO", "Producao"


class TipoDocumentoFiscal(models.TextChoices):
    NFCE = "NFCE", "NFC-e"
    NFE = "NFE", "NF-e"


class StatusDocumentoFiscal(models.TextChoices):
    RASCUNHO = "RASCUNHO", "Rascunho"
    PRONTO = "PRONTO", "Pronto para transmissao"
    EMITIDO = "EMITIDO", "Emitido"
    REJEITADO = "REJEITADO", "Rejeitado"
    CANCELADO = "CANCELADO", "Cancelado"
    INUTILIZADO = "INUTILIZADO", "Inutilizado"


class ConfiguracaoFiscal(models.Model):
    filial = models.OneToOneField("empresas.Filial", on_delete=models.PROTECT, related_name="configuracao_fiscal")
    ambiente = models.CharField(max_length=20, choices=AmbienteFiscal.choices, default=AmbienteFiscal.HOMOLOGACAO)
    regime_tributario = models.CharField(max_length=80, blank=True)
    inscricao_estadual = models.CharField(max_length=30, blank=True)
    csc_id = models.CharField("ID CSC", max_length=20, blank=True)
    csc_token = models.CharField("Token CSC", max_length=255, blank=True)
    certificado_nome = models.CharField(max_length=255, blank=True)
    certificado_validade = models.DateField(null=True, blank=True)
    certificado_a1_criptografado = models.BinaryField(blank=True, null=True, editable=False)
    certificado_senha_criptografada = models.BinaryField(blank=True, null=True, editable=False)
    certificado_atualizado_em = models.DateTimeField(null=True, blank=True)
    ativo = models.BooleanField(default=True)
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


class NaturezaOperacao(models.Model):
    descricao = models.CharField(max_length=120, unique=True)
    cfop = models.CharField(max_length=10, blank=True)
    tipo_documento = models.CharField(max_length=10, choices=TipoDocumentoFiscal.choices, default=TipoDocumentoFiscal.NFCE)
    movimenta_estoque = models.BooleanField(default=True)
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ["descricao"]

    def __str__(self):
        return self.descricao


class DocumentoFiscal(models.Model):
    filial = models.ForeignKey("empresas.Filial", on_delete=models.PROTECT, related_name="documentos_fiscais")
    venda = models.ForeignKey("vendas.Venda", on_delete=models.PROTECT, related_name="documentos_fiscais", null=True, blank=True)
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
    mensagem_retorno = models.TextField(blank=True)
    motivo_cancelamento = models.CharField(max_length=255, blank=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="documentos_fiscais")
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-criado_em"]
        unique_together = ["filial", "tipo_documento", "serie", "numero"]

    def __str__(self):
        numero = self.numero or "sem numero"
        return f"{self.get_tipo_documento_display()} {self.serie}/{numero}"
