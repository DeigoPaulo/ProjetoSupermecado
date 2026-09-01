import hashlib
import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone


class AmbienteFiscal(models.TextChoices):
    HOMOLOGACAO = "HOMOLOGACAO", "Homologacao"
    PRODUCAO = "PRODUCAO", "Producao"


class ProvedorEmissaoFiscal(models.TextChoices):
    DESATIVADO = "DESATIVADO", "Emissão externa desativada"
    PADRAO_SERVIDOR = "PADRAO_SERVIDOR", "Compatibilidade do servidor"
    FOCUS = "FOCUS", "Integração Focus NFe"
    SEFAZ_DIRETA_GO = "SEFAZ_DIRETA_GO", "Conexão direta SEFAZ - Goiás"


class TipoDocumentoFiscal(models.TextChoices):
    NFCE = "NFCE", "NFC-e"
    NFE = "NFE", "NF-e"

class CodigoRegimeTributario(models.TextChoices):
    SIMPLES_NACIONAL = "1", "1 - Simples Nacional"
    SIMPLES_EXCESSO_SUBLIMITE = "2", "2 - Simples Nacional, excesso de sublimite"
    REGIME_NORMAL = "3", "3 - Regime Normal"
    MEI = "4", "4 - Simples Nacional, MEI"


class ModoTransicaoIbsCbs(models.TextChoices):
    LEGADO = "LEGADO", "Legado (ICMS, PIS e COFINS)"
    PREPARACAO = "PREPARACAO", "Preparação IBS/CBS"
    EMISSAO_HOMOLOGADA = "EMISSAO_HOMOLOGADA", "Emissão IBS/CBS homologada"


