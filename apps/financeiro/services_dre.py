from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal

from apps.core_money import quantizar_moeda
from apps.estoque.models import (
    FechamentoEstoqueContabil,
    MovimentacaoEstoque,
    PerdaEstoque,
    TipoMovimentacaoEstoque,
)
from apps.vendas.models import DevolucaoVenda, ItemVenda, StatusVenda, Venda

from .models import (
    GrupoDRE,
    LancamentoFinanceiro,
    MovimentoRecebivelEletronico,
    RecebivelEletronico,
    TipoLancamentoFinanceiro,
    TipoMovimentoRecebivelEletronico,
)


CONTRATO_DRE = "financial_dre_v2"
CONTRATO_RECONCILIACAO_CMV = "financial_cmv_reconciliation_v1"
ZERO = Decimal("0")
PERCENTUAL = Decimal("0.01")


def _moeda(valor):
    return quantizar_moeda(valor or ZERO)


def _percentual(parte, total):
    if not total:
        return Decimal("0.00")
    return (Decimal(parte) / Decimal(total) * Decimal("100")).quantize(PERCENTUAL)


def _linha(codigo, rotulo, valor, natureza="informativa", *, completo=True, observacao=""):
    return {
        "codigo": codigo,
        "rotulo": rotulo,
        "valor": None if valor is None else _moeda(valor),
        "natureza": natureza,
        "completo": completo,
        "observacao": observacao,
    }


def _itens_por_venda(venda_ids):
    itens = ItemVenda.objects.filter(venda_id__in=venda_ids).select_related("produto", "venda")
    resultado = defaultdict(list)
    for item in itens:
        resultado[item.venda_id].append(item)
    return resultado


def _custo_itens(itens, *, proporcoes=None):
    total = ZERO
    sem_snapshot = []
    valor_sem_cobertura = ZERO
    for item in itens:
        proporcao = proporcoes.get(item.pk, item.quantidade) if proporcoes is not None else item.quantidade
        if item.custo_unitario_no_momento is None:
            sem_snapshot.append(item)
            if proporcoes is None:
                valor_sem_cobertura += item.total
            elif item.quantidade:
                valor_sem_cobertura += item.total * proporcao / item.quantidade
            continue
        total += proporcao * item.custo_unitario_no_momento
    return total, sem_snapshot, valor_sem_cobertura


def _movimentos_por_referencia(referencias):
    movimentos = MovimentacaoEstoque.objects.filter(referencia__in=referencias).select_related(
        "produto", "filial"
    )
    resultado = defaultdict(list)
    for movimento in movimentos:
        resultado[movimento.referencia].append(movimento)
    return resultado


def _operacao_reconciliacao(*, tipo, identificador, filial_id, referencia, itens, movimentos, proporcoes=None):
    esperado_bruto, sem_snapshot, _ = _custo_itens(itens, proporcoes=proporcoes)
    movimentos_validos = [
        movimento
        for movimento in movimentos
        if movimento.filial_id == filial_id
        and movimento.tipo == (
            TipoMovimentacaoEstoque.VENDA if tipo == "VENDA" else TipoMovimentacaoEstoque.DEVOLUCAO
        )
    ]
    sem_custo_movimento = sum(1 for movimento in movimentos_validos if movimento.custo_total is None)
    movimento_bruto = sum(
        (movimento.custo_total for movimento in movimentos_validos if movimento.custo_total is not None), ZERO
    )
    esperado = _moeda(esperado_bruto)
    custo_movimento = _moeda(movimento_bruto)
    incompleto = bool(sem_snapshot or sem_custo_movimento)
    diferenca = _moeda(custo_movimento - esperado)
    if incompleto:
        estado = "INCOMPLETO"
    elif diferenca:
        estado = "DIVERGENTE"
    else:
        estado = "OK"
    return {
        "tipo": tipo,
        "id": identificador,
        "referencia": referencia,
        "cmv_snapshot": esperado,
        "custo_movimentacoes": custo_movimento,
        "diferenca": diferenca,
        "itens_sem_snapshot": len(sem_snapshot),
        "movimentos_sem_custo": sem_custo_movimento,
        "quantidade_movimentos": len(movimentos_validos),
        "estado": estado,
    }


