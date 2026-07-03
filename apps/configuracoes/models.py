from django.db import models


class ModeloPapel(models.TextChoices):
    BOBINA_58 = "58MM", "Bobina 58 mm"
    BOBINA_80 = "80MM", "Bobina 80 mm"
    A4 = "A4", "A4"


class TipoDocumentoImpressao(models.TextChoices):
    CUPOM_NAO_FISCAL = "CUPOM_NAO_FISCAL", "Cupom nao fiscal"
    CUPOM_FISCAL = "CUPOM_FISCAL", "Cupom fiscal"
    PEDIDO_SEPARACAO = "PEDIDO_SEPARACAO", "Pedido de separacao"
    ETIQUETA = "ETIQUETA", "Etiqueta"
    RELATORIO = "RELATORIO", "Relatorio"
    FECHAMENTO_CAIXA = "FECHAMENTO_CAIXA", "Fechamento de caixa"


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
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ["empresa", "filial", "tipo_documento"]

    def __str__(self):
        return f"{self.empresa} - {self.tipo_documento}"

# Create your models here.
