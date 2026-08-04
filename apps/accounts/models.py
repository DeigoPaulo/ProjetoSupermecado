import hashlib
import hmac

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import models
from django.utils import timezone


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

class TipoCredencialAutorizacao(models.TextChoices):
    NFC = "NFC", "NFC / MIFARE"
    MAGNETICA = "MAGNETICA", "Cartão magnético"
    CODIGO_BARRAS = "CODIGO_BARRAS", "Código de barras"


class CredencialAutorizacao(models.Model):
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="credenciais_autorizacao",
    )
    tipo = models.CharField(max_length=20, choices=TipoCredencialAutorizacao.choices)
    nome = models.CharField(max_length=80, help_text="Ex.: crachá do gerente ou cartão do supervisor.")
    identificador_hash = models.CharField(max_length=64, unique=True, editable=False)
    pin_hash = models.CharField(max_length=128, blank=True, editable=False)
    valida_ate = models.DateTimeField(null=True, blank=True)
    ativa = models.BooleanField(default=True)
    criada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="credenciais_autorizacao_criadas",
    )
    criada_em = models.DateTimeField(auto_now_add=True)
    atualizada_em = models.DateTimeField(auto_now=True)
    ultimo_uso_em = models.DateTimeField(null=True, blank=True)
    revogada_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-ativa", "usuario__username", "nome"]
        verbose_name = "Credencial de autorização"
        verbose_name_plural = "Credenciais de autorização"

    @staticmethod
    def calcular_hash(identificador):
        valor = str(identificador or "").strip()
        if not valor:
            return ""
        segredo = getattr(settings, "AUTHORIZATION_CREDENTIAL_PEPPER", "") or settings.SECRET_KEY
        return hmac.new(
            segredo.encode("utf-8"),
            f"supervisor-card-v1:{valor}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def definir_identificador(self, identificador):
        self.identificador_hash = self.calcular_hash(identificador)

    def definir_pin(self, pin):
        self.pin_hash = make_password(str(pin)) if pin else ""

    def validar_pin(self, pin):
        return not self.pin_hash or check_password(str(pin or ""), self.pin_hash)

    @property
    def vigente(self):
        return self.ativa and (self.valida_ate is None or self.valida_ate > timezone.now())

    def revogar(self):
        self.ativa = False
        self.revogada_em = timezone.now()
        self.save(update_fields=["ativa", "revogada_em", "atualizada_em"])

    def __str__(self):
        return f"{self.nome} - {self.usuario}"


class UsoCredencialAutorizacao(models.Model):
    credencial = models.ForeignKey(CredencialAutorizacao, on_delete=models.PROTECT, related_name="usos")
    acao = models.CharField(max_length=40, blank=True)
    supervisor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="autorizacoes_por_credencial",
    )
    operador = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="solicitacoes_autorizadas_por_credencial",
    )
    caminho = models.CharField(max_length=255, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    usado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-usado_em"]
        verbose_name = "Uso de credencial de autorização"
        verbose_name_plural = "Usos de credenciais de autorização"
