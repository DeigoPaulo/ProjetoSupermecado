from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Sum
from django.utils import timezone


class TipoContaFinanceira(models.TextChoices):
    PAGAR = "PAGAR", "Conta a pagar"
    RECEBER = "RECEBER", "Conta a receber"


class StatusContaFinanceira(models.TextChoices):
    ABERTA = "ABERTA", "Aberta"
    PAGA = "PAGA", "Paga"
    CANCELADA = "CANCELADA", "Cancelada"


class TipoContaMovimento(models.TextChoices):
    CAIXA = "CAIXA", "Caixa fisico"
    BANCO = "BANCO", "Conta bancaria"
    PIX = "PIX", "Conta PIX"
    OUTRA = "OUTRA", "Outra"


class TipoLancamentoFinanceiro(models.TextChoices):
    ENTRADA = "ENTRADA", "Entrada"
    SAIDA = "SAIDA", "Saida"


class StatusExportacaoContabil(models.TextChoices):
    PENDENTE = "PENDENTE", "Pendente"
    ENVIADO = "ENVIADO", "Enviado"
    REJEITADO = "REJEITADO", "Rejeitado"
    ERRO = "ERRO", "Erro"


class CategoriaFinanceira(models.Model):
    nome = models.CharField(max_length=120, unique=True)
    tipo = models.CharField(max_length=20, choices=TipoContaFinanceira.choices)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["tipo", "nome"]

    def __str__(self):
        return self.nome


class ContaMovimentoFinanceiro(models.Model):
    filial = models.ForeignKey("empresas.Filial", on_delete=models.PROTECT, related_name="contas_movimento")
    nome = models.CharField(max_length=120)
    tipo = models.CharField(max_length=20, choices=TipoContaMovimento.choices)
    saldo_inicial = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    ativa = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["filial__nome", "nome"]
        constraints = [
            models.UniqueConstraint(fields=["filial", "nome"], name="financeiro_conta_movimento_unica")
        ]

    @property
    def saldo_atual(self):
        totais = self.lancamentos.values("tipo").annotate(total=Sum("valor"))
        por_tipo = {item["tipo"]: item["total"] for item in totais}
        return self.saldo_inicial + por_tipo.get(TipoLancamentoFinanceiro.ENTRADA, 0) - por_tipo.get(TipoLancamentoFinanceiro.SAIDA, 0)

    def __str__(self):
        return f"{self.filial} - {self.nome}"


class ContaFinanceira(models.Model):
    tipo = models.CharField(max_length=20, choices=TipoContaFinanceira.choices)
    status = models.CharField(max_length=20, choices=StatusContaFinanceira.choices, default=StatusContaFinanceira.ABERTA)
    descricao = models.CharField(max_length=255)
    categoria = models.ForeignKey(CategoriaFinanceira, on_delete=models.PROTECT, null=True, blank=True, related_name="contas")
    filial = models.ForeignKey("empresas.Filial", on_delete=models.PROTECT, related_name="contas_financeiras")
    fornecedor = models.ForeignKey("fornecedores.Fornecedor", on_delete=models.PROTECT, null=True, blank=True, related_name="contas_pagar")
    cliente = models.ForeignKey("clientes.Cliente", on_delete=models.PROTECT, null=True, blank=True, related_name="contas_receber")
    venda = models.ForeignKey("vendas.Venda", on_delete=models.PROTECT, null=True, blank=True, related_name="contas_financeiras")
    entrada_compra = models.ForeignKey("compras.EntradaCompra", on_delete=models.PROTECT, null=True, blank=True, related_name="contas_financeiras")
    valor = models.DecimalField(max_digits=12, decimal_places=2)
    vencimento = models.DateField()
    data_pagamento = models.DateField(null=True, blank=True)
    valor_pago = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    forma_pagamento = models.CharField(max_length=80, blank=True)
    conta_movimento = models.ForeignKey(ContaMovimentoFinanceiro, on_delete=models.PROTECT, null=True, blank=True, related_name="baixas")
    observacoes = models.TextField(blank=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="contas_financeiras")
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["status", "vencimento", "descricao"]

    def clean(self):
        if self.cliente_id and self.filial_id and self.cliente.empresa_id != self.filial.empresa_id:
            raise ValidationError({"cliente": "Cliente informado pertence a outra empresa."})
        if self.fornecedor_id and self.fornecedor.empresa_id and self.filial_id and self.fornecedor.empresa_id != self.filial.empresa_id:
            raise ValidationError({"fornecedor": "Fornecedor informado pertence a outra empresa."})
    @property
    def esta_vencida(self):
        return self.status == StatusContaFinanceira.ABERTA and self.vencimento < timezone.localdate()

    @property
    def saldo(self):
        return self.valor - (self.valor_pago or 0)

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.descricao}"