def _evidencias_fechamento(*, filial_ids, data_inicio, data_fim):
    fechamentos = list(
        FechamentoEstoqueContabil.objects.filter(
            filial_id__in=filial_ids, data_referencia__lte=data_fim
        )
        .select_related("filial")
        .order_by("filial_id", "data_referencia")
    )
    por_filial = defaultdict(list)
    for fechamento in fechamentos:
        por_filial[fechamento.filial_id].append(fechamento)
    evidencias = []
    for filial_id in filial_ids:
        disponiveis = por_filial.get(filial_id, [])
        inicial = next(
            (item for item in reversed(disponiveis) if item.data_referencia <= data_inicio), None
        )
        final = next(
            (item for item in reversed(disponiveis) if item.data_referencia <= data_fim), None
        )
        filial_nome = (inicial or final).filial.nome if (inicial or final) else str(filial_id)
        evidencias.append(
            {
                "filial_id": filial_id,
                "filial": filial_nome,
                "inicial": _fechamento_dict(inicial, data_inicio),
                "final": _fechamento_dict(final, data_fim),
                "qualidade": (
                    "EXATA"
                    if inicial
                    and final
                    and inicial.data_referencia == data_inicio
                    and final.data_referencia == data_fim
                    else "REFERENCIA_TEMPORAL"
                    if inicial or final
                    else "SEM_FECHAMENTO"
                ),
            }
        )
    return evidencias


def _fechamento_dict(fechamento, data_esperada):
    if not fechamento:
        return None
    return {
        "id": fechamento.pk,
        "data": fechamento.data_referencia,
        "valor_custo": fechamento.valor_total_custo,
        "criterio_custo": fechamento.criterio_custo,
        "data_exata": fechamento.data_referencia == data_esperada,
    }


