from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.auditoria.models import LogAuditoria
from apps.vendas.models import PagamentoVenda, StatusPagamento

from .models import (
    MovimentoRecebivelEletronico,
    RecebivelEletronico,
    RegraLiquidacaoEletronica,
    StatusItemExtratoFinanceiro,
    StatusRecebivelEletronico,
    TipoLancamentoFinanceiro,
    TipoMovimentoRecebivelEletronico,
)


TIPOS_ELETRONICOS = {
    "PIX",
    "CARTAO",
    "DEBITO",
    "CREDITO",
    "VALE_ALIMENTACAO",
    "VALE_REFEICAO",
}
CENTAVO = Decimal("0.01")


def _moeda(valor):
    return Decimal(valor or 0).quantize(CENTAVO, rounding=ROUND_HALF_UP)


@transaction.atomic
def gerar_recebivel_pagamento(pagamento):
    pagamento = (
        PagamentoVenda.objects.select_for_update()
        .select_related("venda__filial", "forma_pagamento")
        .get(pk=pagamento.pk)
    )
    existente = RecebivelEletronico.objects.filter(pagamento=pagamento).first()
    if existente:
        return existente, False
    if pagamento.status != StatusPagamento.CONFIRMADO:
        return None, False
    if (pagamento.forma_pagamento.tipo or "").upper() not in TIPOS_ELETRONICOS:
        return None, False

    regra = (
        RegraLiquidacaoEletronica.objects.filter(
            filial=pagamento.venda.filial,
            forma_pagamento=pagamento.forma_pagamento,
            ativa=True,
        )
        .select_related("filial", "forma_pagamento")
        .first()
    )
    if not regra:
        return None, False

    bruto = _moeda(pagamento.valor)
    taxa = _moeda((bruto * regra.taxa_percentual / Decimal("100")) + regra.taxa_fixa)
    if taxa >= bruto:
        return None, False
    data_venda = timezone.localtime(pagamento.data).date()
    recebivel = RecebivelEletronico.objects.create(
        pagamento=pagamento,
        regra=regra,
        data_venda=data_venda,
        data_prevista=data_venda + timedelta(days=regra.prazo_dias),
        valor_bruto=bruto,
        taxa_prevista=taxa,
        valor_liquido_previsto=bruto - taxa,
        observacao="Agenda gerada pela regra vigente no momento do processamento.",
    )
    return recebivel, True


def sincronizar_recebiveis(*, filiais):
    pagamentos = (
        PagamentoVenda.objects.filter(
            venda__filial__in=filiais,
            status=StatusPagamento.CONFIRMADO,
            forma_pagamento__tipo__in=TIPOS_ELETRONICOS,
            recebivel_eletronico__isnull=True,
        )
        .select_related("venda__filial", "forma_pagamento")
        .order_by("id")
    )
    criados = 0
    sem_regra = 0
    for pagamento in pagamentos.iterator():
        recebivel, criado = gerar_recebivel_pagamento(pagamento)
        if criado:
            criados += 1
        elif recebivel is None:
            sem_regra += 1
    return {"criados": criados, "sem_regra": sem_regra}

def _referencias_pagamento(recebivel):
    pagamento = recebivel.pagamento
    return {
        str(valor).strip()
        for valor in (
            pagamento.nsu,
            pagamento.transacao_externa_id,
            pagamento.codigo_autorizacao,
        )
        if str(valor or "").strip()
    }


def candidatos_recebivel_item(item, *, somente_referencia=False):
    """Retorna candidatos conservadores dentro da filial e conta do extrato."""
    queryset = (
        RecebivelEletronico.objects.select_related(
            "pagamento__venda__filial", "pagamento__forma_pagamento", "regra"
        )
        .filter(
            pagamento__venda__filial=item.conta.filial,
            pagamento__lancamentos_financeiros__conta=item.conta,
        )
        .distinct()
    )
    if item.tipo == TipoLancamentoFinanceiro.ENTRADA:
        queryset = queryset.filter(status=StatusRecebivelEletronico.PENDENTE).exclude(
            movimentos__tipo__in=[
                TipoMovimentoRecebivelEletronico.LIQUIDACAO,
                TipoMovimentoRecebivelEletronico.ANTECIPACAO,
            ]
        )
    else:
        queryset = queryset.filter(
            status__in=[
                StatusRecebivelEletronico.LIQUIDADO,
                StatusRecebivelEletronico.ANTECIPADO,
                StatusRecebivelEletronico.DIVERGENTE,
            ]
        ).exclude(movimentos__tipo=TipoMovimentoRecebivelEletronico.CHARGEBACK)

    referencia = (item.referencia_externa or "").strip()
    por_referencia = [
        recebivel
        for recebivel in queryset.order_by("data_prevista", "id")
        if referencia and referencia in _referencias_pagamento(recebivel)
    ]
    if por_referencia or somente_referencia:
        return por_referencia

    inicio = item.data - timedelta(days=30)
    fim = item.data + timedelta(days=30)
    return list(queryset.filter(data_prevista__range=(inicio, fim)).order_by("data_prevista", "id")[:20])