class StatusHomologacaoFiscal(models.TextChoices):
    PENDENTE = "PENDENTE", "Pendente"
    EM_ANDAMENTO = "EM_ANDAMENTO", "Em andamento"
    CONCLUIDA = "CONCLUIDA", "Concluída"

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
    provedor_emissao = models.CharField(
        "Canal técnico de emissão",
        max_length=24,
        choices=ProvedorEmissaoFiscal.choices,
        default=ProvedorEmissaoFiscal.PADRAO_SERVIDOR,
        help_text=(
            "Seleção técnica exclusiva do Master. Credenciais permanecem no ambiente "
            "seguro do servidor."
        ),
    )
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
    modo_transicao_ibs_cbs = models.CharField(
        "Modo de transição IBS/CBS",
        max_length=24,
        choices=ModoTransicaoIbsCbs.choices,
        default=ModoTransicaoIbsCbs.LEGADO,
        help_text=(
            "Preparação exige CST IBS/CBS e cClassTrib nos produtos após a vigência. "
            "A emissão somente pode ser ativada depois da homologação do schema e do adaptador fiscal."
        ),
    )
    ibs_cbs_vigencia_inicio = models.DateField(
        "Início da vigência IBS/CBS",
        null=True,
        blank=True,
        help_text="Data aprovada pelo contador para iniciar a validação da nova classificação tributária.",
    )
    ibs_cbs_versao_leiaute = models.CharField(
        "Versão do leiaute IBS/CBS",
        max_length=80,
        blank=True,
        help_text="Identifique a Nota Técnica e o pacote XSD homologados para esta filial.",
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

    def ibs_cbs_exigido_em(self, data_referencia=None):
        if self.modo_transicao_ibs_cbs == ModoTransicaoIbsCbs.LEGADO:
            return False
        data_referencia = data_referencia or timezone.localdate()
        return not self.ibs_cbs_vigencia_inicio or data_referencia >= self.ibs_cbs_vigencia_inicio


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
    confirmacoes_nao_localizado = models.PositiveIntegerField(default=0)
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

    @property
    def contingencia_prazo_vencido(self):
        return bool(
            self.tipo_documento == TipoDocumentoFiscal.NFCE
            and self.contingencia_iniciada_em
            and self.transmissao_limite_em
            and self.status != StatusDocumentoFiscal.EMITIDO
            and self.transmissao_limite_em < timezone.now()
        )

    class Meta:
        ordering = ["-criado_em"]
        unique_together = ["filial", "tipo_documento", "serie", "numero"]

    def __str__(self):
        numero = self.numero or "sem número"
        return f"{self.get_tipo_documento_display()} {self.serie}/{numero}"
class TipoEvidenciaFiscal(models.TextChoices):
    XML_ENVIO = "XML_ENVIO", "XML transmitido"
    RETORNO_TRANSMISSAO = "RETORNO_TRANSMISSAO", "Retorno da transmissão"
    XML_AUTORIZADO = "XML_AUTORIZADO", "XML autorizado"
    RETORNO_CONSULTA = "RETORNO_CONSULTA", "Retorno da consulta"
    EVENTO_CANCELAMENTO_ENVIO = "EVENTO_CANCELAMENTO_ENVIO", "Pedido de cancelamento"
    EVENTO_CANCELAMENTO_RETORNO = "EVENTO_CANCELAMENTO_RETORNO", "Retorno do cancelamento"
    EVENTO_CCE_ENVIO = "EVENTO_CCE_ENVIO", "XML da CC-e transmitida"
    EVENTO_CCE_RETORNO = "EVENTO_CCE_RETORNO", "XML de retorno da CC-e"


class EvidenciaFiscalQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValueError("Evidências fiscais são imutáveis e não podem ser alteradas.")

    def delete(self):
        raise ValueError("Evidências fiscais são imutáveis e não podem ser excluídas.")

class EvidenciaFiscal(models.Model):
    objects = EvidenciaFiscalQuerySet.as_manager()

    documento = models.ForeignKey(
        DocumentoFiscal,
        on_delete=models.PROTECT,
        related_name="evidencias_fiscais",
    )
    sequencia = models.PositiveIntegerField()
    tipo = models.CharField(max_length=40, choices=TipoEvidenciaFiscal.choices)
    canal = models.CharField(max_length=40, blank=True)
    referencia = models.CharField(max_length=180)
    chave_acesso = models.CharField(max_length=44, blank=True)
    protocolo = models.CharField(max_length=80, blank=True)
    conteudo = models.TextField()
    conteudo_sha256 = models.CharField(max_length=64)
    anterior_sha256 = models.CharField(max_length=64, blank=True)
    cadeia_sha256 = models.CharField(max_length=64)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="evidencias_fiscais_registradas",
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sequencia", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["documento", "sequencia"],
                name="fiscal_evidencia_documento_seq_uniq",
            ),
            models.UniqueConstraint(
                fields=["documento", "tipo", "referencia"],
                name="fiscal_evidencia_documento_ref_uniq",
            ),
        ]
        indexes = [
            models.Index(
                fields=["documento", "tipo"],
                name="fiscal_evid_doc_tipo_idx",
            ),
        ]
        verbose_name = "evidência fiscal imutável"
        verbose_name_plural = "evidências fiscais imutáveis"

    @staticmethod
    def calcular_cadeia(documento_id, sequencia, tipo, referencia, conteudo_sha256, anterior_sha256):
        base = "|".join(
            [
                str(documento_id),
                str(sequencia),
                str(tipo),
                str(referencia),
                str(conteudo_sha256),
                str(anterior_sha256 or ""),
            ]
        )
        return hashlib.sha256(base.encode("utf-8")).hexdigest()

    def save(self, *args, **kwargs):
        if self.pk or not self._state.adding:
            raise ValueError("Evidências fiscais são imutáveis e não podem ser alteradas.")
        self.conteudo_sha256 = hashlib.sha256(self.conteudo.encode("utf-8")).hexdigest()
        self.cadeia_sha256 = self.calcular_cadeia(
            self.documento_id,
            self.sequencia,
            self.tipo,
            self.referencia,
            self.conteudo_sha256,
            self.anterior_sha256,
        )
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Evidências fiscais são imutáveis e não podem ser excluídas.")

    def __str__(self):
        return f"Evidência {self.documento_id}/{self.sequencia} - {self.tipo}"

class HomologacaoFiscal(models.Model):
    configuracao = models.OneToOneField(
        ConfiguracaoFiscal,
        on_delete=models.CASCADE,
        related_name="homologacao_tecnica",
    )
    status = models.CharField(
        max_length=20,
        choices=StatusHomologacaoFiscal.choices,
        default=StatusHomologacaoFiscal.PENDENTE,
    )
    responsavel_tecnico = models.CharField(max_length=160, blank=True)
    evidencia_referencia = models.CharField(
        max_length=500,
        blank=True,
        help_text="Número de chamado, URL protegida, protocolo ou caminho da evidência de homologação.",
    )
    observacoes = models.TextField(blank=True)
    concluida_em = models.DateTimeField(null=True, blank=True)
    concluida_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="homologacoes_fiscais_concluidas",
    )
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["configuracao__filial__nome"]
        verbose_name = "homologação fiscal"
        verbose_name_plural = "homologações fiscais"

    def __str__(self):
        return f"{self.configuracao.filial} - {self.get_status_display()}"

