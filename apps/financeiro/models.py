import hashlib
import secrets

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
    CAIXA = "CAIXA", "Caixa físico"
    BANCO = "BANCO", "Conta bancária"
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


class NaturezaContaContabil(models.TextChoices):
    ATIVO = "ATIVO", "Ativo"
    PASSIVO = "PASSIVO", "Passivo"
    PATRIMONIO_LIQUIDO = "PATRIMONIO_LIQUIDO", "Patrim?nio l?quido"
    RECEITA = "RECEITA", "Receita"
    DESPESA = "DESPESA", "Despesa"
    COMPENSACAO = "COMPENSACAO", "Compensa??o"


class TipoContaContabil(models.TextChoices):
    SINTETICA = "SINTETICA", "Sint?tica"
    ANALITICA = "ANALITICA", "Anal?tica"


class ContaContabil(models.Model):
    empresa = models.ForeignKey("empresas.Empresa", on_delete=models.PROTECT, related_name="plano_contas")
    codigo = models.CharField(max_length=40)
    nome = models.CharField(max_length=160)
    natureza = models.CharField(max_length=30, choices=NaturezaContaContabil.choices)
    tipo = models.CharField(max_length=20, choices=TipoContaContabil.choices, default=TipoContaContabil.ANALITICA)
    conta_pai = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True, related_name="subcontas", verbose_name="Conta superior")
    ativa = models.BooleanField(default=True)

    class Meta:
        ordering = ["empresa", "codigo"]
        verbose_name = "Conta cont?bil"
        verbose_name_plural = "Plano de contas"
        constraints = [
            models.UniqueConstraint(fields=["empresa", "codigo"], name="financeiro_conta_contabil_codigo_empresa"),
        ]

    def clean(self):
        if self.conta_pai_id and self.conta_pai.empresa_id != self.empresa_id:
            raise ValidationError({"conta_pai": "A conta superior pertence a outra empresa."})
        if self.conta_pai_id and self.conta_pai.tipo != TipoContaContabil.SINTETICA:
            raise ValidationError({"conta_pai": "A conta superior deve ser sint?tica."})
        if self.pk and self.conta_pai_id == self.pk:
            raise ValidationError({"conta_pai": "Uma conta n?o pode ser superior a ela mesma."})
        if self.pk and self.tipo == TipoContaContabil.ANALITICA and self.subcontas.exists():
            raise ValidationError({"tipo": "Uma conta com subcontas deve permanecer sint?tica."})
        if self.pk:
            tipo_anterior = ContaContabil.objects.filter(pk=self.pk).values_list("tipo", flat=True).first()
            if tipo_anterior != self.tipo and (self.categorias_financeiras.exists() or self.lancamentos.exists()):
                raise ValidationError({"tipo": "N?o altere o tipo de uma conta cont?bil j? utilizada."})
        pai = self.conta_pai
        visitados = {self.pk} if self.pk else set()
        while pai:
            if pai.pk in visitados:
                raise ValidationError({"conta_pai": "A hierarquia do plano de contas formaria um ciclo."})
            visitados.add(pai.pk)
            pai = pai.conta_pai

    def __str__(self):
        return f"{self.codigo} - {self.nome}"


class CentroCusto(models.Model):
    empresa = models.ForeignKey("empresas.Empresa", on_delete=models.PROTECT, related_name="centros_custo")
    codigo = models.CharField(max_length=30)
    nome = models.CharField(max_length=120)
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ["empresa", "nome"]
        verbose_name = "Centro de custo"
        verbose_name_plural = "Centros de custo"
        constraints = [
            models.UniqueConstraint(fields=["empresa", "codigo"], name="financeiro_centro_codigo_unico_empresa"),
            models.UniqueConstraint(fields=["empresa", "nome"], name="financeiro_centro_nome_unico_empresa"),
        ]

    def __str__(self):
        return f"{self.codigo} - {self.nome}"


