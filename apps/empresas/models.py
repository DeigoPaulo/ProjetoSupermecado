import uuid

from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models


VALIDAR_IMAGEM_PNG_JPEG = FileExtensionValidator(
    allowed_extensions=["png", "jpg", "jpeg"],
    message="Envie uma imagem PNG, JPG ou JPEG.",
)


class ModoImplantacao(models.TextChoices):
    LOCAL = "LOCAL", "Somente servidor local"
    HIBRIDO = "HIBRIDO", "Servidor local com sincronizacao em nuvem"
    NUVEM_AGENTE = "NUVEM_AGENTE", "Nuvem com agente local"


class PoliticaConflitoSincronizacao(models.TextChoices):
    MANUAL = "MANUAL", "Resolver manualmente"
    REMOTO_PRODUTOS_ESTOQUE = "REMOTO_PRODUTOS_ESTOQUE", "Nuvem prevalece para produtos e estoque"
    LOCAL_PRODUTOS_ESTOQUE = "LOCAL_PRODUTOS_ESTOQUE", "Loja prevalece para produtos e estoque"


class StatusSincronizacao(models.TextChoices):
    PENDENTE = "PENDENTE", "Pendente"
    PROCESSANDO = "PROCESSANDO", "Processando"
    ENVIADO = "ENVIADO", "Enviado"
    ERRO = "ERRO", "Erro"
    PAUSADO = "PAUSADO", "Pausado pela política"


class StatusEventoEntrada(models.TextChoices):
    RECEBIDO = "RECEBIDO", "Recebido"
    PROCESSADO = "PROCESSADO", "Processado"
    CONFLITO = "CONFLITO", "Conflito"
    ERRO = "ERRO", "Erro"
    RESOLVIDO = "RESOLVIDO", "Resolvido manualmente"
    PAUSADO = "PAUSADO", "Pausado pela política"