class StatusDFeRecebido(models.TextChoices):
    NOVO = "NOVO", "Novo"
    XML_DISPONIVEL = "XML_DISPONIVEL", "XML disponível"
    VINCULADO = "VINCULADO", "Vinculado à entrada"
    IGNORADO = "IGNORADO", "Ignorado"


class ConfiguracaoDistribuicaoDFe(models.Model):
    empresa = models.OneToOneField(
        "empresas.Empresa",
        on_delete=models.PROTECT,
        related_name="configuracao_distribuicao_dfe",
    )
    ativo = models.BooleanField("Caixa de entrada de DF-e ativa", default=True)
    ultimo_nsu = models.CharField("Último NSU processado", max_length=20, blank=True)
    ultima_consulta_em = models.DateTimeField(null=True, blank=True)
    ultima_mensagem = models.TextField(blank=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "configuração de distribuição DF-e"
        verbose_name_plural = "configurações de distribuição DF-e"

    def __str__(self):
        return f"DF-e recebidos - {self.empresa}"


class ControleDistribuicaoDFeFilial(models.Model):
    configuracao = models.ForeignKey(
        ConfiguracaoDistribuicaoDFe,
        on_delete=models.CASCADE,
        related_name="controles_filiais",
    )
    filial = models.OneToOneField(
        "empresas.Filial",
        on_delete=models.PROTECT,
        related_name="controle_distribuicao_dfe",
    )
    ultimo_nsu = models.CharField("Último NSU processado", max_length=20, blank=True)
    max_nsu = models.CharField("Maior NSU disponível", max_length=20, blank=True)
    ultima_consulta_em = models.DateTimeField(null=True, blank=True)
    proxima_consulta_em = models.DateTimeField(null=True, blank=True)
    ultima_mensagem = models.TextField(blank=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["filial__nome"]
        verbose_name = "controle de distribuição DF-e por filial"
        verbose_name_plural = "controles de distribuição DF-e por filial"

    def __str__(self):
        return f"DF-e {self.filial} - NSU {self.ultimo_nsu or 'inicial'}"


class DocumentoDFeRecebido(models.Model):
    empresa = models.ForeignKey(
        "empresas.Empresa",
        on_delete=models.PROTECT,
        related_name="documentos_dfe_recebidos",
    )
    filial_destino = models.ForeignKey(
        "empresas.Filial",
        on_delete=models.PROTECT,
        related_name="documentos_dfe_recebidos",
        null=True,
        blank=True,
    )
    entrada_compra = models.OneToOneField(
        "compras.EntradaCompra",
        on_delete=models.PROTECT,
        related_name="documento_dfe_recebido",
        null=True,
        blank=True,
    )
    chave_acesso = models.CharField(max_length=44)
    nsu = models.CharField(max_length=20, blank=True)
    schema = models.CharField(max_length=80, blank=True)
    emitente_cnpj = models.CharField(max_length=14, blank=True)
    emitente_nome = models.CharField(max_length=255, blank=True)
    numero_documento = models.CharField(max_length=30, blank=True)
    data_emissao = models.DateField(null=True, blank=True)
    valor_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    status = models.CharField(max_length=24, choices=StatusDFeRecebido.choices, default=StatusDFeRecebido.NOVO)
    origem = models.CharField(max_length=24, default="MANUAL")
    xml_conteudo = models.TextField(blank=True)
    recebido_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-recebido_em"]
        constraints = [
            models.UniqueConstraint(fields=["empresa", "chave_acesso"], name="fiscal_dfe_empresa_chave_uniq"),
        ]
        indexes = [
            models.Index(fields=["empresa", "status", "-recebido_em"], name="fiscal_dfe_empresa_status_idx"),
        ]

    def __str__(self):
        return f"DF-e {self.chave_acesso or self.pk}"

class EventoDFeRecebido(models.Model):
    empresa = models.ForeignKey(
        "empresas.Empresa",
        on_delete=models.PROTECT,
        related_name="eventos_dfe_recebidos",
    )
    filial_destino = models.ForeignKey(
        "empresas.Filial",
        on_delete=models.PROTECT,
        related_name="eventos_dfe_recebidos",
        null=True,
        blank=True,
    )
    nsu = models.CharField(max_length=20)
    schema = models.CharField(max_length=80, blank=True)
    chave_acesso = models.CharField(max_length=44, blank=True)
    tipo_evento = models.CharField(max_length=20, blank=True)
    sequencia = models.PositiveIntegerField(default=1)
    data_evento = models.DateTimeField(null=True, blank=True)
    descricao = models.CharField(max_length=255, blank=True)
    xml_conteudo = models.TextField()
    recebido_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-recebido_em", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["empresa", "nsu"],
                name="fiscal_evento_dfe_empresa_nsu_uniq",
            )
        ]
        indexes = [
            models.Index(
                fields=["empresa", "-recebido_em"],
                name="fiscal_evt_dfe_emp_data_idx",
            )
        ]
        verbose_name = "evento DF-e recebido"
        verbose_name_plural = "eventos DF-e recebidos"

    def __str__(self):
        return f"Evento DF-e {self.tipo_evento or '-'} - NSU {self.nsu}"


