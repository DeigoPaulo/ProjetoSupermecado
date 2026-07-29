import hashlib
import secrets
import uuid

from django.db import models
from django.utils import timezone


class StatusContrato(models.TextChoices):
    ATIVO = "ATIVO", "Ativo"
    AVISO = "AVISO", "Próximo do vencimento"
    TOLERANCIA = "TOLERANCIA", "Em tolerância"
    SUSPENSO = "SUSPENSO", "Suspenso"
    CANCELADO = "CANCELADO", "Cancelado"


class StatusFatura(models.TextChoices):
    PENDENTE = "PENDENTE", "Pendente"
    RECEBIDA = "RECEBIDA", "Recebida"
    VENCIDA = "VENCIDA", "Vencida"
    CANCELADA = "CANCELADA", "Cancelada"
    ESTORNADA = "ESTORNADA", "Estornada"


class StatusEventoCobranca(models.TextChoices):
    PENDENTE = "PENDENTE", "Pendente"
    PROCESSADO = "PROCESSADO", "Processado"
    IGNORADO = "IGNORADO", "Ignorado"
    ERRO = "ERRO", "Erro"


class PlanoComercial(models.Model):
    nome = models.CharField(max_length=120, unique=True)
    valor_matriz = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    valor_por_filial = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    valor_por_terminal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    dias_tolerancia = models.PositiveSmallIntegerField(default=7)
    dias_aviso = models.PositiveSmallIntegerField(default=10)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nome"]

    def __str__(self):
        return self.nome


class ContratoLicenca(models.Model):
    empresa = models.OneToOneField("empresas.Empresa", on_delete=models.PROTECT, related_name="contrato_licenca")
    plano = models.ForeignKey(PlanoComercial, on_delete=models.PROTECT, related_name="contratos")
    status = models.CharField(max_length=20, choices=StatusContrato.choices, default=StatusContrato.ATIVO)
    dia_vencimento = models.PositiveSmallIntegerField(default=10)
    valor_mensal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    validade_em = models.DateField(null=True, blank=True)
    tolerancia_ate = models.DateTimeField(null=True, blank=True)
    asaas_customer_id = models.CharField(max_length=80, blank=True)
    asaas_subscription_id = models.CharField(max_length=80, blank=True)
    cobranca_automatica = models.BooleanField(default=True)
    bloqueio_automatico = models.BooleanField(default=True)
    motivo_bloqueio = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["empresa__nome_fantasia"]

    def __str__(self):
        return f"{self.empresa} - {self.plano}"

    @property
    def operacional(self):
        return self.status in {StatusContrato.ATIVO, StatusContrato.AVISO, StatusContrato.TOLERANCIA}


class FaturaLicenca(models.Model):
    contrato = models.ForeignKey(ContratoLicenca, on_delete=models.PROTECT, related_name="faturas")
    competencia = models.DateField()
    vencimento = models.DateField()
    valor = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=StatusFatura.choices, default=StatusFatura.PENDENTE)
    referencia_externa = models.CharField(max_length=120, unique=True)
    asaas_payment_id = models.CharField(max_length=80, unique=True, null=True, blank=True)
    invoice_url = models.URLField(blank=True)
    bank_slip_url = models.URLField(blank=True)
    pago_em = models.DateTimeField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-competencia", "-vencimento"]
        constraints = [
            models.UniqueConstraint(fields=["contrato", "competencia"], name="licenca_fatura_competencia_unica")
        ]

    def __str__(self):
        return f"{self.contrato.empresa} - {self.competencia:%m/%Y}"


class InstalacaoLocal(models.Model):
    identificador = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    empresa = models.ForeignKey("empresas.Empresa", on_delete=models.PROTECT, related_name="instalacoes_licenca")
    nome = models.CharField(max_length=120)
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    ativa = models.BooleanField(default=True)
    ultima_consulta_em = models.DateTimeField(null=True, blank=True)
    versao_sistema = models.CharField(max_length=40, blank=True)
    ip_ultimo_acesso = models.GenericIPAddressField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["empresa__nome_fantasia", "nome"]
        unique_together = ["empresa", "nome"]

    @staticmethod
    def hash_token(token):
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def emitir_token(self):
        token = secrets.token_urlsafe(40)
        self.token_hash = self.hash_token(token)
        return token

    def __str__(self):
        return f"{self.empresa} - {self.nome}"