class Empresa(models.Model):
    razao_social = models.CharField(max_length=255)
    nome_fantasia = models.CharField(max_length=255)
    cnpj = models.CharField(max_length=18, unique=True)
    telefone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    endereco = models.TextField(blank=True)
    regime_tributario = models.CharField(max_length=80, blank=True)
    logo = models.ImageField(upload_to="empresas/logos/", blank=True, null=True, validators=[VALIDAR_IMAGEM_PNG_JPEG])
    modo_implantacao = models.CharField(
        "Modo de implantacao",
        max_length=20,
        choices=ModoImplantacao.choices,
        default=ModoImplantacao.LOCAL,
    )
    sincronizacao_automatica = models.BooleanField("Sincronizacao automatica", default=False)
    url_sincronizacao = models.URLField("URL segura da nuvem", blank=True)
    politica_conflito_sincronizacao = models.CharField(
        "Politica de conflito",
        max_length=40,
        choices=PoliticaConflitoSincronizacao.choices,
        default=PoliticaConflitoSincronizacao.MANUAL,
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["nome_fantasia"]

    @property
    def sincronizacao_operacional_habilitada(self):
        return bool(
            self.is_active
            and self.modo_implantacao != ModoImplantacao.LOCAL
            and self.sincronizacao_automatica
            and self.url_sincronizacao
            and self.url_sincronizacao.lower().startswith("https://")
        )

    def save(self, *args, **kwargs):
        if self.modo_implantacao == ModoImplantacao.LOCAL:
            self.sincronizacao_automatica = False
            self.url_sincronizacao = ""
            if kwargs.get("update_fields") is not None:
                kwargs["update_fields"] = set(kwargs["update_fields"]) | {
                    "modo_implantacao", "sincronizacao_automatica", "url_sincronizacao"
                }
        super().save(*args, **kwargs)
        if self.sincronizacao_operacional_habilitada:
            self.eventos_sincronizacao.filter(status=StatusSincronizacao.PAUSADO).update(
                status=StatusSincronizacao.PENDENTE,
                ultimo_erro="",
                proxima_tentativa_em=None,
            )
            self.eventos_entrada_sincronizacao.filter(status=StatusEventoEntrada.PAUSADO).update(
                status=StatusEventoEntrada.RECEBIDO,
                ultimo_erro="",
            )
        else:
            motivo = "Pausado pela política de implantação local ou sincronização desativada."
            self.eventos_sincronizacao.filter(
                status__in=[StatusSincronizacao.PENDENTE, StatusSincronizacao.ERRO]
            ).update(status=StatusSincronizacao.PAUSADO, ultimo_erro=motivo, proxima_tentativa_em=None)
            self.eventos_entrada_sincronizacao.filter(
                status__in=[StatusEventoEntrada.RECEBIDO, StatusEventoEntrada.ERRO]
            ).update(status=StatusEventoEntrada.PAUSADO, ultimo_erro=motivo)
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


class EventoSincronizacao(models.Model):
    identificador = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    empresa = models.ForeignKey(Empresa, on_delete=models.PROTECT, related_name="eventos_sincronizacao")
    filial = models.ForeignKey(Filial, on_delete=models.PROTECT, related_name="eventos_sincronizacao", null=True, blank=True)
    tipo = models.CharField(max_length=100)
    objeto_tipo = models.CharField(max_length=100)
    objeto_id = models.CharField(max_length=80)
    chave_idempotencia = models.CharField(max_length=180, unique=True)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=20, choices=StatusSincronizacao.choices, default=StatusSincronizacao.PENDENTE)
    tentativas = models.PositiveIntegerField(default=0)
    proxima_tentativa_em = models.DateTimeField(null=True, blank=True)
    ultimo_erro = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    processado_em = models.DateTimeField(null=True, blank=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["criado_em"]
        indexes = [
            models.Index(fields=["status", "proxima_tentativa_em"], name="empresas_ev_status_3e6760_idx"),
            models.Index(fields=["empresa", "criado_em"], name="empresas_ev_empresa_a7567c_idx"),
        ]

    def __str__(self):
        return f"{self.tipo} - {self.objeto_tipo}:{self.objeto_id}"


class EventoEntradaSincronizacao(models.Model):
    identificador = models.UUIDField(unique=True, editable=False)
    chave_idempotencia = models.CharField(max_length=180, unique=True)
    empresa = models.ForeignKey(Empresa, on_delete=models.PROTECT, related_name="eventos_entrada_sincronizacao")
    tipo = models.CharField(max_length=100)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=20, choices=StatusEventoEntrada.choices, default=StatusEventoEntrada.RECEBIDO)
    ultimo_erro = models.TextField(blank=True)
    resolucao_conflito = models.TextField(blank=True)
    resolvido_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="eventos_entrada_resolvidos")
    resolvido_em = models.DateTimeField(null=True, blank=True)
    recebido_em = models.DateTimeField(auto_now_add=True)
    processado_em = models.DateTimeField(null=True, blank=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["recebido_em"]
        indexes = [models.Index(fields=["status", "recebido_em"], name="empresas_in_status_entrada_idx")]

    def __str__(self):
        return f"Entrada {self.tipo} - {self.identificador}"


class VendaSincronizada(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.PROTECT, related_name="vendas_sincronizadas")
    filial = models.ForeignKey(Filial, on_delete=models.PROTECT, related_name="vendas_sincronizadas", null=True, blank=True)
    evento = models.OneToOneField(EventoEntradaSincronizacao, on_delete=models.PROTECT, related_name="venda_sincronizada")
    venda_externa_id = models.CharField(max_length=120)
    caixa_externo = models.CharField(max_length=80, blank=True)
    operador = models.CharField(max_length=120, blank=True)
    cliente = models.CharField(max_length=180, blank=True)
    total_bruto = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    desconto = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_liquido = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    itens = models.JSONField(default=list)
    pagamentos = models.JSONField(default=list)
    realizada_em = models.DateTimeField(null=True, blank=True)
    recebida_em = models.DateTimeField(auto_now_add=True)
    atualizada_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-realizada_em", "-recebida_em"]
        constraints = [
            models.UniqueConstraint(fields=["empresa", "venda_externa_id"], name="empresas_venda_sync_unica")
        ]

    def __str__(self):
        return f"Venda sincronizada {self.venda_externa_id} - {self.total_liquido}"


class DocumentoFiscalSincronizado(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.PROTECT, related_name="documentos_fiscais_sincronizados")
    filial = models.ForeignKey(Filial, on_delete=models.PROTECT, related_name="documentos_fiscais_sincronizados", null=True, blank=True)
    evento = models.OneToOneField(EventoEntradaSincronizacao, on_delete=models.PROTECT, related_name="documento_fiscal_sincronizado")
    documento_externo_id = models.CharField(max_length=120)
    venda_externa_id = models.CharField(max_length=120, blank=True)
    tipo_documento = models.CharField(max_length=20, default="NFCE")
    ambiente = models.CharField(max_length=20, blank=True)
    serie = models.CharField(max_length=20, blank=True)
    numero = models.CharField(max_length=30, blank=True)
    chave_acesso = models.CharField(max_length=80, blank=True)
    protocolo = models.CharField(max_length=80, blank=True)
    status = models.CharField(max_length=30, blank=True)
    valor_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    emitido_em = models.DateTimeField(null=True, blank=True)
    payload = models.JSONField(default=dict)
    recebido_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-emitido_em", "-recebido_em"]
        constraints = [
            models.UniqueConstraint(fields=["empresa", "documento_externo_id"], name="empresas_doc_fiscal_sync_unico")
        ]

    def __str__(self):
        return f"Documento fiscal sincronizado {self.documento_externo_id}"

# Create your models here.
