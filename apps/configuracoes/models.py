from django.conf import settings
from django.db import models


class ModeloPapel(models.TextChoices):
    BOBINA_58 = "58MM", "Bobina 58 mm"
    BOBINA_80 = "80MM", "Bobina 80 mm"
    A4 = "A4", "A4"


class TipoDocumentoImpressao(models.TextChoices):
    CUPOM_NAO_FISCAL = "CUPOM_NAO_FISCAL", "Cupom não fiscal"
    CUPOM_FISCAL = "CUPOM_FISCAL", "Cupom fiscal"
    PEDIDO_SEPARACAO = "PEDIDO_SEPARACAO", "Pedido de separação"
    ETIQUETA = "ETIQUETA", "Etiqueta"
    RELATORIO = "RELATORIO", "Relatório"
    FECHAMENTO_CAIXA = "FECHAMENTO_CAIXA", "Fechamento de caixa"


class LinguagemImpressora(models.TextChoices):
    WINDOWS = "WINDOWS", "Driver do Windows"
    ZPL = "ZPL", "ZPL (Zebra)"
    EPL = "EPL", "EPL (Zebra/Eltron)"
    PPLA = "PPLA", "PPLA (Argox)"
    PPLB = "PPLB", "PPLB (Argox)"


class TipoMidiaEtiqueta(models.TextChoices):
    GAP = "GAP", "Etiqueta com gap"
    CONTINUA = "CONTINUA", "Mídia contínua"
    MARCA_PRETA = "MARCA_PRETA", "Marca preta"


class OrientacaoEtiqueta(models.TextChoices):
    RETRATO = "RETRATO", "Retrato"
    PAISAGEM = "PAISAGEM", "Paisagem"


class ConfiguracaoImpressao(models.Model):
    empresa = models.ForeignKey("empresas.Empresa", on_delete=models.PROTECT, related_name="configuracoes_impressao")
    filial = models.ForeignKey("empresas.Filial", on_delete=models.PROTECT, related_name="configuracoes_impressao", null=True, blank=True)
    tipo_documento = models.CharField(max_length=40, choices=TipoDocumentoImpressao.choices)
    modelo_papel = models.CharField(max_length=10, choices=ModeloPapel.choices, default=ModeloPapel.BOBINA_80)
    exibir_logo = models.BooleanField(default=True)
    tamanho_fonte = models.PositiveIntegerField(default=10)
    margem_superior_mm = models.PositiveIntegerField(default=5)
    margem_inferior_mm = models.PositiveIntegerField(default=5)
    margem_esquerda_mm = models.PositiveIntegerField(default=5)
    margem_direita_mm = models.PositiveIntegerField(default=5)
    mensagem_rodape = models.TextField(blank=True)
    impressora_padrao = models.CharField(max_length=255, blank=True)
    impressao_automatica = models.BooleanField(default=False)
    gaveta_automatica = models.BooleanField(default=False)
    abrir_gaveta_em_dinheiro = models.BooleanField(default=True)
    abrir_gaveta_em_movimento_caixa = models.BooleanField(default=True)
    numero_vias = models.PositiveIntegerField(default=1)
    largura_etiqueta_mm = models.DecimalField(max_digits=6, decimal_places=2, default=110, blank=True)
    altura_etiqueta_mm = models.DecimalField(max_digits=6, decimal_places=2, default=30, blank=True)
    gap_horizontal_mm = models.DecimalField(max_digits=5, decimal_places=2, default=2, blank=True)
    gap_vertical_mm = models.DecimalField(max_digits=5, decimal_places=2, default=2, blank=True)
    colunas_etiqueta = models.PositiveSmallIntegerField(default=1, blank=True)
    dpi_impressora = models.PositiveSmallIntegerField(default=203, blank=True)
    densidade_impressao = models.PositiveSmallIntegerField(default=8, blank=True)
    velocidade_impressao = models.PositiveSmallIntegerField(default=4, blank=True)
    tipo_midia_etiqueta = models.CharField(max_length=20, choices=TipoMidiaEtiqueta.choices, default=TipoMidiaEtiqueta.GAP, blank=True)
    linguagem_impressora = models.CharField(max_length=10, choices=LinguagemImpressora.choices, default=LinguagemImpressora.WINDOWS, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ["empresa", "filial", "tipo_documento"]

    def __str__(self):
        return f"{self.empresa} - {self.tipo_documento}"


class ModeloEtiqueta(models.Model):
    configuracao = models.ForeignKey(ConfiguracaoImpressao, on_delete=models.CASCADE, related_name="modelos_etiqueta")
    terminal = models.ForeignKey("pdv.TerminalPdv", on_delete=models.PROTECT, related_name="modelos_etiqueta", null=True, blank=True)
    nome = models.CharField(max_length=80)
    largura_mm = models.DecimalField(max_digits=6, decimal_places=2, default=110)
    altura_mm = models.DecimalField(max_digits=6, decimal_places=2, default=30)
    gap_horizontal_mm = models.DecimalField(max_digits=5, decimal_places=2, default=2)
    gap_vertical_mm = models.DecimalField(max_digits=5, decimal_places=2, default=2)
    colunas = models.PositiveSmallIntegerField(default=1)
    orientacao = models.CharField(max_length=10, choices=OrientacaoEtiqueta.choices, default=OrientacaoEtiqueta.PAISAGEM)
    padrao = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["configuracao__empresa_id", "configuracao__filial_id", "nome"]
        unique_together = ["configuracao", "nome"]

    def __str__(self):
        return f"{self.nome} - {self.largura_mm} x {self.altura_mm} mm"


class ResultadoHomologacaoServidor(models.TextChoices):
    APROVADA = "APROVADA", "Aprovada"
    REPROVADA = "REPROVADA", "Reprovada"


class HomologacaoServidorLocal(models.Model):
    maquina = models.CharField(max_length=120)
    sistema_operacional = models.CharField(max_length=120)
    versao_artefato = models.CharField(max_length=50)
    hash_evidencia = models.CharField(max_length=64, unique=True)
    resultado = models.CharField(max_length=12, choices=ResultadoHomologacaoServidor.choices)
    observacoes = models.TextField(blank=True)
    itens_validados = models.JSONField(default=list, blank=True)
    registrada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="homologacoes_servidor_local",
    )
    criada_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criada_em", "-id"]
        verbose_name = "homologação de servidor local"
        verbose_name_plural = "homologações de servidor local"

    @property
    def itens_validados_labels(self):
        from .homologation import rotulos_itens_homologacao

        return rotulos_itens_homologacao(self.itens_validados)

    def __str__(self):
        return f"{self.maquina} - {self.get_resultado_display()} - {self.versao_artefato}"

# Create your models here.
