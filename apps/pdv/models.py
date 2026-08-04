import secrets
import uuid

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import models


class StatusCaixa(models.TextChoices):
    ABERTO = "ABERTO", "Aberto"
    FECHADO = "FECHADO", "Fechado"
    CONFERIDO = "CONFERIDO", "Conferido"
    CANCELADO = "CANCELADO", "Cancelado"


class StatusAcessoPdvNuvem(models.TextChoices):
    PENDENTE = "PENDENTE", "Pendente"
    APROVADO = "APROVADO", "Aprovado"
    RECUSADO = "RECUSADO", "Recusado"
    EXPIRADO = "EXPIRADO", "Expirado"


class ProvedorTef(models.TextChoices):
    NAO_CONFIGURADO = "NAO_CONFIGURADO", "Não configurado"
    SITEF = "SITEF", "SiTef / Software Express"
    CIELO = "CIELO", "Cielo"
    STONE = "STONE", "Stone"
    GETNET = "GETNET", "Getnet"
    PAGBANK = "PAGBANK", "PagBank / PagSeguro"
    REDE = "REDE", "Rede"
    OUTRO = "OUTRO", "Outro adaptador"


class ModoIntegracaoTef(models.TextChoices):
    DESKTOP_BRIDGE = "DESKTOP_BRIDGE", "App desktop / bridge local"
    API = "API", "API direta da operadora"
    POS_INTEGRADO = "POS_INTEGRADO", "POS/SmartPOS integrado"
    MANUAL = "MANUAL", "Manual sem retorno automático"


class ProtocoloBalanca(models.TextChoices):
    NAO_CONFIGURADO = "NAO_CONFIGURADO", "Não configurado"
    SERIAL = "SERIAL", "Serial RS-232/USB"
    TCP_IP = "TCP_IP", "TCP/IP"
    ARQUIVO_TXT = "ARQUIVO_TXT", "Arquivo texto local"
    OUTRO = "OUTRO", "Outro protocolo"


class StatusLicencaTerminal(models.TextChoices):
    PENDENTE = "PENDENTE", "Pendente"
    LIBERADA = "LIBERADA", "Liberada"
    BLOQUEADA = "BLOQUEADA", "Bloqueada"
    CANCELADA = "CANCELADA", "Cancelada"


class CanalAtualizacaoPdv(models.TextChoices):
    ESTAVEL = "ESTAVEL", "Estavel"
    PILOTO = "PILOTO", "Piloto"


class TerminalPdv(models.Model):
    identificador = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    filial = models.ForeignKey("empresas.Filial", on_delete=models.PROTECT, related_name="terminais_pdv")
    nome = models.CharField(max_length=80)
    descricao = models.CharField(max_length=255, blank=True)
    chave_api_hash = models.CharField(max_length=128, blank=True, editable=False)
    chave_api_prefixo = models.CharField(max_length=12, blank=True, editable=False)
    permite_modo_offline = models.BooleanField(default=True)
    emite_documento_fiscal = models.BooleanField(default=True)
    provedor_tef = models.CharField(max_length=30, choices=ProvedorTef.choices, default=ProvedorTef.NAO_CONFIGURADO)
    modo_integracao_tef = models.CharField(max_length=30, choices=ModoIntegracaoTef.choices, default=ModoIntegracaoTef.DESKTOP_BRIDGE)
    usa_balanca = models.BooleanField(default=False)
    protocolo_balanca = models.CharField(max_length=30, choices=ProtocoloBalanca.choices, default=ProtocoloBalanca.NAO_CONFIGURADO)
    porta_balanca = models.CharField(max_length=80, blank=True)
    modelo_balanca = models.CharField(max_length=120, blank=True)
    status_licenca = models.CharField(max_length=20, choices=StatusLicencaTerminal.choices, default=StatusLicencaTerminal.PENDENTE)
    licenca_liberada_em = models.DateTimeField(null=True, blank=True)
    licenca_liberada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="terminais_pdv_liberados")
    observacao_licenca = models.CharField(max_length=255, blank=True)
    canal_atualizacao = models.CharField(max_length=20, choices=CanalAtualizacaoPdv.choices, default=CanalAtualizacaoPdv.ESTAVEL)
    bloquear_atualizacoes = models.BooleanField(default=False)
    ativo = models.BooleanField(default=True)
    ultima_conexao = models.DateTimeField(null=True, blank=True)
    ultimo_ip = models.GenericIPAddressField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["filial__nome", "nome"]
        unique_together = ["filial", "nome"]

    def __str__(self):
        return f"{self.nome} - {self.filial}"

    def gerar_chave_api(self):
        chave = secrets.token_urlsafe(32)
        self.chave_api_hash = make_password(chave)
        self.chave_api_prefixo = chave[:8]
        return chave

    def validar_chave_api(self, chave):
        return bool(chave and self.chave_api_hash and check_password(chave, self.chave_api_hash))

    def balanca_configuracao(self):
        leitura_automatica = self.usa_balanca and self.protocolo_balanca != ProtocoloBalanca.NAO_CONFIGURADO
        return {
            "contrato": "pdv_scale_v1",
            "opcional": True,
            "habilitada": self.usa_balanca,
            "protocolo": self.protocolo_balanca,
            "porta": self.porta_balanca,
            "modelo": self.modelo_balanca,
            "leitura_automatica": leitura_automatica,
            "unidade_padrao": "KG",
            "precisao_decimal": 3,
            "timeout_ms": 3000,
            "baudrate": 9600,
            "bytesize": 8,
            "paridade": "N",
            "stopbits": "1",
            "comando_leitura": "",
            "terminador": "\\r\\n",
            "fator_conversao": "1",
            "fallback_manual": True,
            "status_operacional": "habilitada" if leitura_automatica else "manual",
        }

    @property
    def licenca_liberada(self):
        return self.ativo and self.status_licenca == StatusLicencaTerminal.LIBERADA