@transaction.atomic
def conciliar_recebivel_com_item(
    *, item, recebivel, usuario, valor_alocado=None, automatico=False, ip=None
):
    from .models import ItemExtratoFinanceiro

    item = ItemExtratoFinanceiro.objects.select_for_update().select_related("conta").get(pk=item.pk)
    recebivel = (
        RecebivelEletronico.objects.select_for_update()
        .select_related("pagamento__venda__filial", "pagamento__forma_pagamento")
        .get(pk=recebivel.pk)
    )
    if item.status == StatusItemExtratoFinanceiro.CONCILIADO or item.lancamento_id:
        raise ValidationError("Este item do extrato já foi conciliado.")
    if recebivel.pagamento.venda.filial_id != item.conta.filial_id:
        raise ValidationError("O recebível e o extrato pertencem a filiais diferentes.")
    if not recebivel.pagamento.lancamentos_financeiros.filter(conta=item.conta).exists():
        raise ValidationError("O recebível não pertence à conta de movimento deste extrato.")

    valor_ja_alocado = _moeda(item.valor_alocado_recebiveis)
    saldo_disponivel = _moeda(item.valor - valor_ja_alocado)
    if saldo_disponivel <= 0:
        raise ValidationError("Este item do extrato não possui saldo disponível para alocação.")
    valor_movimento = saldo_disponivel if valor_alocado is None else _moeda(valor_alocado)
    if valor_movimento <= 0:
        raise ValidationError("O valor da alocação deve ser maior que zero.")
    if valor_movimento > saldo_disponivel:
        raise ValidationError(
            f"O valor informado excede o saldo disponível de R$ {saldo_disponivel:.2f}."
        )

    if item.tipo == TipoLancamentoFinanceiro.ENTRADA:
        if recebivel.status != StatusRecebivelEletronico.PENDENTE:
            raise ValidationError("Somente recebíveis pendentes podem receber uma liquidação.")
        tipo = (
            TipoMovimentoRecebivelEletronico.ANTECIPACAO
            if item.data < recebivel.data_prevista
            else TipoMovimentoRecebivelEletronico.LIQUIDACAO
        )
        divergencia = _moeda(valor_movimento - recebivel.valor_liquido_previsto)
        status = (
            StatusRecebivelEletronico.DIVERGENTE
            if divergencia != Decimal("0.00")
            else (
                StatusRecebivelEletronico.ANTECIPADO
                if tipo == TipoMovimentoRecebivelEletronico.ANTECIPACAO
                else StatusRecebivelEletronico.LIQUIDADO
            )
        )
        recebivel.status = status
        recebivel.data_liquidacao = item.data
        recebivel.valor_liquidado = valor_movimento
        recebivel.referencia_liquidacao = item.referencia_externa
        if divergencia:
            recebivel.observacao = (
                f"Liquidação divergente: esperado R$ {recebivel.valor_liquido_previsto:.2f}, "
                f"recebido R$ {valor_movimento:.2f}, diferença R$ {divergencia:.2f}."
            )
        elif tipo == TipoMovimentoRecebivelEletronico.ANTECIPACAO:
            recebivel.observacao = f"Liquidação antecipada em {item.data:%d/%m/%Y}."
        else:
            recebivel.observacao = f"Liquidação confirmada em {item.data:%d/%m/%Y}."
        recebivel.save(update_fields=[
            "status", "data_liquidacao", "valor_liquidado", "referencia_liquidacao",
            "observacao", "atualizado_em",
        ])
    else:
        if recebivel.status not in {
            StatusRecebivelEletronico.LIQUIDADO,
            StatusRecebivelEletronico.ANTECIPADO,
            StatusRecebivelEletronico.DIVERGENTE,
        }:
            raise ValidationError("Chargeback exige um recebível já liquidado ou divergente.")
        tipo = TipoMovimentoRecebivelEletronico.CHARGEBACK
        recebivel.status = StatusRecebivelEletronico.CHARGEBACK
        recebivel.observacao = (
            f"Chargeback de R$ {valor_movimento:.2f} identificado em {item.data:%d/%m/%Y}."
        )
        recebivel.save(update_fields=["status", "observacao", "atualizado_em"])

    MovimentoRecebivelEletronico.objects.create(
        recebivel=recebivel,
        item_extrato=item,
        tipo=tipo,
        data=item.data,
        valor=valor_movimento,
        referencia=item.referencia_externa,
        automatico=automatico,
        usuario=usuario,
    )
    total_alocado = _moeda(valor_ja_alocado + valor_movimento)
    saldo_restante = _moeda(item.valor - total_alocado)
    item.status = (
        StatusItemExtratoFinanceiro.CONCILIADO
        if saldo_restante == Decimal("0.00")
        else StatusItemExtratoFinanceiro.PARCIAL
    )
    item.observacao = (
        f"R$ {total_alocado:.2f} de R$ {item.valor:.2f} alocados a recebíveis; "
        f"saldo R$ {saldo_restante:.2f}."
    )
    item.save(update_fields=["status", "observacao"])
    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="financeiro",
        acao="CONCILIA_RECEBIVEL_EXTRATO",
        descricao=(
            f"Item de extrato #{item.pk} alocado ao recebível #{recebivel.pk} como "
            f"{tipo}; valor R$ {valor_movimento:.2f}; saldo R$ {saldo_restante:.2f}."
        ),
        objeto_tipo="RecebivelEletronico",
        objeto_id=str(recebivel.pk),
        ip=ip,
    )
    return recebivel