class TipoManifestacaoDestinatario(models.TextChoices):
    CONFIRMACAO = "210200", "Confirmação da operação"
    CIENCIA = "210210", "Ciência da operação"
    DESCONHECIMENTO = "210220", "Desconhecimento da operação"
    OPERACAO_NAO_REALIZADA = "210240", "Operação não realizada"


class StatusManifestacaoDestinatario(models.TextChoices):
    PENDENTE = "PENDENTE", "Pendente"
    AUTORIZADA = "AUTORIZADA", "Autorizada"
    REJEITADA = "REJEITADA", "Rejeitada"
    ERRO = "ERRO", "Erro de transmissão"


class ManifestacaoDestinatario(models.Model):
    empresa = models.ForeignKey(
        "empresas.Empresa", on_delete=models.PROTECT, related_name="manifestacoes_destinatario"
    )
    filial = models.ForeignKey(
        "empresas.Filial", on_delete=models.PROTECT, related_name="manifestacoes_destinatario"
    )
    documento = models.ForeignKey(
        DocumentoDFeRecebido,
        on_delete=models.PROTECT,
        related_name="manifestacoes_destinatario",
    )
    tipo = models.CharField(max_length=6, choices=TipoManifestacaoDestinatario.choices)
    status = models.CharField(
        max_length=16,
        choices=StatusManifestacaoDestinatario.choices,
        default=StatusManifestacaoDestinatario.PENDENTE,
    )
    justificativa = models.CharField(max_length=255, blank=True)
    ambiente = models.CharField(max_length=20, choices=AmbienteFiscal.choices)
    codigo_status = models.CharField(max_length=10, blank=True)
    protocolo = models.CharField(max_length=80, blank=True)
    mensagem = models.TextField(blank=True)
    xml_envio = models.TextField(blank=True)
    xml_retorno = models.TextField(blank=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="manifestacoes_destinatario",
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    processado_em = models.DateTimeField(null=True, blank=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-criado_em", "-id"]
        indexes = [
            models.Index(
                fields=["empresa", "documento", "-criado_em"],
                name="fiscal_manif_emp_doc_idx",
            )
        ]
        verbose_name = "manifestação do destinatário"
        verbose_name_plural = "manifestações do destinatário"

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.documento.chave_acesso}"


class StatusCartaCorrecao(models.TextChoices):
    PENDENTE = "PENDENTE", "Pendente"
    AUTORIZADA = "AUTORIZADA", "Autorizada"
    REJEITADA = "REJEITADA", "Rejeitada"
    ERRO = "ERRO", "Erro de transmissão"


class CartaCorrecaoFiscal(models.Model):
    empresa = models.ForeignKey(
        "empresas.Empresa", on_delete=models.PROTECT, related_name="cartas_correcao_fiscais"
    )
    filial = models.ForeignKey(
        "empresas.Filial", on_delete=models.PROTECT, related_name="cartas_correcao_fiscais"
    )
    documento = models.ForeignKey(
        DocumentoFiscal,
        on_delete=models.PROTECT,
        related_name="cartas_correcao",
    )
    sequencia = models.PositiveSmallIntegerField()
    correcao = models.CharField(max_length=1000)
    status = models.CharField(
        max_length=16,
        choices=StatusCartaCorrecao.choices,
        default=StatusCartaCorrecao.PENDENTE,
    )
    ambiente = models.CharField(max_length=20, choices=AmbienteFiscal.choices)
    codigo_status = models.CharField(max_length=10, blank=True)
    protocolo = models.CharField(max_length=80, blank=True)
    mensagem = models.TextField(blank=True)
    xml_envio = models.TextField(blank=True)
    xml_retorno = models.TextField(blank=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="cartas_correcao_fiscais",
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    processado_em = models.DateTimeField(null=True, blank=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-sequencia", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["documento", "sequencia"],
                name="fiscal_cce_documento_seq_uniq",
            )
        ]
        indexes = [
            models.Index(
                fields=["empresa", "documento", "-sequencia"],
                name="fiscal_cce_emp_doc_seq_idx",
            )
        ]
        verbose_name = "Carta de Correção Eletrônica"
        verbose_name_plural = "Cartas de Correção Eletrônicas"

    def __str__(self):
        return f"CC-e #{self.sequencia} - {self.documento}"


class TipoDocumentoConsultaCadastro(models.TextChoices):
    CNPJ = "CNPJ", "CNPJ"
    CPF = "CPF", "CPF"
    IE = "IE", "Inscrição estadual"


class StatusConsultaCadastro(models.TextChoices):
    PENDENTE = "PENDENTE", "Pendente"
    SUCESSO = "SUCESSO", "Consultado"
    REJEITADA = "REJEITADA", "Rejeitada"
    ERRO = "ERRO", "Erro de comunicação"


class ConsultaCadastroContribuinte(models.Model):
    empresa = models.ForeignKey(
        "empresas.Empresa", on_delete=models.PROTECT, related_name="consultas_cadastro_fiscais"
    )
    filial = models.ForeignKey(
        "empresas.Filial", on_delete=models.PROTECT, related_name="consultas_cadastro_fiscais"
    )
    uf = models.CharField(max_length=2)
    tipo_documento = models.CharField(
        max_length=4, choices=TipoDocumentoConsultaCadastro.choices
    )
    documento = models.CharField(max_length=14)
    status = models.CharField(
        max_length=16,
        choices=StatusConsultaCadastro.choices,
        default=StatusConsultaCadastro.PENDENTE,
    )
    codigo_status = models.CharField(max_length=10, blank=True)
    mensagem = models.TextField(blank=True)
    ocorrencias = models.JSONField(default=list, blank=True)
    xml_envio = models.TextField(blank=True)
    xml_retorno = models.TextField(blank=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="consultas_cadastro_fiscais",
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    processado_em = models.DateTimeField(null=True, blank=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-criado_em", "-id"]
        indexes = [
            models.Index(
                fields=["empresa", "filial", "-criado_em"],
                name="fiscal_cad_emp_fil_data_idx",
            )
        ]
        verbose_name = "consulta de cadastro do contribuinte"
        verbose_name_plural = "consultas de cadastro dos contribuintes"

    def __str__(self):
        return f"{self.tipo_documento} {self.documento} - {self.get_status_display()}"

class StatusFonteAtualizacaoFiscal(models.TextChoices):
    NOVA = "NOVA", "Aguardando primeira consulta"
    OK = "OK", "Atualizada"
    ERRO = "ERRO", "Falha na consulta"


class FonteAtualizacaoFiscal(models.Model):
    codigo = models.SlugField(max_length=80, unique=True)
    nome = models.CharField(max_length=160)
    url = models.URLField(max_length=500)
    status = models.CharField(
        max_length=12,
        choices=StatusFonteAtualizacaoFiscal.choices,
        default=StatusFonteAtualizacaoFiscal.NOVA,
    )
    etag = models.CharField(max_length=255, blank=True)
    ultima_modificacao_http = models.CharField(max_length=255, blank=True)
    conteudo_sha256 = models.CharField(max_length=64, blank=True)
    itens_snapshot = models.JSONField(default=list, blank=True)
    ultima_consulta_em = models.DateTimeField(null=True, blank=True)
    ultima_alteracao_em = models.DateTimeField(null=True, blank=True)
    ultima_mensagem = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nome"]
        verbose_name = "fonte de atualização fiscal"
        verbose_name_plural = "fontes de atualização fiscal"

    def __str__(self):
        return self.nome


class StatusAlertaAtualizacaoFiscal(models.TextChoices):
    NOVO = "NOVO", "Novo"
    REVISADO = "REVISADO", "Revisado"
    IGNORADO = "IGNORADO", "Ignorado"


class AlertaAtualizacaoFiscal(models.Model):
    fonte = models.ForeignKey(
        FonteAtualizacaoFiscal,
        on_delete=models.CASCADE,
        related_name="alertas",
    )
    fingerprint = models.CharField(max_length=64)
    titulo = models.CharField(max_length=500)
    url_referencia = models.URLField(max_length=500)
    status = models.CharField(
        max_length=12,
        choices=StatusAlertaAtualizacaoFiscal.choices,
        default=StatusAlertaAtualizacaoFiscal.NOVO,
    )
    detectado_em = models.DateTimeField(auto_now_add=True)
    revisado_em = models.DateTimeField(null=True, blank=True)
    revisado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="alertas_atualizacao_fiscal_revisados",
    )

    class Meta:
        ordering = ["-detectado_em"]
        constraints = [
            models.UniqueConstraint(
                fields=["fonte", "fingerprint"],
                name="fiscal_alerta_fonte_fingerprint_uniq",
            )
        ]
        indexes = [
            models.Index(
                fields=["status", "-detectado_em"],
                name="fiscal_alerta_status_data_idx",
            )
        ]
        verbose_name = "alerta de atualização fiscal"
        verbose_name_plural = "alertas de atualização fiscal"

    def __str__(self):
        return self.titulo

class CatalogoBeneficioFiscal(models.Model):
    uf = models.CharField(max_length=2)
    versao = models.CharField(max_length=100)
    fonte_nome = models.CharField(max_length=255)
    fonte_url = models.URLField(max_length=500)
    fonte_sha256 = models.CharField(max_length=64)
    publicado_em = models.DateField(null=True, blank=True)
    vigencia_inicio = models.DateField()
    vigencia_fim = models.DateField(null=True, blank=True)
    ativo = models.BooleanField(default=False)
    quantidade_itens = models.PositiveIntegerField(default=0)
    codigos_duplicados = models.JSONField(default=list, blank=True)
    importado_em = models.DateTimeField(auto_now_add=True)
    importado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="catalogos_beneficio_fiscal_importados",
    )

    class Meta:
        ordering = ["uf", "-vigencia_inicio", "-importado_em"]
        constraints = [
            models.UniqueConstraint(
                fields=["uf", "versao", "fonte_sha256"],
                name="fiscal_cbenef_uf_versao_hash_uniq",
            ),
        ]
        indexes = [
            models.Index(
                fields=["uf", "ativo", "vigencia_inicio", "vigencia_fim"],
                name="fiscal_cbenef_vigencia_idx",
            ),
        ]
        verbose_name = "catálogo de benefício fiscal"
        verbose_name_plural = "catálogos de benefícios fiscais"

    def clean(self):
        super().clean()
        self.uf = (self.uf or "").strip().upper()
        self.fonte_sha256 = (self.fonte_sha256 or "").strip().lower()
        erros = {}
        if not re.fullmatch(r"[a-f0-9]{64}", self.fonte_sha256):
            erros["fonte_sha256"] = "Informe o SHA-256 integral do arquivo oficial."
        if self.vigencia_fim and self.vigencia_fim < self.vigencia_inicio:
            erros["vigencia_fim"] = "A vigência final não pode anteceder a inicial."
        if erros:
            raise ValidationError(erros)

    def __str__(self):
        return f"cBenef {self.uf} - {self.versao}"


class ItemBeneficioFiscal(models.Model):
    catalogo = models.ForeignKey(
        CatalogoBeneficioFiscal,
        on_delete=models.PROTECT,
        related_name="itens",
    )
    codigo = models.CharField(max_length=20)
    csts = models.JSONField(default=list)
    dispositivo_legal = models.TextField(blank=True)
    descricao = models.TextField(blank=True)
    observacao = models.TextField(blank=True)

    class Meta:
        ordering = ["codigo"]
        constraints = [
            models.UniqueConstraint(
                fields=["catalogo", "codigo"],
                name="fiscal_cbenef_catalogo_codigo_uniq",
            ),
        ]
        indexes = [models.Index(fields=["codigo"], name="fiscal_cbenef_codigo_idx")]
        verbose_name = "item de benefício fiscal"
        verbose_name_plural = "itens de benefícios fiscais"

    def __str__(self):
        return f"{self.codigo} ({', '.join(self.csts)})"

class CatalogoNCM(models.Model):
    versao = models.CharField(max_length=120)
    referencia_em = models.DateField()
    ato = models.CharField(max_length=255)
    fonte_nome = models.CharField(max_length=255)
    fonte_url = models.URLField(max_length=500)
    fonte_sha256 = models.CharField(max_length=64)
    ativo = models.BooleanField(default=False)
    quantidade_itens = models.PositiveIntegerField(default=0)
    quantidade_linhas_origem = models.PositiveIntegerField(default=0)
    importado_em = models.DateTimeField(auto_now_add=True)
    importado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="catalogos_ncm_importados",
    )

    class Meta:
        ordering = ["-referencia_em", "-importado_em"]
        constraints = [
            models.UniqueConstraint(
                fields=["versao", "fonte_sha256"],
                name="fiscal_ncm_versao_hash_uniq",
            ),
        ]
        indexes = [
            models.Index(
                fields=["ativo", "referencia_em"],
                name="fiscal_ncm_ativo_ref_idx",
            ),
        ]
        verbose_name = "catálogo NCM"
        verbose_name_plural = "catálogos NCM"

    def clean(self):
        super().clean()
        self.fonte_sha256 = (self.fonte_sha256 or "").strip().lower()
        if not re.fullmatch(r"[a-f0-9]{64}", self.fonte_sha256):
            raise ValidationError({"fonte_sha256": "Informe o SHA-256 integral do arquivo oficial."})

    def __str__(self):
        return f"NCM {self.versao} ({self.referencia_em:%d/%m/%Y})"


