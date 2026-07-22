from django.conf import settings
from django.db import models


class StatusVenda(models.TextChoices):
    ABERTA = "ABERTA", "Aberta"
    FINALIZADA = "FINALIZADA", "Finalizada"
    CANCELADA = "CANCELADA", "Cancelada"


class TipoDocumentoConsumidor(models.TextChoices):
    NAO_IDENTIFICADO = "NAO_IDENTIFICADO", "Nao identificado"
    CPF = "CPF", "CPF"
    CNPJ = "CNPJ", "CNPJ"
    ESTRANGEIRO = "ESTRANGEIRO", "Documento estrangeiro"


class StatusPreVenda(models.TextChoices):
    ABERTA = "ABERTA", "Aberta"
    CONVERTIDA = "CONVERTIDA", "Convertida"
    CANCELADA = "CANCELADA", "Cancelada"


class StatusPagamento(models.TextChoices):
    PENDENTE = "PENDENTE", "Pendente"
    CONFIRMADO = "CONFIRMADO", "Confirmado"
    RECUSADO = "RECUSADO", "Recusado"
    ESTORNO_PENDENTE = "ESTORNO_PENDENTE", "Estorno pendente"
    ESTORNADO = "ESTORNADO", "Estornado"


class FormaPagamento(models.Model):
    nome = models.CharField(max_length=100)
    tipo = models.CharField(max_length=50)
    conta_movimento_padrao = models.ForeignKey(
        "financeiro.ContaMovimentoFinanceiro",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="formas_pagamento_padrao",
    )
    ativo = models.BooleanField(default=True)
    permite_troco = models.BooleanField(default=False)
    exige_autorizacao = models.BooleanField(default=False)

    class Meta:
        ordering = ["nome"]

    def __str__(self):
        return self.nome


class Venda(models.Model):
    filial = models.ForeignKey("empresas.Filial", on_delete=models.PROTECT, related_name="vendas")
    caixa = models.ForeignKey("pdv.Caixa", on_delete=models.PROTECT, related_name="vendas")
    cliente = models.ForeignKey("clientes.Cliente", on_delete=models.PROTECT, related_name="vendas", null=True, blank=True)
    documento_consumidor_tipo = models.CharField(max_length=20, choices=TipoDocumentoConsumidor.choices, default=TipoDocumentoConsumidor.NAO_IDENTIFICADO)
    documento_consumidor = models.CharField(max_length=32, blank=True)
    observacao_fiscal_consumidor = models.CharField(max_length=255, blank=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="vendas")
    total_bruto = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    desconto = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_liquido = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=StatusVenda.choices, default=StatusVenda.ABERTA)
    data = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-data"]

    def __str__(self):
        return f"Venda {self.id} - {self.total_liquido}"


class ItemVenda(models.Model):
    venda = models.ForeignKey(Venda, on_delete=models.PROTECT, related_name="itens")
    produto = models.ForeignKey("produtos.Produto", on_delete=models.PROTECT)
    quantidade = models.DecimalField(max_digits=12, decimal_places=3)
    preco_unitario_venda = models.DecimalField(max_digits=10, decimal_places=2)
    desconto = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    custo_unitario_no_momento = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    def __str__(self):
        return f"{self.quantidade} x {self.produto}"


class DevolucaoVenda(models.Model):
    venda = models.ForeignKey(Venda, on_delete=models.PROTECT, related_name="devolucoes")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="devolucoes_venda")
    motivo = models.CharField(max_length=255)
    valor_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    data = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-data"]

    def __str__(self):
        return f"Devolucao {self.id} - Venda {self.venda_id}"


class ItemDevolucaoVenda(models.Model):
    devolucao = models.ForeignKey(DevolucaoVenda, on_delete=models.PROTECT, related_name="itens")
    item_venda = models.ForeignKey(ItemVenda, on_delete=models.PROTECT, related_name="itens_devolucao")
    produto = models.ForeignKey("produtos.Produto", on_delete=models.PROTECT)
    quantidade = models.DecimalField(max_digits=12, decimal_places=3)
    valor_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    valor_total = models.DecimalField(max_digits=12, decimal_places=2)

    def __str__(self):
        return f"{self.quantidade} x {self.produto}"


class PagamentoVenda(models.Model):
    venda = models.ForeignKey(Venda, on_delete=models.PROTECT, related_name="pagamentos")
    forma_pagamento = models.ForeignKey(FormaPagamento, on_delete=models.PROTECT)
    valor = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=30, choices=StatusPagamento.choices, default=StatusPagamento.CONFIRMADO)
    transacao_externa_id = models.CharField(max_length=120, blank=True)
    nsu = models.CharField(max_length=60, blank=True)
    codigo_autorizacao = models.CharField(max_length=60, blank=True)
    mensagem_processadora = models.CharField(max_length=255, blank=True)
    motivo_estorno = models.CharField(max_length=255, blank=True)
    estorno_solicitado_em = models.DateTimeField(null=True, blank=True)
    estornado_em = models.DateTimeField(null=True, blank=True)
    data = models.DateTimeField(auto_now_add=True)


class PreVenda(models.Model):
    filial = models.ForeignKey("empresas.Filial", on_delete=models.PROTECT, related_name="pre_vendas")
    cliente = models.ForeignKey("clientes.Cliente", on_delete=models.PROTECT, related_name="pre_vendas", null=True, blank=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="pre_vendas")
    venda = models.OneToOneField(Venda, on_delete=models.PROTECT, related_name="pre_venda_origem", null=True, blank=True)
    total_bruto = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    desconto = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_liquido = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=StatusPreVenda.choices, default=StatusPreVenda.ABERTA)
    observacao = models.TextField(blank=True)
    validade = models.DateField(null=True, blank=True)
    criada_em = models.DateTimeField(auto_now_add=True)
    atualizada_em = models.DateTimeField(auto_now=True)
    convertida_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-criada_em"]

    def __str__(self):
        return f"DAV {self.id} - {self.total_liquido}"


class ItemPreVenda(models.Model):
    pre_venda = models.ForeignKey(PreVenda, on_delete=models.PROTECT, related_name="itens")
    produto = models.ForeignKey("produtos.Produto", on_delete=models.PROTECT)
    quantidade = models.DecimalField(max_digits=12, decimal_places=3)
    preco_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    desconto = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2)

    def __str__(self):
        return f"{self.quantidade} x {self.produto}"

# Create your models here.
