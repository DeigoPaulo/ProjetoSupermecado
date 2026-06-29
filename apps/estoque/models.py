from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction


class TipoMovimentacaoEstoque(models.TextChoices):
    ENTRADA = "ENTRADA", "Entrada"
    SAIDA = "SAIDA", "Saida"
    AJUSTE = "AJUSTE", "Ajuste"
    VENDA = "VENDA", "Venda"
    DEVOLUCAO = "DEVOLUCAO", "Devolucao"
    PERDA = "PERDA", "Perda"
    RESERVA = "RESERVA", "Reserva"
    LIBERACAO_RESERVA = "LIBERACAO_RESERVA", "Liberacao de reserva"


class Estoque(models.Model):
    produto = models.ForeignKey("produtos.Produto", on_delete=models.PROTECT, related_name="estoques")
    filial = models.ForeignKey("empresas.Filial", on_delete=models.PROTECT, related_name="estoques")
    quantidade_atual = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    quantidade_reservada = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["produto", "filial"]
        ordering = ["produto__nome", "filial__nome"]

    @property
    def quantidade_disponivel(self):
        return self.quantidade_atual - self.quantidade_reservada

    def clean(self):
        if self.quantidade_atual < 0:
            raise ValidationError("Quantidade atual nao pode ser negativa.")
        if self.quantidade_reservada < 0:
            raise ValidationError("Quantidade reservada nao pode ser negativa.")
        if self.quantidade_reservada > self.quantidade_atual:
            raise ValidationError("Quantidade reservada nao pode superar o estoque fisico.")

    def __str__(self):
        return f"{self.produto} / {self.filial}: {self.quantidade_disponivel}"


class MovimentacaoEstoque(models.Model):
    produto = models.ForeignKey("produtos.Produto", on_delete=models.PROTECT, related_name="movimentacoes")
    filial = models.ForeignKey("empresas.Filial", on_delete=models.PROTECT, related_name="movimentacoes_estoque")
    tipo = models.CharField(max_length=30, choices=TipoMovimentacaoEstoque.choices)
    quantidade = models.DecimalField(max_digits=12, decimal_places=3)
    motivo = models.CharField(max_length=255, blank=True)
    referencia = models.CharField(max_length=120, blank=True)
    custo_unitario = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    custo_total = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)
    data = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-data"]

    def __str__(self):
        return f"{self.tipo} {self.quantidade} - {self.produto}"


class StatusInventario(models.TextChoices):
    ABERTO = "ABERTO", "Aberto"
    APLICADO = "APLICADO", "Aplicado"
    CANCELADO = "CANCELADO", "Cancelado"


class InventarioEstoque(models.Model):
    filial = models.ForeignKey("empresas.Filial", on_delete=models.PROTECT, related_name="inventarios")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="inventarios")
    descricao = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=StatusInventario.choices, default=StatusInventario.ABERTO)
    criado_em = models.DateTimeField(auto_now_add=True)
    aplicado_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-criado_em"]

    def __str__(self):
        return f"Inventario {self.id} - {self.filial}"


class ItemInventarioEstoque(models.Model):
    inventario = models.ForeignKey(InventarioEstoque, on_delete=models.CASCADE, related_name="itens")
    produto = models.ForeignKey("produtos.Produto", on_delete=models.PROTECT, related_name="itens_inventario")
    quantidade_sistema = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    quantidade_contada = models.DecimalField(max_digits=12, decimal_places=3)
    diferenca = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    observacao = models.CharField(max_length=255, blank=True)

    class Meta:
        unique_together = ["inventario", "produto"]
        ordering = ["produto__nome"]

    def __str__(self):
        return f"{self.produto}: {self.diferenca}"


class TipoPerdaEstoque(models.TextChoices):
    VENCIMENTO = "VENCIMENTO", "Vencimento"
    AVARIA = "AVARIA", "Avaria"
    QUEBRA = "QUEBRA", "Quebra"
    EXTRAVIO_FURTO = "EXTRAVIO_FURTO", "Extravio/furto"
    CONSUMO_INTERNO = "CONSUMO_INTERNO", "Consumo interno"
    DEVOLUCAO_NAO_REAPROVEITAVEL = "DEVOLUCAO_NAO_REAPROVEITAVEL", "Devolucao nao reaproveitavel"
    OUTROS = "OUTROS", "Outros"


class PerdaEstoque(models.Model):
    produto = models.ForeignKey("produtos.Produto", on_delete=models.PROTECT, related_name="perdas")
    filial = models.ForeignKey("empresas.Filial", on_delete=models.PROTECT, related_name="perdas_estoque")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="perdas_estoque")
    tipo = models.CharField(max_length=40, choices=TipoPerdaEstoque.choices)
    quantidade = models.DecimalField(max_digits=12, decimal_places=3)
    motivo = models.CharField(max_length=255)
    custo_unitario_no_momento = models.DecimalField(max_digits=10, decimal_places=2)
    preco_venda_no_momento = models.DecimalField(max_digits=10, decimal_places=2)
    valor_custo_estimado = models.DecimalField(max_digits=12, decimal_places=2)
    valor_venda_estimado = models.DecimalField(max_digits=12, decimal_places=2)
    data = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-data"]

    def __str__(self):
        return f"{self.tipo} - {self.produto} ({self.quantidade})"


def movimentar_estoque(*, produto, filial, tipo, quantidade, usuario=None, motivo="", referencia="", custo_unitario=None):
    with transaction.atomic():
        estoque, _ = Estoque.objects.select_for_update().get_or_create(produto=produto, filial=filial)

        if tipo in [TipoMovimentacaoEstoque.SAIDA, TipoMovimentacaoEstoque.VENDA, TipoMovimentacaoEstoque.PERDA]:
            if estoque.quantidade_disponivel < quantidade:
                raise ValidationError("Estoque insuficiente.")
            estoque.quantidade_atual -= quantidade
        elif tipo == TipoMovimentacaoEstoque.RESERVA:
            if estoque.quantidade_disponivel < quantidade:
                raise ValidationError("Estoque insuficiente para reserva.")
            estoque.quantidade_reservada += quantidade
        elif tipo == TipoMovimentacaoEstoque.LIBERACAO_RESERVA:
            if estoque.quantidade_reservada < quantidade:
                raise ValidationError("Reserva insuficiente para liberacao.")
            estoque.quantidade_reservada -= quantidade
        else:
            estoque.quantidade_atual += quantidade

        estoque.full_clean()
        estoque.save()

        custo_total = None
        if custo_unitario is not None:
            custo_total = custo_unitario * quantidade

        return MovimentacaoEstoque.objects.create(
            produto=produto,
            filial=filial,
            tipo=tipo,
            quantidade=quantidade,
            motivo=motivo,
            referencia=referencia,
            custo_unitario=custo_unitario,
            custo_total=custo_total,
            usuario=usuario,
        )

# Create your models here.