class ItemNCM(models.Model):
    catalogo = models.ForeignKey(
        CatalogoNCM,
        on_delete=models.PROTECT,
        related_name="itens",
    )
    codigo = models.CharField(max_length=8)
    codigo_formatado = models.CharField(max_length=12)
    descricao = models.TextField()
    vigencia_inicio = models.DateField()
    vigencia_fim = models.DateField()
    ato_inicio = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["codigo"]
        constraints = [
            models.UniqueConstraint(
                fields=["catalogo", "codigo"],
                name="fiscal_ncm_catalogo_codigo_uniq",
            ),
        ]
        indexes = [models.Index(fields=["codigo"], name="fiscal_ncm_codigo_idx")]
        verbose_name = "item NCM"
        verbose_name_plural = "itens NCM"

    def __str__(self):
        return f"{self.codigo_formatado} - {self.descricao}"

class CatalogoCEST(models.Model):
    versao = models.CharField(max_length=120)
    referencia_em = models.DateField()
    ato = models.CharField(max_length=255)
    fonte_nome = models.CharField(max_length=255)
    fonte_url = models.URLField(max_length=500)
    fonte_sha256 = models.CharField(max_length=64)
    ativo = models.BooleanField(default=False)
    quantidade_itens = models.PositiveIntegerField(default=0)
    quantidade_linhas_origem = models.PositiveIntegerField(default=0)
    quantidade_tabelas_origem = models.PositiveIntegerField(default=0)
    importado_em = models.DateTimeField(auto_now_add=True)
    importado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="catalogos_cest_importados",
    )

    class Meta:
        ordering = ["-referencia_em", "-importado_em"]
        constraints = [
            models.UniqueConstraint(
                fields=["versao", "fonte_sha256"],
                name="fiscal_cest_versao_hash_uniq",
            ),
        ]
        indexes = [
            models.Index(
                fields=["ativo", "referencia_em"],
                name="fiscal_cest_ativo_ref_idx",
            ),
        ]
        verbose_name = "catálogo CEST"
        verbose_name_plural = "catálogos CEST"

    def clean(self):
        super().clean()
        self.fonte_sha256 = (self.fonte_sha256 or "").strip().lower()
        if not re.fullmatch(r"[a-f0-9]{64}", self.fonte_sha256):
            raise ValidationError({"fonte_sha256": "Informe o SHA-256 integral do arquivo oficial."})

    def __str__(self):
        return f"CEST {self.versao} ({self.referencia_em:%d/%m/%Y})"