def calcular_dre_gerencial(*, data_inicio, data_fim, filial_ids):
    filial_ids = tuple(sorted(set(filial_ids)))
    vendas_periodo = list(
        Venda.objects.filter(
            filial_id__in=filial_ids,
            data__date__range=(data_inicio, data_fim),
            status__in=[StatusVenda.FINALIZADA, StatusVenda.CANCELADA],
        ).select_related("filial")
    )
    cancelamentos_estruturados = list(
        Venda.objects.filter(
            filial_id__in=filial_ids,
            status=StatusVenda.CANCELADA,
            cancelada_em__date__range=(data_inicio, data_fim),
        ).select_related("filial")
    )
    cancelamentos_legados = list(
        Venda.objects.filter(
            filial_id__in=filial_ids,
            status=StatusVenda.CANCELADA,
            cancelada_em__isnull=True,
            data__date__range=(data_inicio, data_fim),
        ).select_related("filial")
    )
    devolucoes = list(
        DevolucaoVenda.objects.filter(
            venda__filial_id__in=filial_ids,
            data__date__range=(data_inicio, data_fim),
        )
        .select_related("venda", "venda__filial")
        .prefetch_related("itens__item_venda__produto")
    )

    vendas_por_id = {
        venda.pk: venda
        for venda in vendas_periodo + cancelamentos_estruturados + cancelamentos_legados
    }
    itens_venda = _itens_por_venda(vendas_por_id)

    receita_bruta = sum((venda.total_bruto for venda in vendas_periodo), ZERO)
    descontos = sum((venda.desconto for venda in vendas_periodo), ZERO)
    cancelamentos = sum(
        (venda.total_liquido for venda in cancelamentos_estruturados + cancelamentos_legados), ZERO
    )
    valor_devolucoes = sum((devolucao.valor_total for devolucao in devolucoes), ZERO)
    receita_liquida = receita_bruta - descontos - cancelamentos - valor_devolucoes

    cmv_bruto = ZERO
    cmv_cancelamentos = ZERO
    cmv_devolucoes = ZERO
    itens_com_snapshot_ids = set()
    itens_sem_snapshot_ids = set()
    valor_sem_cobertura = ZERO
    base_cobertura = ZERO
    produtos = defaultdict(lambda: {"produto_id": None, "produto": "", "cmv_bruto": ZERO, "reversoes": ZERO})

    for venda in vendas_periodo:
        itens = itens_venda[venda.pk]
        custo, ausentes, descoberto = _custo_itens(itens)
        cmv_bruto += custo
        itens_sem_snapshot_ids.update(item.pk for item in ausentes)
        itens_com_snapshot_ids.update(item.pk for item in itens if item.custo_unitario_no_momento is not None)
        valor_sem_cobertura += descoberto
        base_cobertura += sum((item.total for item in itens), ZERO)
        for item in itens:
            linha = produtos[item.produto_id]
            linha["produto_id"] = item.produto_id
            linha["produto"] = item.produto.nome
            if item.custo_unitario_no_momento is not None:
                linha["cmv_bruto"] += item.quantidade * item.custo_unitario_no_momento

    for venda in cancelamentos_estruturados + cancelamentos_legados:
        itens = itens_venda[venda.pk]
        custo, ausentes, descoberto = _custo_itens(itens)
        cmv_cancelamentos += custo
        itens_sem_snapshot_ids.update(item.pk for item in ausentes)
        itens_com_snapshot_ids.update(item.pk for item in itens if item.custo_unitario_no_momento is not None)
        valor_sem_cobertura += descoberto
        base_cobertura += sum((item.total for item in itens), ZERO)
        for item in itens:
            linha = produtos[item.produto_id]
            linha["produto_id"] = item.produto_id
            linha["produto"] = item.produto.nome
            if item.custo_unitario_no_momento is not None:
                linha["reversoes"] += item.quantidade * item.custo_unitario_no_momento

    for devolucao in devolucoes:
        itens_devolvidos = list(devolucao.itens.all())
        originais = [item.item_venda for item in itens_devolvidos]
        proporcoes = {item.item_venda_id: item.quantidade for item in itens_devolvidos}
        custo, ausentes, descoberto = _custo_itens(originais, proporcoes=proporcoes)
        cmv_devolucoes += custo
        itens_sem_snapshot_ids.update(item.pk for item in ausentes)
        itens_com_snapshot_ids.update(
            item.pk for item in originais if item.custo_unitario_no_momento is not None
        )
        valor_sem_cobertura += descoberto
        base_cobertura += sum((item.valor_total for item in itens_devolvidos), ZERO)
        for devolvido in itens_devolvidos:
            original = devolvido.item_venda
            linha = produtos[original.produto_id]
            linha["produto_id"] = original.produto_id
            linha["produto"] = original.produto.nome
            if original.custo_unitario_no_momento is not None:
                linha["reversoes"] += (
                    devolvido.quantidade * original.custo_unitario_no_momento
                )

    cmv_liquido = cmv_bruto - cmv_cancelamentos - cmv_devolucoes
    itens_com_snapshot = len(itens_com_snapshot_ids)
    itens_sem_snapshot = len(itens_sem_snapshot_ids)
    cmv_completo = itens_sem_snapshot == 0

    perdas_qs = PerdaEstoque.objects.filter(
        filial_id__in=filial_ids, data__date__range=(data_inicio, data_fim)
    ).select_related("produto", "filial")
    perdas_total = ZERO
    perdas_por_tipo = defaultdict(lambda: {"quantidade": 0, "valor": ZERO})
    for perda in perdas_qs:
        perdas_total += perda.valor_custo_estimado
        perdas_por_tipo[perda.get_tipo_display()]["quantidade"] += 1
        perdas_por_tipo[perda.get_tipo_display()]["valor"] += perda.valor_custo_estimado

    lancamentos_base = (
        LancamentoFinanceiro.objects.filter(
            conta__filial_id__in=filial_ids, data__range=(data_inicio, data_fim)
        )
        .select_related(
            "conta__filial",
            "conta_financeira__categoria",
            "conta_financeira__centro_custo",
            "conta_contabil",
        )
        .filter(transferencia__isnull=True, sangria__isnull=True, suprimento__isnull=True, estorno_de__isnull=True)
        .exclude(conta_financeira__entrada_compra__isnull=False)
    )
    originais_estornados = LancamentoFinanceiro.objects.filter(estorno_de__isnull=False).values("estorno_de_id")
    lancamentos = list(lancamentos_base.exclude(pk__in=originais_estornados))
    grupos = defaultdict(lambda: {"quantidade": 0, "valor": ZERO})
    detalhes_despesas = defaultdict(lambda: {"quantidade": 0, "valor": ZERO})
    saidas_relevantes = ZERO
    entradas_relevantes = ZERO
    for lancamento in lancamentos:
        categoria = lancamento.conta_financeira.categoria if lancamento.conta_financeira_id else None
        grupo = categoria.grupo_dre if categoria else GrupoDRE.NAO_CLASSIFICADO
        grupos[(lancamento.tipo, grupo)]["quantidade"] += 1
        grupos[(lancamento.tipo, grupo)]["valor"] += lancamento.valor
        if lancamento.tipo == TipoLancamentoFinanceiro.SAIDA:
            saidas_relevantes += lancamento.valor
            if grupo != GrupoDRE.NAO_CLASSIFICADO:
                chave = (
                    categoria.nome if categoria else "Sem categoria",
                    lancamento.conta_contabil.codigo if lancamento.conta_contabil_id else "",
                    lancamento.centro_custo.nome if lancamento.centro_custo_id else "",
                    lancamento.conta.filial.nome,
                )
                detalhes_despesas[chave]["quantidade"] += 1
                detalhes_despesas[chave]["valor"] += lancamento.valor
        else:
            entradas_relevantes += lancamento.valor

    despesas_operacionais = grupos[(TipoLancamentoFinanceiro.SAIDA, GrupoDRE.DESPESA_OPERACIONAL)]["valor"]
    despesas_financeiras_livro = grupos[(TipoLancamentoFinanceiro.SAIDA, GrupoDRE.DESPESA_FINANCEIRA)]["valor"]
    outras_despesas = grupos[(TipoLancamentoFinanceiro.SAIDA, GrupoDRE.OUTRA_DESPESA)]["valor"]
    outras_receitas = grupos[(TipoLancamentoFinanceiro.ENTRADA, GrupoDRE.OUTRA_RECEITA)]["valor"]
    tributos = grupos[(TipoLancamentoFinanceiro.SAIDA, GrupoDRE.TRIBUTO_RESULTADO)]["valor"]
    tributos_classificados = grupos[(TipoLancamentoFinanceiro.SAIDA, GrupoDRE.TRIBUTO_RESULTADO)]["quantidade"] > 0
    saidas_nao = grupos[(TipoLancamentoFinanceiro.SAIDA, GrupoDRE.NAO_CLASSIFICADO)]
    entradas_nao = grupos[(TipoLancamentoFinanceiro.ENTRADA, GrupoDRE.NAO_CLASSIFICADO)]

    movimentos_recebiveis = list(
        MovimentoRecebivelEletronico.objects.filter(
            recebivel__pagamento__venda__filial_id__in=filial_ids,
            data__range=(data_inicio, data_fim),
        ).select_related("recebivel")
    )
    taxas_realizadas = ZERO
    chargebacks = ZERO
    antecipacoes_sem_taxa_segregada = ZERO
    for movimento in movimentos_recebiveis:
        if movimento.tipo in {
            TipoMovimentoRecebivelEletronico.LIQUIDACAO,
            TipoMovimentoRecebivelEletronico.ANTECIPACAO,
        }:
            taxa = max(movimento.recebivel.valor_bruto - movimento.valor, ZERO)
            taxas_realizadas += taxa
            if movimento.tipo == TipoMovimentoRecebivelEletronico.ANTECIPACAO:
                antecipacoes_sem_taxa_segregada += movimento.valor
        elif movimento.tipo == TipoMovimentoRecebivelEletronico.CHARGEBACK:
            chargebacks += movimento.valor
    taxas_previstas = sum(
        RecebivelEletronico.objects.filter(
            pagamento__venda__filial_id__in=filial_ids,
            data_venda__range=(data_inicio, data_fim),
        ).values_list("taxa_prevista", flat=True),
        ZERO,
    )
    despesas_financeiras = despesas_financeiras_livro + taxas_realizadas + chargebacks

    lucro_bruto = receita_liquida - cmv_liquido
    resultado_operacional = (
        lucro_bruto
        - perdas_total
        - despesas_operacionais
        - despesas_financeiras
        + outras_receitas
        - outras_despesas
    )
    resultado_conhecido = resultado_operacional - tributos
    resultado_completo = bool(
        cmv_completo
        and not saidas_nao["quantidade"]
        and not entradas_nao["quantidade"]
        and tributos_classificados
    )

    referencias = []
    operacoes_base = []
    for venda in vendas_periodo:
        referencia = f"venda:{venda.pk}"
        referencias.append(referencia)
        operacoes_base.append(("VENDA", venda.pk, venda.filial_id, referencia, itens_venda[venda.pk], None))
    for venda in cancelamentos_estruturados + cancelamentos_legados:
        referencia = f"cancelamento_venda:{venda.pk}"
        referencias.append(referencia)
        operacoes_base.append(("CANCELAMENTO", venda.pk, venda.filial_id, referencia, itens_venda[venda.pk], None))
    for devolucao in devolucoes:
        referencia = f"devolucao_venda:{devolucao.pk}"
        referencias.append(referencia)
        itens_devolvidos = list(devolucao.itens.all())
        originais = [item.item_venda for item in itens_devolvidos]
        proporcoes = {item.item_venda_id: item.quantidade for item in itens_devolvidos}
        operacoes_base.append(
            ("DEVOLUCAO", devolucao.pk, devolucao.venda.filial_id, referencia, originais, proporcoes)
        )
    movimentos_por_ref = _movimentos_por_referencia(referencias)
    operacoes = [
        _operacao_reconciliacao(
            tipo=tipo,
            identificador=identificador,
            filial_id=filial_id,
            referencia=referencia,
            itens=itens,
            movimentos=movimentos_por_ref.get(referencia, []),
            proporcoes=proporcoes,
        )
        for tipo, identificador, filial_id, referencia, itens, proporcoes in operacoes_base
    ]
    if not operacoes:
        estado_reconciliacao = "SEM_BASE"
    elif any(item["estado"] == "INCOMPLETO" for item in operacoes):
        estado_reconciliacao = "INCOMPLETO"
    elif any(item["estado"] == "DIVERGENTE" for item in operacoes):
        estado_reconciliacao = "DIVERGENTE"
    else:
        estado_reconciliacao = "OK"
    reconciliacao = {
        "contrato": CONTRATO_RECONCILIACAO_CMV,
        "estado": estado_reconciliacao,
        "quantidade_operacoes": len(operacoes),
        "cmv_snapshot_vendas": _moeda(cmv_bruto),
        "custo_movimentos_venda": _moeda(
            sum((item["custo_movimentacoes"] for item in operacoes if item["tipo"] == "VENDA"), ZERO)
        ),
        "reversao_snapshot_cancelamentos": _moeda(cmv_cancelamentos),
        "custo_movimentos_cancelamentos": _moeda(
            sum((item["custo_movimentacoes"] for item in operacoes if item["tipo"] == "CANCELAMENTO"), ZERO)
        ),
        "reversao_snapshot_devolucoes": _moeda(cmv_devolucoes),
        "custo_movimentos_devolucoes": _moeda(
            sum((item["custo_movimentacoes"] for item in operacoes if item["tipo"] == "DEVOLUCAO"), ZERO)
        ),
        "diferenca": _moeda(sum((item["diferenca"] for item in operacoes), ZERO)),
        "cobertura_snapshot": {
            "itens_com_snapshot": itens_com_snapshot,
            "itens_sem_snapshot": itens_sem_snapshot,
            "percentual": _percentual(base_cobertura - valor_sem_cobertura, base_cobertura),
            "completa": cmv_completo,
        },
        "divergencias": [item for item in operacoes if item["estado"] != "OK"],
        "operacoes": operacoes,
        "fechamentos_estoque": _evidencias_fechamento(
            filial_ids=filial_ids, data_inicio=data_inicio, data_fim=data_fim
        ),
    }

    cobertura = _percentual(base_cobertura - valor_sem_cobertura, base_cobertura)
    alertas = []
    if not cmv_completo:
        alertas.append("Há itens sem snapshot de custo; o CMV conhecido está incompleto.")
    if cancelamentos_legados:
        alertas.append("Cancelamentos legados sem data foram revertidos na data original da venda.")
    if saidas_nao["quantidade"] or entradas_nao["quantidade"]:
        alertas.append("Há movimentos financeiros relevantes sem grupo DRE.")
    if estado_reconciliacao in {"DIVERGENTE", "INCOMPLETO"}:
        alertas.append("A reconciliação entre snapshots de venda e movimentos de estoque exige conferência.")
    if not tributos_classificados:
        alertas.append("Tributos sobre resultado não foram apurados por classificação explícita.")
    if any(item["qualidade"] != "EXATA" for item in reconciliacao["fechamentos_estoque"]):
        alertas.append("Não há fechamentos de estoque exatos para todas as datas e filiais do período.")

    linhas = [
        _linha("receita_bruta", "Receita bruta de vendas", receita_bruta, "receita"),
        _linha("descontos", "Descontos comerciais", descontos, "deducao"),
        _linha("cancelamentos", "Cancelamentos", cancelamentos, "deducao"),
        _linha("devolucoes", "Devoluções", valor_devolucoes, "deducao"),
        _linha("receita_liquida", "Receita líquida", receita_liquida, "subtotal"),
        _linha("cmv", "CMV", cmv_liquido, "deducao", completo=cmv_completo),
        _linha("lucro_bruto", "Lucro bruto", lucro_bruto, "subtotal", completo=cmv_completo),
        _linha("perdas_estoque", "Perdas de estoque", perdas_total, "deducao"),
        _linha("despesas_operacionais", "Despesas operacionais", despesas_operacionais, "deducao"),
        _linha("despesas_financeiras", "Despesas financeiras", despesas_financeiras, "deducao"),
        _linha("outras_receitas", "Outras receitas", outras_receitas, "receita"),
        _linha("outras_despesas", "Outras despesas", outras_despesas, "deducao"),
        _linha("resultado_operacional", "Resultado operacional antes dos tributos", resultado_operacional, "resultado", completo=cmv_completo),
        _linha(
            "tributos_resultado",
            "Tributos sobre resultado",
            tributos if tributos_classificados else None,
            "deducao",
            completo=tributos_classificados,
            observacao="Não apurado" if not tributos_classificados else "Somente lançamentos explicitamente classificados.",
        ),
        _linha(
            "resultado_liquido",
            "Resultado líquido gerencial",
            resultado_conhecido if resultado_completo else None,
            "resultado",
            completo=resultado_completo,
            observacao="Resultado conhecido: R$ %.2f" % _moeda(resultado_conhecido) if not resultado_completo else "",
        ),
    ]
    return {
        "contrato": CONTRATO_DRE,
        "periodo": {"inicio": data_inicio, "fim": data_fim},
        "escopo": {"filiais": list(filial_ids)},
        "linhas": linhas,
        "totais": {linha["codigo"]: linha["valor"] for linha in linhas},
        "margem_bruta_percentual": _percentual(lucro_bruto, receita_liquida) if receita_liquida > 0 else None,
        "cmv": {
            "cmv_bruto_vendas": _moeda(cmv_bruto),
            "cmv_reversao_cancelamentos": _moeda(cmv_cancelamentos),
            "cmv_reversao_devolucoes": _moeda(cmv_devolucoes),
            "cmv_liquido": _moeda(cmv_liquido),
            "itens_com_snapshot": itens_com_snapshot,
            "itens_sem_snapshot": itens_sem_snapshot,
            "valor_vendas_sem_cobertura_cmv": _moeda(valor_sem_cobertura),
            "cobertura_cmv_percentual": cobertura,
            "cmv_completo": cmv_completo,
            "criterio_arredondamento": "Soma em alta precisão e quantização monetária somente no total apresentado.",
        },
        "cancelamentos_legados_sem_data": len(cancelamentos_legados),
        "qualidade_temporal_parcial": bool(cancelamentos_legados),
        "resultado_liquido_completo": resultado_completo,
        "resultado_conhecido": _moeda(resultado_conhecido),
        "saidas_nao_classificadas": {
            "quantidade": saidas_nao["quantidade"],
            "valor": _moeda(saidas_nao["valor"]),
            "percentual": _percentual(saidas_nao["valor"], saidas_relevantes),
        },
        "entradas_nao_classificadas": {
            "quantidade": entradas_nao["quantidade"],
            "valor": _moeda(entradas_nao["valor"]),
            "percentual": _percentual(entradas_nao["valor"], entradas_relevantes),
        },
        "perdas_por_tipo": [
            {"tipo": tipo, "quantidade": dados["quantidade"], "valor": _moeda(dados["valor"])}
            for tipo, dados in sorted(perdas_por_tipo.items())
        ],
        "recebiveis": {
            "taxas_realizadas": _moeda(taxas_realizadas),
            "taxas_previstas_diagnostico": _moeda(taxas_previstas),
            "chargebacks": _moeda(chargebacks),
            "antecipacoes_valor_liquidado_sem_taxa_segregada": _moeda(antecipacoes_sem_taxa_segregada),
        },
        "despesas_detalhadas": [
            {
                "categoria": chave[0],
                "conta_contabil": chave[1],
                "centro_custo": chave[2],
                "filial": chave[3],
                "quantidade": dados["quantidade"],
                "valor": _moeda(dados["valor"]),
            }
            for chave, dados in sorted(detalhes_despesas.items())
        ],
        "cmv_por_produto": [
            {
                **dados,
                "cmv_bruto": _moeda(dados["cmv_bruto"]),
                "reversoes": _moeda(dados["reversoes"]),
                "cmv_liquido": _moeda(dados["cmv_bruto"] - dados["reversoes"]),
            }
            for dados in sorted(produtos.values(), key=lambda item: item["produto"])
        ],
        "reconciliacao_cmv": reconciliacao,
        "alertas": alertas,
    }


def serializar_dre_json(valor):
    if isinstance(valor, Decimal):
        return format(valor, "f")
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    if isinstance(valor, dict):
        return {chave: serializar_dre_json(item) for chave, item in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [serializar_dre_json(item) for item in valor]
    return valor