class EventoDispositivoTerminal(models.Model):
    terminal = models.ForeignKey(TerminalPdv, on_delete=models.CASCADE, related_name="eventos_dispositivo")
    evento_id = models.CharField(max_length=80, null=True, blank=True)
    tipo = models.CharField(max_length=40)
    status = models.CharField(max_length=40, blank=True)
    mensagem = models.CharField(max_length=255, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    ocorrido_em = models.DateTimeField(null=True, blank=True)
    recebido_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-recebido_em"]
        indexes = [
            models.Index(fields=["terminal", "-recebido_em"]),
            models.Index(fields=["tipo", "status"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["terminal", "evento_id"], name="uniq_evento_dispositivo_terminal"),
        ]

    def __str__(self):
        return f"{self.terminal} - {self.tipo} - {self.status or 'evento'}"


class Caixa(models.Model):
    filial = models.ForeignKey("empresas.Filial", on_delete=models.PROTECT, related_name="caixas")
    usuario_abertura = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="caixas_abertos")
    data_abertura = models.DateTimeField(auto_now_add=True)
    valor_inicial = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    usuario_fechamento = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="caixas_fechados", null=True, blank=True)
    data_fechamento = models.DateTimeField(null=True, blank=True)
    valor_final = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    usuario_conferencia = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="caixas_conferidos", null=True, blank=True)
    data_conferencia = models.DateTimeField(null=True, blank=True)
    valor_conferido = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    observacao_conferencia = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=StatusCaixa.choices, default=StatusCaixa.ABERTO)

    class Meta:
        ordering = ["-data_abertura"]

    def __str__(self):
        return f"Caixa {self.id} - {self.filial} - {self.status}"


class Sangria(models.Model):
    caixa = models.ForeignKey(Caixa, on_delete=models.PROTECT, related_name="sangrias")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    valor = models.DecimalField(max_digits=12, decimal_places=2)
    motivo = models.CharField(max_length=255)
    data = models.DateTimeField(auto_now_add=True)


class Suprimento(models.Model):
    caixa = models.ForeignKey(Caixa, on_delete=models.PROTECT, related_name="suprimentos")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    valor = models.DecimalField(max_digits=12, decimal_places=2)
    motivo = models.CharField(max_length=255)
    data = models.DateTimeField(auto_now_add=True)


class AcessoPdvNuvem(models.Model):
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="solicitacoes_pdv_nuvem")
    filial = models.ForeignKey("empresas.Filial", on_delete=models.PROTECT, related_name="solicitacoes_pdv_nuvem", null=True, blank=True)
    status = models.CharField(max_length=20, choices=StatusAcessoPdvNuvem.choices, default=StatusAcessoPdvNuvem.PENDENTE)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    justificativa = models.CharField(max_length=255, blank=True)
    decidido_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="decisoes_pdv_nuvem", null=True, blank=True)
    decidido_em = models.DateTimeField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-criado_em"]
        indexes = [
            models.Index(fields=["usuario", "status"]),
            models.Index(fields=["filial", "status"]),
        ]

    def __str__(self):
        return f"Acesso PDV nuvem {self.usuario} - {self.status}"

# Create your models here.