class ItemCEST(models.Model):
    catalogo = models.ForeignKey(
        CatalogoCEST,
        on_delete=models.PROTECT,
        related_name="itens",
    )
    codigo = models.CharField(max_length=7)
    codigo_formatado = models.CharField(max_length=9)
    item = models.CharField(max_length=20)
    segmento_codigo = models.CharField(max_length=2)
    segmento_nome = models.CharField(max_length=255)
    ncm_sh_original = models.CharField(max_length=500, blank=True)
    ncm_prefixos = models.JSONField(default=list)
    descricao = models.TextField()

    class Meta:
        ordering = ["codigo"]
        constraints = [
            models.UniqueConstraint(
                fields=["catalogo", "codigo"],
                name="fiscal_cest_catalogo_codigo_uniq",
            ),
        ]
        indexes = [models.Index(fields=["codigo"], name="fiscal_cest_codigo_idx")]
        verbose_name = "item CEST"
        verbose_name_plural = "itens CEST"

    def __str__(self):
        return f"{self.codigo_formatado} - {self.descricao}"
class CatalogoCFOP(models.Model):
    versao = models.CharField(max_length=120)
    referencia_em = models.DateField()
    ato = models.CharField(max_length=255)
    fonte_nome = models.CharField(max_length=255)
    fonte_url = models.URLField(max_length=500)
    fonte_sha256 = models.CharField(max_length=64)
    ativo = models.BooleanField(default=False)
    quantidade_itens = models.PositiveIntegerField(default=0)
    quantidade_linhas_origem = models.PositiveIntegerField(default=0)
    quantidade_agrupadores = models.PositiveIntegerField(default=0)
    importado_em = models.DateTimeField(auto_now_add=True)
    importado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="catalogos_cfop_importados",
    )

    class Meta:
        ordering = ["-referencia_em", "-importado_em"]
        constraints = [
            models.UniqueConstraint(
                fields=["versao", "fonte_sha256"],
                name="fiscal_cfop_versao_hash_uniq",
            ),
        ]
        indexes = [
            models.Index(
                fields=["ativo", "referencia_em"],
                name="fiscal_cfop_ativo_ref_idx",
            ),
        ]
        verbose_name = "catálogo CFOP"
        verbose_name_plural = "catálogos CFOP"

    def clean(self):
        super().clean()
        self.fonte_sha256 = (self.fonte_sha256 or "").strip().lower()
        if not re.fullmatch(r"[a-f0-9]{64}", self.fonte_sha256):
            raise ValidationError({"fonte_sha256": "Informe o SHA-256 integral do arquivo oficial."})

    def __str__(self):
        return f"CFOP {self.versao} ({self.referencia_em:%d/%m/%Y})"


