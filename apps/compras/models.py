from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class StatusEntradaCompra(models.TextChoices):
    RASCUNHO = "RASCUNHO", "Rascunho"
    FINALIZADA = "FINALIZADA", "Finalizada"
    CANCELADA = "CANCELADA", "Cancelada"


class StatusPedidoCompra(models.TextChoices):
    RASCUNHO = "RASCUNHO", "Rascunho"
    ENVIADO = "ENVIADO", "Enviado ao fornecedor"
    CONVERTIDO = "CONVERTIDO", "Entrada de compra gerada"
    CANCELADO = "CANCELADO", "Cancelado"


class StatusCotacaoCompra(models.TextChoices):
    RASCUNHO = "RASCUNHO", "Rascunho"
    ABERTA = "ABERTA", "Aberta para propostas"
    ENCERRADA = "ENCERRADA", "Encerrada com pedido"
    CANCELADA = "CANCELADA", "Cancelada"


class CotacaoCompra(models.Model):
    filial = models.ForeignKey("empresas.Filial", on_delete=models.PROTECT, related_name="cotacoes_compra")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="cotacoes_compra")
    referencia = models.CharField(max_length=80, blank=True)
    validade = models.DateField(null=True, blank=True)
    observacoes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=StatusCotacaoCompra.choices, default=StatusCotacaoCompra.RASCUNHO)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Cotacao {self.id} - {self.referencia or self.filial}"


class ItemCotacaoCompra(models.Model):
    cotacao = models.ForeignKey(CotacaoCompra, on_delete=models.CASCADE, related_name="itens")
    produto = models.ForeignKey("produtos.Produto", on_delete=models.PROTECT, related_name="itens_cotacao_compra")
    quantidade = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001"))],
    )

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(fields=["cotacao", "produto"], name="compras_cotacao_produto_unico"),
        ]

    def __str__(self):
        return f"{self.quantidade} x {self.produto}"


class RespostaCotacaoFornecedor(models.Model):
    cotacao = models.ForeignKey(CotacaoCompra, on_delete=models.CASCADE, related_name="respostas")
    fornecedor = models.ForeignKey("fornecedores.Fornecedor", on_delete=models.PROTECT, related_name="respostas_cotacao")
    prazo_entrega_dias = models.PositiveIntegerField(default=0)
    observacoes = models.TextField(blank=True)
    selecionada = models.BooleanField(default=False)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="respostas_cotacao")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["fornecedor__razao_social"]
        constraints = [
            models.UniqueConstraint(fields=["cotacao", "fornecedor"], name="compras_cotacao_fornecedor_unico"),
        ]

    @property
    def total_proposto(self):
        return sum(
            (
                preco.item.quantidade * preco.custo_unitario
                for preco in self.precos.all()
                if preco.disponivel and preco.custo_unitario is not None
            ),
            Decimal("0.00"),
        )

    @property
    def proposta_completa(self):
        precos = list(self.precos.all())
        return (
            len(precos) == self.cotacao.itens.count()
            and all(preco.disponivel and preco.custo_unitario is not None for preco in precos)
        )

    def __str__(self):
        return f"{self.fornecedor} - cotacao {self.cotacao_id}"


class PrecoRespostaCotacao(models.Model):
    resposta = models.ForeignKey(RespostaCotacaoFornecedor, on_delete=models.CASCADE, related_name="precos")
    item = models.ForeignKey(ItemCotacaoCompra, on_delete=models.CASCADE, related_name="precos_fornecedores")
    disponivel = models.BooleanField(default=True)
    custo_unitario = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ["item_id"]
        constraints = [
            models.UniqueConstraint(fields=["resposta", "item"], name="compras_resposta_item_unico"),
        ]

    @property
    def total_proposto(self):
        if not self.disponivel or self.custo_unitario is None:
            return None
        return self.item.quantidade * self.custo_unitario

    def __str__(self):
        return f"{self.resposta.fornecedor} - {self.item.produto}"


class PedidoCompra(models.Model):
    cotacao_origem = models.OneToOneField(
        CotacaoCompra,
        on_delete=models.PROTECT,
        related_name="pedido_gerado",
        null=True,
        blank=True,
    )
    fornecedor = models.ForeignKey("fornecedores.Fornecedor", on_delete=models.PROTECT, related_name="pedidos_compra")
    filial = models.ForeignKey("empresas.Filial", on_delete=models.PROTECT, related_name="pedidos_compra")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="pedidos_compra")
    referencia = models.CharField(max_length=80, blank=True)
    previsao_entrega = models.DateField(null=True, blank=True)
    observacoes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=StatusPedidoCompra.choices, default=StatusPedidoCompra.RASCUNHO)
    total_previsto = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    enviado_em = models.DateTimeField(null=True, blank=True)
    cancelado_em = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Pedido {self.id} - {self.fornecedor}"


class ItemPedidoCompra(models.Model):
    pedido = models.ForeignKey(PedidoCompra, on_delete=models.CASCADE, related_name="itens")
    produto = models.ForeignKey("produtos.Produto", on_delete=models.PROTECT, related_name="itens_pedido_compra")
    quantidade = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001"))],
    )
    custo_unitario_previsto = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    total_previsto = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(fields=["pedido", "produto"], name="compras_pedido_produto_unico"),
        ]

    def __str__(self):
        return f"{self.quantidade} x {self.produto}"


class EntradaCompra(models.Model):
    pedido_origem = models.OneToOneField(
        PedidoCompra,
        on_delete=models.PROTECT,
        related_name="entrada_gerada",
        null=True,
        blank=True,
    )
    fornecedor = models.ForeignKey("fornecedores.Fornecedor", on_delete=models.PROTECT, related_name="entradas_compra")
    filial = models.ForeignKey("empresas.Filial", on_delete=models.PROTECT, related_name="entradas_compra")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="entradas_compra")
    numero_documento = models.CharField(max_length=80, blank=True)
    chave_acesso_xml = models.CharField(max_length=44, null=True, blank=True, unique=True)
    importada_xml_em = models.DateTimeField(null=True, blank=True)
    data_emissao = models.DateField(null=True, blank=True)
    vencimento_financeiro = models.DateField(null=True, blank=True)
    gerar_conta_financeira = models.BooleanField(default=True)
    data_recebimento = models.DateTimeField(auto_now_add=True)
    observacoes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=StatusEntradaCompra.choices, default=StatusEntradaCompra.RASCUNHO)
    total_produtos = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_documento = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-data_recebimento"]

    def __str__(self):
        return f"Entrada {self.id} - {self.fornecedor}"


class ItemEntradaCompra(models.Model):
    entrada = models.ForeignKey(EntradaCompra, on_delete=models.CASCADE, related_name="itens")
    produto = models.ForeignKey("produtos.Produto", on_delete=models.PROTECT, related_name="itens_compra")
    quantidade = models.DecimalField(max_digits=12, decimal_places=3)
    custo_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    atualizar_preco_custo = models.BooleanField(default=True)
    codigo_lote = models.CharField(max_length=60, blank=True)
    fabricacao = models.DateField(null=True, blank=True)
    validade = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.quantidade} x {self.produto}"

# Create your models here.