class CategoriaFinanceira(models.Model):
    empresa = models.ForeignKey("empresas.Empresa", on_delete=models.PROTECT, related_name="categorias_financeiras")
    nome = models.CharField(max_length=120)
    conta_contabil = models.ForeignKey(ContaContabil, on_delete=models.PROTECT, null=True, blank=True, related_name="categorias_financeiras", verbose_name="Conta cont?bil")
    tipo = models.CharField(max_length=20, choices=TipoContaFinanceira.choices)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["tipo", "nome"]
        constraints = [models.UniqueConstraint(fields=["empresa", "nome"], name="financeiro_categoria_unica_por_empresa")]

    def clean(self):
        if self.conta_contabil_id and self.conta_contabil.empresa_id != self.empresa_id:
            raise ValidationError({"conta_contabil": "A conta cont?bil pertence a outra empresa."})
        if self.conta_contabil_id and self.conta_contabil.tipo != TipoContaContabil.ANALITICA:
            raise ValidationError({"conta_contabil": "Selecione uma conta cont?bil anal?tica para a categoria."})

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
    centro_custo = models.ForeignKey(CentroCusto, on_delete=models.PROTECT, null=True, blank=True, related_name="contas_financeiras", verbose_name="Centro de custo")
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
        if self.categoria_id and self.filial_id and self.categoria.empresa_id != self.filial.empresa_id:
            raise ValidationError({"categoria": "Categoria informada pertence a outra empresa."})
        if self.centro_custo_id and self.filial_id and self.centro_custo.empresa_id != self.filial.empresa_id:
            raise ValidationError({"centro_custo": "Centro de custo informado pertence a outra empresa."})
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
            raise ValidationError("Transferências financeiras não podem ser alteradas.")
        if self.conta_origem_id == self.conta_destino_id:
            raise ValidationError("As contas de origem e destino devem ser diferentes.")
        if self.valor <= 0:
            raise ValidationError("Valor da transferencia deve ser maior que zero.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Transferências financeiras não podem ser excluídas.")

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
    centro_custo = models.ForeignKey(CentroCusto, on_delete=models.PROTECT, null=True, blank=True, related_name="lancamentos", verbose_name="Centro de custo")
    conta_contabil = models.ForeignKey(ContaContabil, on_delete=models.PROTECT, null=True, blank=True, related_name="lancamentos", verbose_name="Conta cont?bil")
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
            raise ValidationError("Lancamentos do livro financeiro não podem ser alterados.")
        if self.centro_custo_id and self.conta_id and self.centro_custo.empresa_id != self.conta.filial.empresa_id:
            raise ValidationError({"centro_custo": "Centro de custo informado pertence a outra empresa."})
        if self.conta_contabil_id and self.conta_id and self.conta_contabil.empresa_id != self.conta.filial.empresa_id:
            raise ValidationError({"conta_contabil": "Conta cont?bil informada pertence a outra empresa."})
        if self.conta_contabil_id and self.conta_contabil.tipo != TipoContaContabil.ANALITICA:
            raise ValidationError({"conta_contabil": "Lan?amentos exigem conta cont?bil anal?tica."})
        if self.valor <= 0:
            raise ValidationError("Valor do lançamento deve ser maior que zero.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Lancamentos do livro financeiro não podem ser excluidos.")

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
            raise ValidationError("Conciliacoes financeiras não podem ser alteradas.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Conciliacoes financeiras não podem ser excluídas.")

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
class ChaveIntegracaoContabil(models.Model):
    empresa = models.ForeignKey("empresas.Empresa", on_delete=models.PROTECT, related_name="chaves_integracao_contabil")
    nome = models.CharField(max_length=120)
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    ativa = models.BooleanField(default=True)
    valida_ate = models.DateTimeField(null=True, blank=True)
    criada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="chaves_integracao_contabil_criadas")
    criada_em = models.DateTimeField(auto_now_add=True)
    atualizada_em = models.DateTimeField(auto_now=True)
    ultima_utilizacao_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["empresa__nome_fantasia", "nome"]
        constraints = [
            models.UniqueConstraint(fields=["empresa", "nome"], name="financeiro_chave_contabil_empresa_nome"),
        ]

    @staticmethod
    def calcular_hash(token):
        return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()

    @classmethod
    def gerar_token(cls):
        return f"dvc_{secrets.token_urlsafe(32)}"

    def definir_token(self, token):
        self.token_hash = self.calcular_hash(token)

    @property
    def vigente(self):
        return self.ativa and (self.valida_ate is None or self.valida_ate > timezone.now())

    def revogar(self):
        self.ativa = False
        self.save(update_fields=["ativa", "atualizada_em"])

    def __str__(self):
        return f"{self.empresa} - {self.nome}"