class ItemCFOP(models.Model):
    class Direcao(models.TextChoices):
        ENTRADA = "ENTRADA", "entrada"
        SAIDA = "SAIDA", "saída"

    class Alcance(models.TextChoices):
        INTERNA = "INTERNA", "interno"
        INTERESTADUAL = "INTERESTADUAL", "interestadual"
        EXTERIOR = "EXTERIOR", "exterior"

    catalogo = models.ForeignKey(
        CatalogoCFOP,
        on_delete=models.PROTECT,
        related_name="itens",
    )
    codigo = models.CharField(max_length=4)
    codigo_formatado = models.CharField(max_length=5)
    titulo = models.CharField(max_length=500)
    nota_explicativa = models.TextField()
    direcao = models.CharField(max_length=10, choices=Direcao.choices)
    alcance = models.CharField(max_length=20, choices=Alcance.choices)

    class Meta:
        ordering = ["codigo"]
        constraints = [
            models.UniqueConstraint(
                fields=["catalogo", "codigo"],
                name="fiscal_cfop_catalogo_codigo_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["codigo"], name="fiscal_cfop_codigo_idx"),
            models.Index(fields=["direcao", "alcance"], name="fiscal_cfop_dir_alc_idx"),
        ]
        verbose_name = "item CFOP"
        verbose_name_plural = "itens CFOP"

    def __str__(self):
        return f"{self.codigo_formatado} - {self.titulo}"
