from collections import defaultdict
from decimal import Decimal

from django.db.models import Q

from apps.compras.models import EntradaCompra, StatusEntradaCompra
from apps.estoque.models import MovimentacaoEstoque, TipoMovimentacaoEstoque
from apps.financeiro.models import StatusContaFinanceira, TipoLancamentoFinanceiro
from apps.fiscal.models import DocumentoDFeRecebido, StatusDocumentoFiscal
from apps.vendas.models import StatusPagamento, StatusVenda, Venda


TOLERANCIA = Decimal("0.01")


def _quantidades_por_produto(itens, campo_quantidade="quantidade"):
    totais = defaultdict(lambda: Decimal("0.000"))
    for item in itens:
        totais[item.produto_id] += getattr(item, campo_quantidade)
    return dict(totais)


def _quantidades_movimentos(movimentos):
    totais = defaultdict(lambda: Decimal("0.000"))
    for movimento in movimentos:
        totais[movimento.produto_id] += movimento.quantidade
    return dict(totais)


def _diferente(valor_a, valor_b, tolerancia=TOLERANCIA):
    return abs((valor_a or Decimal("0")) - (valor_b or Decimal("0"))) > tolerancia


def _movimentos_por_referencia(*, registros, tipo, prefixo, tamanho_lote=500):
    registros = list(registros)
    referencias = [f"{prefixo}:{registro.pk}" for registro in registros]
    filiais_ids = {registro.filial_id for registro in registros}
    movimentos_por_referencia = defaultdict(list)
    for inicio in range(0, len(referencias), tamanho_lote):
        lote = referencias[inicio : inicio + tamanho_lote]
        movimentos = MovimentacaoEstoque.objects.filter(
            filial_id__in=filiais_ids,
            referencia__in=lote,
            tipo=tipo,
        ).select_related("produto")
        for movimento in movimentos:
            movimentos_por_referencia[movimento.referencia].append(movimento)
    return movimentos_por_referencia


def reconciliar_vendas(*, filiais, data_inicio, data_fim):
    vendas = (
        Venda.objects.select_related("filial")
        .filter(filial__in=filiais, data__date__range=(data_inicio, data_fim))
        .prefetch_related(
            "itens",
            "pagamentos__lancamentos_financeiros",
            "documentos_fiscais",
            "devolucoes",
        )
        .order_by("data", "pk")
    )
    vendas = list(vendas)
    movimentos_por_venda = _movimentos_por_referencia(
        registros=vendas, tipo=TipoMovimentacaoEstoque.VENDA, prefixo="venda"
    )
    linhas = []
    for venda in vendas:
        itens = list(venda.itens.all())
        pagamentos = list(venda.pagamentos.all())
        documentos = list(venda.documentos_fiscais.all())
        pagamentos_confirmados = sum(
            (pagamento.valor for pagamento in pagamentos if pagamento.status == StatusPagamento.CONFIRMADO),
            Decimal("0.00"),
        )
        pagamentos_pendentes = sum(
            (pagamento.valor for pagamento in pagamentos if pagamento.status in {StatusPagamento.PENDENTE, StatusPagamento.ESTORNO_PENDENTE}),
            Decimal("0.00"),
        )
        pagamentos_estornados = sum(
            (pagamento.valor for pagamento in pagamentos if pagamento.status == StatusPagamento.ESTORNADO),
            Decimal("0.00"),
        )
        livro_financeiro = sum(
            (
                lancamento.valor
                for pagamento in pagamentos
                for lancamento in pagamento.lancamentos_financeiros.all()
                if lancamento.tipo == TipoLancamentoFinanceiro.ENTRADA and not lancamento.estorno_de_id
            ),
            Decimal("0.00"),
        )
        documentos_emitidos = [doc for doc in documentos if doc.status == StatusDocumentoFiscal.EMITIDO]
        valor_fiscal = sum((doc.valor_total for doc in documentos_emitidos), Decimal("0.00"))
        movimentos = movimentos_por_venda[f"venda:{venda.pk}"]
        itens_estoque_ok = _quantidades_por_produto(itens) == _quantidades_movimentos(movimentos)
        codigos = []
        if venda.status == StatusVenda.FINALIZADA:
            if _diferente(pagamentos_confirmados, venda.total_liquido):
                codigos.append("PAGAMENTO_DIVERGENTE")
            if _diferente(livro_financeiro, pagamentos_confirmados):
                codigos.append("LIVRO_FINANCEIRO_DIVERGENTE")
            if not documentos_emitidos:
                codigos.append("DOCUMENTO_FISCAL_AUSENTE")
            elif _diferente(valor_fiscal, venda.total_liquido):
                codigos.append("VALOR_FISCAL_DIVERGENTE")
            if not itens_estoque_ok:
                codigos.append("ESTOQUE_DIVERGENTE")
            if any(doc.status not in {StatusDocumentoFiscal.EMITIDO, StatusDocumentoFiscal.CANCELADO} for doc in documentos):
                codigos.append("DOCUMENTO_FISCAL_PENDENTE")
            situacao = "OK" if not codigos else "DIVERGENTE"
        elif venda.status == StatusVenda.CANCELADA:
            codigos.append("VENDA_CANCELADA_REVISAR_EVENTOS")
            situacao = "REVISAO"
        else:
            codigos.append("VENDA_ABERTA_NA_COMPETENCIA")
            situacao = "REVISAO"
        linhas.append(
            {
                "filial": venda.filial.nome,
                "venda_id": venda.pk,
                "data": venda.data,
                "status_venda": venda.get_status_display(),
                "total_venda": venda.total_liquido,
                "pagamentos_confirmados": pagamentos_confirmados,
                "pagamentos_pendentes": pagamentos_pendentes,
                "pagamentos_estornados": pagamentos_estornados,
                "livro_financeiro": livro_financeiro,
                "documentos_fiscais": len(documentos),
                "documentos_emitidos": len(documentos_emitidos),
                "valor_fiscal": valor_fiscal,
                "itens_venda": len(itens),
                "movimentos_estoque": len(movimentos),
                "devolucoes": venda.devolucoes.count(),
                "situacao": situacao,
                "divergencias": "|".join(codigos),
            }
        )
    return linhas