class TransferenciaFinanceira(models.Model):
    conta_origem = models.ForeignKey(
        ContaMovimentoFinanceiro,
        on_delete=models.PROTECT,
        related_name="transferencias_saida",
    )
    conta_destino = models.ForeignKey(
        ContaMovimentoFinanceiro,
        on_delete=models.PROTECT,
        related_name="transferencias_entrada",
    )
    valor = models.DecimalField(max_digits=14, decimal_places=2)
    data = models.DateField(default=timezone.localdate)
    descricao = models.CharField(max_length=255, blank=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="transferencias_financeiras")
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-data", "-criado_em"]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Transferencias financeiras nao podem ser alteradas.")
        if self.conta_origem_id == self.conta_destino_id:
            raise ValidationError("As contas de origem e destino devem ser diferentes.")
        if self.valor <= 0:
            raise ValidationError("Valor da transferencia deve ser maior que zero.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Transferencias financeiras nao podem ser excluidas.")

    def __str__(self):
        return f"Transferencia #{self.pk} - {self.conta_origem} para {self.conta_destino}"


class LancamentoFinanceiro(models.Model):
    conta = models.ForeignKey(ContaMovimentoFinanceiro, on_delete=models.PROTECT, related_name="lancamentos")
    tipo = models.CharField(max_length=20, choices=TipoLancamentoFinanceiro.choices)
    origem = models.CharField(max_length=40)
    descricao = models.CharField(max_length=255)
    valor = models.DecimalField(max_digits=14, decimal_places=2)
    data = models.DateField(default=timezone.localdate)
    conta_financeira = models.ForeignKey(ContaFinanceira, on_delete=models.PROTECT, null=True, blank=True, related_name="lancamentos")
    transferencia = models.ForeignKey(TransferenciaFinanceira, on_delete=models.PROTECT, null=True, blank=True, related_name="lancamentos")
    estorno_de = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True, related_name="estornos")
    pagamento_venda = models.ForeignKey("vendas.PagamentoVenda", on_delete=models.PROTECT, null=True, blank=True, related_name="lancamentos_financeiros")
    sangria = models.ForeignKey("pdv.Sangria", on_delete=models.PROTECT, null=True, blank=True, related_name="lancamentos_financeiros")
    suprimento = models.ForeignKey("pdv.Suprimento", on_delete=models.PROTECT, null=True, blank=True, related_name="lancamentos_financeiros")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="lancamentos_financeiros")
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-data", "-criado_em"]
        indexes = [
            models.Index(fields=["conta", "data"], name="financeiro_lanc_conta_data_idx"),
            models.Index(fields=["tipo", "data"], name="financeiro_lanc_tipo_data_idx"),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Lancamentos do livro financeiro nao podem ser alterados.")
        if self.valor <= 0:
            raise ValidationError("Valor do lancamento deve ser maior que zero.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Lancamentos do livro financeiro nao podem ser excluidos.")

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.descricao}"

class ConciliacaoLancamentoFinanceiro(models.Model):
    lancamento = models.OneToOneField(LancamentoFinanceiro, on_delete=models.PROTECT, related_name="conciliacao_bancaria")
    data_conciliacao = models.DateField(default=timezone.localdate)
    referencia_externa = models.CharField(max_length=120)
    observacao = models.CharField(max_length=255, blank=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="conciliacoes_financeiras")
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-data_conciliacao", "-criado_em"]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Conciliacoes financeiras nao podem ser alteradas.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Conciliacoes financeiras nao podem ser excluidas.")

    def __str__(self):
        return f"Conciliacao do lancamento #{self.lancamento_id} - {self.referencia_externa}"

class ExportacaoContabil(models.Model):
    empresa = models.ForeignKey("empresas.Empresa", on_delete=models.PROTECT, related_name="exportacoes_contabeis")
    filial = models.ForeignKey(
        "empresas.Filial", on_delete=models.PROTECT, null=True, blank=True, related_name="exportacoes_contabeis"
    )
    data_inicio = models.DateField()
    data_fim = models.DateField()
    contrato = models.CharField(max_length=80, default="financial_accounting_package_v1")
    chave_idempotencia = models.CharField(max_length=64, unique=True)
    payload_sha256 = models.CharField(max_length=64)
    provedor = models.CharField(max_length=120)
    status = models.CharField(
        max_length=20, choices=StatusExportacaoContabil.choices, default=StatusExportacaoContabil.PENDENTE
    )
    protocolo = models.CharField(max_length=120, blank=True)
    mensagem = models.TextField(blank=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="exportacoes_contabeis"
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-criado_em"]
        indexes = [
            models.Index(fields=["empresa", "data_inicio", "data_fim"], name="fin_exp_empresa_periodo_idx"),
        ]

    def delete(self, *args, **kwargs):
        raise ValidationError("Exportações contábeis não podem ser excluídas.")

    def __str__(self):
        return f"Exportação contábil #{self.pk} - {self.get_status_display()}"