class ConcessaoLicenca(models.Model):
    instalacao = models.OneToOneField(InstalacaoLocal, on_delete=models.CASCADE, related_name="concessao")
    status = models.CharField(max_length=20, choices=StatusContrato.choices)
    emitida_em = models.DateTimeField(default=timezone.now)
    valida_ate = models.DateTimeField()
    tolerancia_ate = models.DateTimeField(null=True, blank=True)
    assinatura = models.TextField()
    payload = models.JSONField(default=dict)
    atualizado_em = models.DateTimeField(auto_now=True)


class EstadoLicencaLocal(models.Model):
    empresa = models.OneToOneField("empresas.Empresa", on_delete=models.CASCADE, related_name="estado_licenca_local")
    status = models.CharField(max_length=20, choices=StatusContrato.choices, default=StatusContrato.ATIVO)
    valida_ate = models.DateTimeField(null=True, blank=True)
    tolerancia_ate = models.DateTimeField(null=True, blank=True)
    offline_ate = models.DateTimeField(null=True, blank=True)
    ultima_sincronizacao_em = models.DateTimeField(null=True, blank=True)
    proxima_fatura_vencimento = models.DateField(null=True, blank=True)
    valor_pendente = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    url_pagamento = models.URLField(blank=True)
    mensagem = models.TextField(blank=True)
    ultimo_erro = models.TextField(blank=True)
    assinatura = models.TextField(blank=True)
    liberacao_emergencial_ate = models.DateTimeField(null=True, blank=True)
    liberacao_emergencial_motivo = models.TextField(blank=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    @property
    def bloqueado(self):
        agora = timezone.now()
        if self.liberacao_emergencial_ate and agora <= self.liberacao_emergencial_ate:
            return False
        if self.offline_ate and agora > self.offline_ate:
            return True
        if self.status not in {StatusContrato.SUSPENSO, StatusContrato.CANCELADO}:
            return False
        return not self.tolerancia_ate or agora > self.tolerancia_ate

    @property
    def mensagem_operacional(self):
        if self.offline_ate and timezone.now() > self.offline_ate:
            return "A instalação local não conseguiu renovar a licença dentro do prazo offline. Verifique a internet ou contate a Deigo Tecnologia."
        return self.mensagem


class DesafioLiberacaoLocal(models.Model):
    identificador = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    empresa = models.ForeignKey("empresas.Empresa", on_delete=models.CASCADE, related_name="desafios_licenca")
    nonce_hash = models.CharField(max_length=64, unique=True, editable=False)
    criado_em = models.DateTimeField(auto_now_add=True)
    expira_em = models.DateTimeField()
    usado_em = models.DateTimeField(null=True, blank=True)


class AutorizacaoEmergencial(models.Model):
    identificador = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    instalacao = models.ForeignKey(InstalacaoLocal, on_delete=models.PROTECT, related_name="autorizacoes_emergenciais")
    desafio_id = models.UUIDField(unique=True)
    nonce_hash = models.CharField(max_length=64)
    motivo = models.TextField()
    emitida_por = models.ForeignKey(
        "auth.User",
        on_delete=models.PROTECT,
        related_name="autorizacoes_licenca_emitidas",
    )
    emitida_em = models.DateTimeField(default=timezone.now)
    valida_ate = models.DateTimeField()
    usada_em = models.DateTimeField(null=True, blank=True)
    reconciliada_em = models.DateTimeField(null=True, blank=True)
    assinatura = models.TextField()
    ip_emissao = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-emitida_em"]


class LiberacaoEmergencialLocal(models.Model):
    autorizacao_id = models.UUIDField(unique=True)
    empresa = models.ForeignKey("empresas.Empresa", on_delete=models.PROTECT, related_name="liberacoes_emergenciais")
    desafio = models.OneToOneField(DesafioLiberacaoLocal, on_delete=models.PROTECT, related_name="liberacao")
    instalacao_id = models.UUIDField()
    motivo = models.TextField()
    emitida_em = models.DateTimeField()
    valida_ate = models.DateTimeField()
    aplicada_em = models.DateTimeField(default=timezone.now)
    sincronizada_em = models.DateTimeField(null=True, blank=True)
    assinatura = models.TextField()

    class Meta:
        ordering = ["-aplicada_em"]

class EventoWebhookAsaas(models.Model):
    evento_id = models.CharField(max_length=120, unique=True)
    tipo = models.CharField(max_length=80)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=20, choices=StatusEventoCobranca.choices, default=StatusEventoCobranca.PENDENTE)
    erro = models.TextField(blank=True)
    recebido_em = models.DateTimeField(auto_now_add=True)
    processado_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["recebido_em"]