def reconciliar_entradas(*, filiais, data_inicio, data_fim):
    entradas = (
        EntradaCompra.objects.select_related("filial", "fornecedor")
        .filter(filial__in=filiais)
        .filter(
            Q(data_emissao__range=(data_inicio, data_fim))
            | Q(data_emissao__isnull=True, data_recebimento__date__range=(data_inicio, data_fim))
        )
        .prefetch_related("itens", "contas_financeiras")
        .order_by("data_emissao", "data_recebimento", "pk")
    )
    entradas = list(entradas)
    documentos_por_entrada = {
        documento.entrada_compra_id: documento
        for documento in DocumentoDFeRecebido.objects.filter(
            entrada_compra__in=entradas, entrada_compra__filial__in=filiais
        )
    }
    movimentos_por_entrada = _movimentos_por_referencia(
        registros=entradas, tipo=TipoMovimentacaoEstoque.ENTRADA, prefixo="entrada_compra"
    )
    linhas = []
    for entrada in entradas:
        itens = list(entrada.itens.all())
        contas = list(entrada.contas_financeiras.all())
        documento = documentos_por_entrada.get(entrada.pk)
        total_itens = sum((item.total for item in itens), Decimal("0.00"))
        valor_contas = sum(
            (conta.valor for conta in contas if conta.status != StatusContaFinanceira.CANCELADA),
            Decimal("0.00"),
        )
        movimentos = movimentos_por_entrada[f"entrada_compra:{entrada.pk}"]
        itens_estoque_ok = _quantidades_por_produto(itens) == _quantidades_movimentos(movimentos)
        valor_esperado = entrada.total_documento if entrada.total_documento is not None else entrada.total_produtos
        codigos = []
        if entrada.status == StatusEntradaCompra.FINALIZADA:
            if _diferente(total_itens, entrada.total_produtos):
                codigos.append("TOTAL_ITENS_DIVERGENTE")
            if entrada.chave_acesso_xml and not documento:
                codigos.append("DFE_RECEBIDO_NAO_VINCULADO")
            if entrada.gerar_conta_financeira and _diferente(valor_contas, valor_esperado):
                codigos.append("CONTA_PAGAR_DIVERGENTE")
            if not entrada.gerar_conta_financeira and contas:
                codigos.append("CONTA_PAGAR_INDEVIDA")
            if not itens_estoque_ok:
                codigos.append("ESTOQUE_DIVERGENTE")
            situacao = "OK" if not codigos else "DIVERGENTE"
        elif entrada.status == StatusEntradaCompra.CANCELADA:
            codigos.append("ENTRADA_CANCELADA_REVISAR_ESTORNOS")
            situacao = "REVISAO"
        else:
            codigos.append("ENTRADA_RASCUNHO_NA_COMPETENCIA")
            situacao = "REVISAO"
        linhas.append(
            {
                "filial": entrada.filial.nome,
                "entrada_id": entrada.pk,
                "data_emissao": entrada.data_emissao,
                "data_recebimento": entrada.data_recebimento,
                "status_entrada": entrada.get_status_display(),
                "fornecedor": str(entrada.fornecedor),
                "numero_documento": entrada.numero_documento,
                "chave_acesso": entrada.chave_acesso_xml or "",
                "total_itens": total_itens,
                "total_produtos": entrada.total_produtos,
                "total_documento": entrada.total_documento,
                "documento_dfe_vinculado": bool(documento),
                "contas_pagar": len(contas),
                "valor_contas_pagar": valor_contas,
                "itens_entrada": len(itens),
                "movimentos_estoque": len(movimentos),
                "situacao": situacao,
                "divergencias": "|".join(codigos),
            }
        )
    return linhas


def gerar_reconciliacao_operacional(*, filiais, data_inicio, data_fim):
    vendas = reconciliar_vendas(filiais=filiais, data_inicio=data_inicio, data_fim=data_fim)
    entradas = reconciliar_entradas(filiais=filiais, data_inicio=data_inicio, data_fim=data_fim)
    return {
        "contrato": "accounting_operational_reconciliation_v1",
        "periodo": {"inicio": data_inicio.isoformat(), "fim": data_fim.isoformat()},
        "resumo": {
            "vendas": len(vendas),
            "vendas_ok": sum(1 for linha in vendas if linha["situacao"] == "OK"),
            "vendas_divergentes": sum(1 for linha in vendas if linha["situacao"] == "DIVERGENTE"),
            "vendas_revisao": sum(1 for linha in vendas if linha["situacao"] == "REVISAO"),
            "entradas": len(entradas),
            "entradas_ok": sum(1 for linha in entradas if linha["situacao"] == "OK"),
            "entradas_divergentes": sum(1 for linha in entradas if linha["situacao"] == "DIVERGENTE"),
            "entradas_revisao": sum(1 for linha in entradas if linha["situacao"] == "REVISAO"),
        },
        "vendas": vendas,
        "entradas": entradas,
        "observacao": "Conferência somente leitura; nenhuma divergência gera correção ou obrigação automaticamente.",
    }



