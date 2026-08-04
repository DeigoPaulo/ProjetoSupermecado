from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.auditoria.models import LogAuditoria

from .models import (
    ComposicaoProduto,
    DesmembramentoProduto,
    Estoque,
    InventarioEstoque,
    ItemProducaoComposicaoProduto,
    ItemDesmembramentoProduto,
    LoteEstoque,
    MovimentacaoEstoque,
    MovimentacaoLoteEstoque,
    OrdemProducaoComposicao,
    PerdaEstoque,
    ProducaoComposicaoProduto,
    StatusDesmembramentoProduto,
    StatusInventario,
    StatusOrdemProducaoComposicao,
    StatusProducaoComposicao,
    TipoDesmembramentoProduto,
    TipoMovimentacaoEstoque,
    TipoPerdaEstoque,
    TipoSaidaDesmembramento,
    consumir_lotes_movimentacao,
    criar_lote_movimentacao,
    movimentar_estoque,
    restaurar_lotes_movimentacao,
)


def _autorizacao_texto(supervisor):
    return f" Autorizado por: {supervisor}." if supervisor else ""

TIPOS_COM_CONSERVACAO_MASSA = {
    TipoDesmembramentoProduto.ACOUGUE,
    TipoDesmembramentoProduto.HORTIFRUTI,
}


def _conservacao_massa_aplicavel(*, tipo, produto_origem, destinos):
    return bool(
        tipo in TIPOS_COM_CONSERVACAO_MASSA
        and produto_origem.unidade == "KG"
        and all(destino["produto"].unidade == "KG" for destino in destinos)
    )


def _resumo_conservacao_massa(*, tipo, produto_origem, quantidade_origem, destinos):
    quantidade_total = sum((destino["quantidade"] for destino in destinos), Decimal("0.000"))
    aplicavel = _conservacao_massa_aplicavel(tipo=tipo, produto_origem=produto_origem, destinos=destinos)
    excesso = max(quantidade_total - quantidade_origem, Decimal("0.000")) if aplicavel else Decimal("0.000")
    nao_classificada = max(quantidade_origem - quantidade_total, Decimal("0.000")) if aplicavel else Decimal("0.000")
    rendimento_total = ((quantidade_total / quantidade_origem) * Decimal("100")).quantize(Decimal("0.01"))
    return {
        "aplicavel": aplicavel,
        "valida": not aplicavel or (excesso == 0 and nao_classificada == 0),
        "quantidade_total": quantidade_total,
        "excesso": excesso,
        "nao_classificada": nao_classificada,
        "rendimento_total": rendimento_total,
    }


def _normalizar_data_lote(valor, rotulo):
    if not valor or isinstance(valor, date):
        return valor
    try:
        return date.fromisoformat(str(valor))
    except ValueError as exc:
        raise ValidationError(f"Informe uma data de {rotulo} valida.") from exc


def saldo_rastreado_lotes(*, produto, filial, bloquear=False):
    lotes = LoteEstoque.objects.filter(
        produto=produto,
        filial=filial,
        quantidade_atual__gt=0,
    )
    if bloquear:
        lotes = lotes.select_for_update()
    return sum((lote.quantidade_atual for lote in lotes), Decimal("0.000"))


@transaction.atomic
def atribuir_saldo_historico_lote(
    *,
    estoque,
    codigo,
    quantidade,
    custo_unitario,
    usuario,
    motivo,
    fabricacao=None,
    validade=None,
    supervisor=None,
    ip=None,
):
    motivo = (motivo or "").strip()
    codigo = (codigo or "").strip()
    if not motivo:
        raise ValidationError("Informe o motivo da atribuicao.")
    if not codigo:
        raise ValidationError("Informe o código do lote.")
    if quantidade <= 0:
        raise ValidationError("Quantidade deve ser maior que zero.")
    if custo_unitario < 0:
        raise ValidationError("Custo unitario não pode ser negativo.")

    estoque = Estoque.objects.select_for_update().select_related("produto", "filial").get(pk=estoque.pk)
    lotes_atuais = list(
        LoteEstoque.objects.select_for_update().filter(
            produto=estoque.produto,
            filial=estoque.filial,
            quantidade_atual__gt=0,
        )
    )
    saldo_rastreado = sum((lote.quantidade_atual for lote in lotes_atuais), Decimal("0.000"))
    saldo_sem_lote = estoque.quantidade_atual - saldo_rastreado
    if saldo_sem_lote < quantidade:
        raise ValidationError(
            f"A quantidade excede o saldo sem lote disponivel ({saldo_sem_lote})."
        )

    lote = LoteEstoque(
        produto=estoque.produto,
        filial=estoque.filial,
        codigo=codigo,
        fabricacao=fabricacao,
        validade=validade,
        quantidade_inicial=quantidade,
        quantidade_atual=quantidade,
        custo_unitario=custo_unitario,
        origem_referencia=f"atribuicao_historico:estoque:{estoque.id}",
    )
    lote.full_clean()
    lote.save()
    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="estoque",
        acao="ATRIBUICAO_SALDO_HISTORICO_LOTE",
        descricao=(
            f"{quantidade} de {estoque.produto} / {estoque.filial} atribuido ao lote {codigo} "
            f"sem alterar o saldo agregado. Motivo: {motivo}.{_autorizacao_texto(supervisor)}"
        ),
        objeto_tipo="LoteEstoque",
        objeto_id=str(lote.id),
        ip=ip,
    )
    return lote


def reconciliar_lotes_reducao_inventario(*, produto, filial, saldo_novo, movimentacao):
    lotes = list(
        LoteEstoque.objects.select_for_update().filter(
            produto=produto,
            filial=filial,
            quantidade_atual__gt=0,
        ).order_by(F("validade").asc(nulls_last=True), "criado_em", "id")
    )
    saldo_rastreado = sum((lote.quantidade_atual for lote in lotes), Decimal("0.000"))
    excesso_rastreado = max(saldo_rastreado - saldo_novo, Decimal("0.000"))
    reduzido = Decimal("0.000")
    for lote in lotes:
        if excesso_rastreado <= 0:
            break
        quantidade = min(lote.quantidade_atual, excesso_rastreado)
        lote.quantidade_atual -= quantidade
        lote.save(update_fields=["quantidade_atual", "atualizado_em"])
        MovimentacaoLoteEstoque.objects.create(
            movimentacao=movimentacao,
            lote=lote,
            quantidade=quantidade,
            custo_unitario=lote.custo_unitario,
        )
        excesso_rastreado -= quantidade
        reduzido += quantidade
    return reduzido


@transaction.atomic
def aplicar_inventario(*, inventario, usuario, supervisor=None, ip=None):
    inventario = InventarioEstoque.objects.select_for_update().get(pk=inventario.pk)
    if inventario.status != StatusInventario.ABERTO:
        raise ValidationError("Apenas inventarios abertos podem ser aplicados.")

    itens = list(inventario.itens.select_related("produto"))
    if not itens:
        raise ValidationError("Inclua ao menos um item antes de aplicar o inventario.")

    for item in itens:
        estoque, _ = Estoque.objects.select_for_update().get_or_create(produto=item.produto, filial=inventario.filial)
        item.quantidade_sistema = estoque.quantidade_atual
        item.diferenca = item.quantidade_contada - estoque.quantidade_atual
        item.save(update_fields=["quantidade_sistema", "diferenca"])

        estoque.quantidade_atual = item.quantidade_contada
        estoque.full_clean()
        estoque.save()

        if item.diferenca != 0:
            movimentacao = MovimentacaoEstoque.objects.create(
                produto=item.produto,
                filial=inventario.filial,
                tipo=TipoMovimentacaoEstoque.AJUSTE,
                quantidade=item.diferenca,
                motivo=f"Inventario: {inventario.descricao}",
                referencia=f"inventario:{inventario.id}",
                usuario=usuario,
            )
            if item.diferenca < 0:
                reconciliar_lotes_reducao_inventario(
                    produto=item.produto,
                    filial=inventario.filial,
                    saldo_novo=item.quantidade_contada,
                    movimentacao=movimentacao,
                )

    inventario.status = StatusInventario.APLICADO
    inventario.aplicado_em = timezone.now()
    inventario.save(update_fields=["status", "aplicado_em"])

    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="estoque",
        acao="APLICACAO_INVENTARIO",
        descricao=f"Inventario {inventario.id} aplicado com {len(itens)} item(ns).{_autorizacao_texto(supervisor)}",
        objeto_tipo="InventarioEstoque",
        objeto_id=str(inventario.id),
        ip=ip,
    )
    return inventario


@transaction.atomic
def registrar_perda_estoque(*, produto, filial, usuario, tipo, quantidade, motivo, supervisor=None, ip=None):
    custo_unitario = produto.preco_custo
    preco_venda = produto.preco_venda
    perda = PerdaEstoque.objects.create(
        produto=produto,
        filial=filial,
        usuario=usuario,
        tipo=tipo,
        quantidade=quantidade,
        motivo=motivo,
        custo_unitario_no_momento=custo_unitario,
        preco_venda_no_momento=preco_venda,
        valor_custo_estimado=custo_unitario * quantidade,
        valor_venda_estimado=preco_venda * quantidade,
    )
    movimentar_estoque(
        produto=produto,
        filial=filial,
        tipo=TipoMovimentacaoEstoque.PERDA,
        quantidade=quantidade,
        usuario=usuario,
        motivo=f"Perda/{tipo}: {motivo}",
        referencia=f"perda:{perda.id}",
        custo_unitario=custo_unitario,
    )
    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="estoque",
        acao="REGISTRO_PERDA",
        descricao=f"Perda {perda.id}: {produto} - {quantidade}. Motivo: {motivo}.{_autorizacao_texto(supervisor)}",
        objeto_tipo="PerdaEstoque",
        objeto_id=str(perda.id),
        ip=ip,
    )
    return perda


@transaction.atomic
def confirmar_producao_composicao(
    *,
    composicao,
    filial,
    quantidade_final,
    usuario,
    motivo,
    observacao="",
    codigo_lote="",
    fabricacao=None,
    validade=None,
    supervisor=None,
    ip=None,
):
    if not motivo:
        raise ValidationError("Informe o motivo da produção.")
    if quantidade_final <= 0:
        raise ValidationError("Quantidade final da composição deve ser maior que zero.")

    composicao = (
        ComposicaoProduto.objects.select_for_update()
        .select_related("empresa", "filial", "produto_final")
        .prefetch_related("itens__produto_componente")
        .get(pk=composicao.pk)
    )
    if not composicao.is_active:
        raise ValidationError("Composição inativa não pode ser produzida.")
    if composicao.filial_id and composicao.filial_id != filial.id:
        raise ValidationError("Composição pertence a outra filial.")
    codigo_lote = (codigo_lote or "").strip()
    fabricacao = _normalizar_data_lote(fabricacao, "fabricacao")
    validade = _normalizar_data_lote(validade, "validade")
    if composicao.produto_final.exige_lote and not codigo_lote:
        raise ValidationError("O produto final exige lote.")
    if (fabricacao or validade) and not codigo_lote:
        raise ValidationError("Informe o lote ao preencher fabricação ou validade.")
    if fabricacao and validade and fabricacao > validade:
        raise ValidationError("A validade não pode ser anterior a fabricação.")

    itens_receita = list(composicao.itens.select_related("produto_componente"))
    if not itens_receita:
        raise ValidationError("Inclua ao menos um componente na composição.")
    fator = quantidade_final / composicao.quantidade_final

    consumos = []
    custo_total = Decimal("0.00")
    for item_receita in itens_receita:
        if item_receita.produto_componente_id == composicao.produto_final_id:
            raise ValidationError("Produto final não pode ser componente da própria composição.")
        quantidade_consumida = item_receita.quantidade * fator
        estoque_componente, _ = Estoque.objects.select_for_update().get_or_create(
            produto=item_receita.produto_componente,
            filial=filial,
        )
        if estoque_componente.quantidade_disponivel < quantidade_consumida:
            raise ValidationError(f"Estoque insuficiente do componente {item_receita.produto_componente}.")
        custo_unitario = Decimal(item_receita.produto_componente.preco_custo)
        custo_item = custo_unitario * quantidade_consumida
        custo_total += custo_item
        consumos.append((item_receita.produto_componente, quantidade_consumida, custo_unitario, custo_item, estoque_componente))

    producao = ProducaoComposicaoProduto.objects.create(
        composicao=composicao,
        empresa=filial.empresa,
        filial=filial,
        produto_final=composicao.produto_final,
        quantidade_final=quantidade_final,
        custo_total=custo_total,
        usuario=usuario,
        motivo=motivo,
        observacao=observacao,
    )

    for produto_componente, quantidade_consumida, custo_unitario, custo_item, estoque_componente in consumos:
        ItemProducaoComposicaoProduto.objects.create(
            producao=producao,
            produto_componente=produto_componente,
            quantidade_consumida=quantidade_consumida,
            custo_unitario=custo_unitario,
            custo_total=custo_item,
        )
        estoque_componente.quantidade_atual -= quantidade_consumida
        estoque_componente.full_clean()
        estoque_componente.save()
        movimento_componente = MovimentacaoEstoque.objects.create(
            produto=produto_componente,
            filial=filial,
            tipo=TipoMovimentacaoEstoque.DESMEMBRAMENTO,
            quantidade=-quantidade_consumida,
            motivo=f"Composicao {producao.id}: consumo de componente",
            referencia=f"composicao:{producao.id}:componente:{produto_componente.id}",
            custo_unitario=custo_unitario,
            custo_total=custo_item,
            usuario=usuario,
        )
        consumir_lotes_movimentacao(
            movimentacao=movimento_componente,
            quantidade=quantidade_consumida,
        )

    estoque_final, _ = Estoque.objects.select_for_update().get_or_create(produto=composicao.produto_final, filial=filial)
    estoque_final.quantidade_atual += quantidade_final
    estoque_final.full_clean()
    estoque_final.save()
    movimento_final = MovimentacaoEstoque.objects.create(
        produto=composicao.produto_final,
        filial=filial,
        tipo=TipoMovimentacaoEstoque.DESMEMBRAMENTO,
        quantidade=quantidade_final,
        motivo=f"Composicao {producao.id}: entrada do produto final",
        referencia=f"composicao:{producao.id}:final",
        custo_unitario=custo_total / quantidade_final,
        custo_total=custo_total,
        usuario=usuario,
    )
    if codigo_lote:
        criar_lote_movimentacao(
            movimentacao=movimento_final,
            codigo_lote=codigo_lote,
            quantidade=quantidade_final,
            custo_unitario=custo_total / quantidade_final,
            fabricacao=fabricacao,
            validade=validade,
        )

    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="estoque",
        acao="PRODUCAO_COMPOSICAO",
        descricao=(
            f"Composicao {producao.id}: {quantidade_final} de {composicao.produto_final} gerado "
            f"com {len(consumos)} componente(s). Motivo: {motivo}.{_autorizacao_texto(supervisor)}"
        ),
        objeto_tipo="ProducaoComposicaoProduto",
        objeto_id=str(producao.id),
        ip=ip,
    )
    return producao


@transaction.atomic
def cancelar_producao_composicao(*, producao, usuario, motivo, supervisor=None, ip=None):
    if not motivo:
        raise ValidationError("Informe o motivo do cancelamento.")

    producao = (
        ProducaoComposicaoProduto.objects.select_for_update()
        .select_related("filial", "produto_final")
        .prefetch_related("itens__produto_componente")
        .get(pk=producao.pk)
    )
    if producao.status != StatusProducaoComposicao.CONFIRMADO:
        raise ValidationError("Apenas composicoes confirmadas podem ser canceladas.")

    estoque_final, _ = Estoque.objects.select_for_update().get_or_create(produto=producao.produto_final, filial=producao.filial)
    if estoque_final.quantidade_disponivel < producao.quantidade_final:
        raise ValidationError("Produto final não possui saldo suficiente para cancelar a composição.")

    estoque_final.quantidade_atual -= producao.quantidade_final
    estoque_final.full_clean()
    estoque_final.save()
    movimento_final_cancelamento = MovimentacaoEstoque.objects.create(
        produto=producao.produto_final,
        filial=producao.filial,
        tipo=TipoMovimentacaoEstoque.DESMEMBRAMENTO,
        quantidade=-producao.quantidade_final,
        motivo=f"Cancelamento da composicao {producao.id}: {motivo}",
        referencia=f"composicao:{producao.id}:cancelamento:final",
        custo_unitario=producao.custo_total / producao.quantidade_final,
        custo_total=producao.custo_total,
        usuario=usuario,
    )
    movimento_final_origem = MovimentacaoEstoque.objects.filter(
        referencia=f"composicao:{producao.id}:final"
    ).first()
    alocacao_final = (
        movimento_final_origem.alocacoes_lote.select_related("lote").first()
        if movimento_final_origem
        else None
    )
    if alocacao_final:
        consumir_lotes_movimentacao(
            movimentacao=movimento_final_cancelamento,
            quantidade=producao.quantidade_final,
            lote_id=alocacao_final.lote_id,
            exigir_lote=True,
        )
    else:
        reconciliar_lotes_reducao_inventario(
            produto=producao.produto_final,
            filial=producao.filial,
            saldo_novo=estoque_final.quantidade_atual,
            movimentacao=movimento_final_cancelamento,
        )

    for item in producao.itens.select_related("produto_componente"):
        estoque_componente, _ = Estoque.objects.select_for_update().get_or_create(
            produto=item.produto_componente,
            filial=producao.filial,
        )
        estoque_componente.quantidade_atual += item.quantidade_consumida
        estoque_componente.full_clean()
        estoque_componente.save()
        movimento_reversao = MovimentacaoEstoque.objects.create(
            produto=item.produto_componente,
            filial=producao.filial,
            tipo=TipoMovimentacaoEstoque.DESMEMBRAMENTO,
            quantidade=item.quantidade_consumida,
            motivo=f"Cancelamento da composicao {producao.id}: retorno do componente",
            referencia=f"composicao:{producao.id}:cancelamento:componente:{item.id}",
            custo_unitario=item.custo_unitario,
            custo_total=item.custo_total,
            usuario=usuario,
        )
        movimento_origem = MovimentacaoEstoque.objects.filter(
            referencia=f"composicao:{producao.id}:componente:{item.produto_componente_id}"
        ).first()
        if movimento_origem:
            restaurar_lotes_movimentacao(
                movimentacao_origem=movimento_origem,
                movimentacao_reversao=movimento_reversao,
            )

    producao.status = StatusProducaoComposicao.CANCELADO
    producao.cancelado_em = timezone.now()
    producao.observacao = f"{producao.observacao}\nCancelado: {motivo}".strip()
    producao.save(update_fields=["status", "cancelado_em", "observacao"])

    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="estoque",
        acao="CANCELAMENTO_COMPOSICAO",
        descricao=f"Composicao {producao.id} cancelada. Motivo: {motivo}.{_autorizacao_texto(supervisor)}",
        objeto_tipo="ProducaoComposicaoProduto",
        objeto_id=str(producao.id),
        ip=ip,
    )
    return producao


@transaction.atomic
def confirmar_ordem_producao_composicao(
    *,
    ordem,
    usuario,
    codigo_lote="",
    fabricacao=None,
    validade=None,
    supervisor=None,
    ip=None,
):
    ordem = (
        OrdemProducaoComposicao.objects.select_for_update()
        .select_related("composicao", "filial", "produto_final")
        .get(pk=ordem.pk)
    )
    if ordem.status != StatusOrdemProducaoComposicao.PLANEJADA:
        raise ValidationError("Apenas ordens planejadas podem ser produzidas.")
    producao = confirmar_producao_composicao(
        composicao=ordem.composicao,
        filial=ordem.filial,
        quantidade_final=ordem.quantidade_planejada,
        usuario=usuario,
        motivo=f"Ordem de produção {ordem.id}: {ordem.motivo}",
        observacao=ordem.observacao,
        codigo_lote=codigo_lote,
        fabricacao=fabricacao,
        validade=validade,
        supervisor=supervisor,
        ip=ip,
    )
    ordem.status = StatusOrdemProducaoComposicao.PRODUZIDA
    ordem.producao_gerada = producao
    ordem.concluido_em = timezone.now()
    ordem.save(update_fields=["status", "producao_gerada", "concluido_em", "atualizado_em"])
    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="estoque",
        acao="ORDEM_PRODUCAO_COMPOSICAO_CONFIRMADA",
        descricao=f"Ordem de produção {ordem.id} confirmou a produção {producao.id}.{_autorizacao_texto(supervisor)}",
        objeto_tipo="OrdemProducaoComposicao",
        objeto_id=str(ordem.id),
        ip=ip,
    )
    return ordem


@transaction.atomic
def cancelar_ordem_producao_composicao(*, ordem, usuario, motivo, supervisor=None, ip=None):
    if not motivo:
        raise ValidationError("Informe o motivo do cancelamento.")
    ordem = OrdemProducaoComposicao.objects.select_for_update().get(pk=ordem.pk)
    if ordem.status != StatusOrdemProducaoComposicao.PLANEJADA:
        raise ValidationError("Apenas ordens planejadas podem ser canceladas.")
    ordem.status = StatusOrdemProducaoComposicao.CANCELADA
    ordem.observacao = f"{ordem.observacao}\nCancelada: {motivo}".strip()
    ordem.concluido_em = timezone.now()
    ordem.save(update_fields=["status", "observacao", "concluido_em", "atualizado_em"])
    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="estoque",
        acao="ORDEM_PRODUCAO_COMPOSICAO_CANCELADA",
        descricao=f"Ordem de produção {ordem.id} cancelada. Motivo: {motivo}.{_autorizacao_texto(supervisor)}",
        objeto_tipo="OrdemProducaoComposicao",
        objeto_id=str(ordem.id),
        ip=ip,
    )
    return ordem


@transaction.atomic
def confirmar_desmembramento_multidestino(
    *,
    filial,
    produto_origem,
    quantidade_origem,
    destinos,
    usuario,
    motivo,
    tipo=TipoDesmembramentoProduto.SIMPLES,
    observacao="",
    supervisor=None,
    ip=None,
):
    if quantidade_origem <= 0:
        raise ValidationError("As quantidades do desmembramento devem ser maiores que zero.")
    destinos = list(destinos or [])
    if not destinos:
        raise ValidationError("Inclua ao menos um produto destino no desmembramento.")
    for destino in destinos:
        if destino["quantidade"] <= 0:
            raise ValidationError("As quantidades do desmembramento devem ser maiores que zero.")
        if produto_origem == destino["produto"]:
            raise ValidationError("Produto origem e produto destino devem ser diferentes.")
        tipo_saida = destino.get("tipo_saida") or TipoSaidaDesmembramento.VENDAVEL
        if (
            tipo_saida != TipoSaidaDesmembramento.PERDA
            and destino["produto"].exige_lote
            and not (destino.get("lote") or "").strip()
        ):
            raise ValidationError(f"O produto destino {destino['produto']} exige lote.")

    estoque_origem, _ = Estoque.objects.select_for_update().get_or_create(produto=produto_origem, filial=filial)
    if estoque_origem.quantidade_disponivel < quantidade_origem:
        raise ValidationError("Estoque insuficiente para desmembrar o produto origem.")

    custo_origem = Decimal(produto_origem.preco_custo)
    custo_total_origem = custo_origem * quantidade_origem
    quantidade_total_destinos = sum(destino["quantidade"] for destino in destinos)
    if quantidade_total_destinos <= 0:
        raise ValidationError("As quantidades do desmembramento devem ser maiores que zero.")
    conservacao = _resumo_conservacao_massa(
        tipo=tipo,
        produto_origem=produto_origem,
        quantidade_origem=quantidade_origem,
        destinos=destinos,
    )
    if not conservacao["valida"]:
        if conservacao["excesso"]:
            detalhe = f"Excesso: {conservacao['excesso']:.3f} KG."
        else:
            detalhe = f"Quantidade nao classificada: {conservacao['nao_classificada']:.3f} KG."
        raise ValidationError(
            f"Conservacao de massa invalida: {quantidade_origem:.3f} KG de origem devem corresponder "
            f"aos {quantidade_total_destinos:.3f} KG de destinos, incluindo perdas. {detalhe}"
        )
    custo_unitario_base = custo_total_origem / quantidade_total_destinos

    desmembramento = DesmembramentoProduto.objects.create(
        empresa=filial.empresa,
        filial=filial,
        produto_origem=produto_origem,
        quantidade_origem=quantidade_origem,
        custo_total_origem=custo_total_origem,
        tipo=tipo,
        usuario=usuario,
        motivo=motivo,
        observacao=observacao,
    )

    estoque_origem.quantidade_atual -= quantidade_origem
    estoque_origem.full_clean()
    estoque_origem.save()
    movimento_origem = MovimentacaoEstoque.objects.create(
        produto=produto_origem,
        filial=filial,
        tipo=TipoMovimentacaoEstoque.DESMEMBRAMENTO,
        quantidade=-quantidade_origem,
        motivo=f"Desmembramento {desmembramento.id}: {motivo}",
        referencia=f"desmembramento:{desmembramento.id}:origem",
        custo_unitario=custo_origem,
        custo_total=custo_total_origem,
        usuario=usuario,
    )
    consumir_lotes_movimentacao(
        movimentacao=movimento_origem,
        quantidade=quantidade_origem,
    )

    for destino in destinos:
        produto_destino = destino["produto"]
        quantidade_destino = destino["quantidade"]
        tipo_saida = destino.get("tipo_saida") or TipoSaidaDesmembramento.VENDAVEL
        custo_total_item = custo_unitario_base * quantidade_destino
        percentual_rendimento = ((quantidade_destino / quantidade_origem) * Decimal("100")).quantize(Decimal("0.01"))
        item = ItemDesmembramentoProduto.objects.create(
            desmembramento=desmembramento,
            produto_destino=produto_destino,
            quantidade_gerada=quantidade_destino,
            unidade=produto_destino.unidade,
            custo_unitario_calculado=custo_unitario_base,
            custo_total=custo_total_item,
            percentual_rendimento=percentual_rendimento,
            percentual_rendimento_esperado=destino.get("percentual_rendimento_esperado"),
            lote=destino.get("lote", ""),
            validade=destino.get("validade"),
            tipo_saida=tipo_saida,
        )
        if tipo_saida == TipoSaidaDesmembramento.PERDA:
            preco_venda_destino = Decimal(produto_destino.preco_venda)
            PerdaEstoque.objects.create(
                produto=produto_destino,
                filial=filial,
                usuario=usuario,
                desmembramento_item=item,
                tipo=TipoPerdaEstoque.QUEBRA,
                quantidade=quantidade_destino,
                motivo=f"Desmembramento {desmembramento.id}: {motivo}",
                custo_unitario_no_momento=custo_unitario_base,
                preco_venda_no_momento=preco_venda_destino,
                valor_custo_estimado=custo_total_item,
                valor_venda_estimado=preco_venda_destino * quantidade_destino,
            )
            MovimentacaoEstoque.objects.create(
                produto=produto_destino,
                filial=filial,
                tipo=TipoMovimentacaoEstoque.PERDA,
                quantidade=-quantidade_destino,
                motivo=f"Desmembramento {desmembramento.id}: perda/descarte gerado",
                referencia=f"desmembramento:{desmembramento.id}:perda:item:{item.id}",
                custo_unitario=custo_unitario_base,
                custo_total=custo_total_item,
                usuario=usuario,
            )
        else:
            estoque_destino, _ = Estoque.objects.select_for_update().get_or_create(produto=produto_destino, filial=filial)
            estoque_destino.quantidade_atual += quantidade_destino
            estoque_destino.full_clean()
            estoque_destino.save()
            movimento_destino = MovimentacaoEstoque.objects.create(
                produto=produto_destino,
                filial=filial,
                tipo=TipoMovimentacaoEstoque.DESMEMBRAMENTO,
                quantidade=quantidade_destino,
                motivo=f"Desmembramento {desmembramento.id}: entrada de destino",
                referencia=f"desmembramento:{desmembramento.id}:item:{item.id}",
                custo_unitario=custo_unitario_base,
                custo_total=custo_total_item,
                usuario=usuario,
            )
            if item.lote:
                criar_lote_movimentacao(
                    movimentacao=movimento_destino,
                    codigo_lote=item.lote,
                    quantidade=quantidade_destino,
                    custo_unitario=custo_unitario_base,
                    validade=item.validade,
                )

    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="estoque",
        acao="DESMEMBRAMENTO_PRODUTO",
        descricao=(
            f"Desmembramento {desmembramento.id}: {quantidade_origem} de {produto_origem} gerou "
            f"{len(destinos)} destino(s). Motivo: {motivo}.{_autorizacao_texto(supervisor)}"
        ),
        objeto_tipo="DesmembramentoProduto",
        objeto_id=str(desmembramento.id),
        ip=ip,
    )
    return desmembramento


def confirmar_desmembramento_simples(
    *,
    filial,
    produto_origem,
    quantidade_origem,
    produto_destino,
    quantidade_destino,
    usuario,
    motivo,
    tipo=TipoDesmembramentoProduto.SIMPLES,
    tipo_saida_destino=TipoSaidaDesmembramento.VENDAVEL,
    observacao="",
    supervisor=None,
    ip=None,
):
    return confirmar_desmembramento_multidestino(
        filial=filial,
        produto_origem=produto_origem,
        quantidade_origem=quantidade_origem,
        destinos=[{"produto": produto_destino, "quantidade": quantidade_destino, "tipo_saida": tipo_saida_destino}],
        usuario=usuario,
        motivo=motivo,
        tipo=tipo,
        observacao=observacao,
        supervisor=supervisor,
        ip=ip,
    )


def simular_desmembramento_multidestino(
    *,
    filial,
    produto_origem,
    quantidade_origem,
    destinos,
    tipo=TipoDesmembramentoProduto.SIMPLES,
    **_,
):
    if quantidade_origem <= 0:
        raise ValidationError("As quantidades do desmembramento devem ser maiores que zero.")
    destinos = list(destinos or [])
    if not destinos:
        raise ValidationError("Inclua ao menos um produto destino no desmembramento.")
    for destino in destinos:
        if destino["quantidade"] <= 0:
            raise ValidationError("As quantidades do desmembramento devem ser maiores que zero.")
        if produto_origem == destino["produto"]:
            raise ValidationError("Produto origem e produto destino devem ser diferentes.")

    estoque_origem = Estoque.objects.filter(produto=produto_origem, filial=filial).first()
    saldo_origem = estoque_origem.quantidade_disponivel if estoque_origem else Decimal("0.000")
    custo_origem = Decimal(produto_origem.preco_custo)
    custo_total_origem = custo_origem * quantidade_origem
    quantidade_total_destinos = sum(destino["quantidade"] for destino in destinos)
    if quantidade_total_destinos <= 0:
        raise ValidationError("As quantidades do desmembramento devem ser maiores que zero.")
    conservacao = _resumo_conservacao_massa(
        tipo=tipo,
        produto_origem=produto_origem,
        quantidade_origem=quantidade_origem,
        destinos=destinos,
    )
    custo_unitario_destino = custo_total_origem / quantidade_total_destinos
    destinos_previstos = [
        {
            "produto": destino["produto"],
            "quantidade": destino["quantidade"],
            "tipo_saida": destino.get("tipo_saida") or TipoSaidaDesmembramento.VENDAVEL,
            "percentual_rendimento_esperado": destino.get("percentual_rendimento_esperado"),
            "percentual_rendimento": ((destino["quantidade"] / quantidade_origem) * Decimal("100")).quantize(Decimal("0.01")),
            "rendimento_abaixo_esperado": (
                destino.get("percentual_rendimento_esperado") is not None
                and ((destino["quantidade"] / quantidade_origem) * Decimal("100")).quantize(Decimal("0.01"))
                < destino.get("percentual_rendimento_esperado")
            ),
            "lote": destino.get("lote", ""),
            "validade": destino.get("validade"),
            "custo_total": custo_unitario_destino * destino["quantidade"],
        }
        for destino in destinos
    ]

    return {
        "filial": filial,
        "produto_origem": produto_origem,
        "quantidade_origem": quantidade_origem,
        "quantidade_destino": quantidade_total_destinos,
        "destinos": destinos_previstos,
        "saldo_origem": saldo_origem,
        "saldo_origem_apos": saldo_origem - quantidade_origem,
        "estoque_suficiente": saldo_origem >= quantidade_origem,
        "custo_total_origem": custo_total_origem,
        "custo_unitario_destino": custo_unitario_destino,
        "conservacao_massa_aplicada": conservacao["aplicavel"],
        "conservacao_massa_valida": conservacao["valida"],
        "excesso_quantidade": conservacao["excesso"],
        "quantidade_nao_classificada": conservacao["nao_classificada"],
        "rendimento_total": conservacao["rendimento_total"],
    }


def simular_desmembramento_simples(*, filial, produto_origem, quantidade_origem, produto_destino, quantidade_destino, **kwargs):
    return simular_desmembramento_multidestino(
        filial=filial,
        produto_origem=produto_origem,
        quantidade_origem=quantidade_origem,
        destinos=[
            {
                "produto": produto_destino,
                "quantidade": quantidade_destino,
                "tipo_saida": kwargs.get("tipo_saida_destino") or TipoSaidaDesmembramento.VENDAVEL,
                "percentual_rendimento_esperado": kwargs.get("percentual_rendimento_esperado"),
                "lote": kwargs.get("lote", ""),
                "validade": kwargs.get("validade"),
            }
        ],
    )


@transaction.atomic
def cancelar_desmembramento_produto(*, desmembramento, usuario, motivo, supervisor=None, ip=None):
    if not motivo:
        raise ValidationError("Informe o motivo do cancelamento.")

    desmembramento = (
        DesmembramentoProduto.objects.select_for_update()
        .select_related("filial", "produto_origem")
        .prefetch_related("itens__produto_destino")
        .get(pk=desmembramento.pk)
    )
    if desmembramento.status != StatusDesmembramentoProduto.CONFIRMADO:
        raise ValidationError("Apenas desmembramentos confirmados podem ser cancelados.")

    estoque_origem, _ = Estoque.objects.select_for_update().get_or_create(
        produto=desmembramento.produto_origem,
        filial=desmembramento.filial,
    )
    itens = list(desmembramento.itens.select_related("produto_destino"))
    if not itens:
        raise ValidationError("Desmembramento sem itens de destino não pode ser cancelado.")

    estoques_destino = {}
    for item in itens:
        if item.tipo_saida == TipoSaidaDesmembramento.PERDA:
            continue
        estoque_destino, _ = Estoque.objects.select_for_update().get_or_create(
            produto=item.produto_destino,
            filial=desmembramento.filial,
        )
        if estoque_destino.quantidade_disponivel < item.quantidade_gerada:
            raise ValidationError(
                f"Produto destino {item.produto_destino} nao possui saldo suficiente para reverter o desmembramento."
            )
        estoques_destino[item.id] = estoque_destino

    for item in itens:
        if item.tipo_saida == TipoSaidaDesmembramento.PERDA:
            item.perdas_geradas.all().delete()
            MovimentacaoEstoque.objects.create(
                produto=item.produto_destino,
                filial=desmembramento.filial,
                tipo=TipoMovimentacaoEstoque.PERDA,
                quantidade=item.quantidade_gerada,
                motivo=f"Cancelamento do desmembramento {desmembramento.id}: perda/descarte revertida",
                referencia=f"desmembramento:{desmembramento.id}:cancelamento:perda:item:{item.id}",
                custo_unitario=item.custo_unitario_calculado,
                custo_total=item.custo_total,
                usuario=usuario,
            )
            continue
        estoque_destino = estoques_destino[item.id]
        estoque_destino.quantidade_atual -= item.quantidade_gerada
        estoque_destino.full_clean()
        estoque_destino.save()
        movimento_cancelamento = MovimentacaoEstoque.objects.create(
            produto=item.produto_destino,
            filial=desmembramento.filial,
            tipo=TipoMovimentacaoEstoque.DESMEMBRAMENTO,
            quantidade=-item.quantidade_gerada,
            motivo=f"Cancelamento do desmembramento {desmembramento.id}: {motivo}",
            referencia=f"desmembramento:{desmembramento.id}:cancelamento:item:{item.id}",
            custo_unitario=item.custo_unitario_calculado,
            custo_total=item.custo_total,
            usuario=usuario,
        )
        if item.lote:
            consumir_lotes_movimentacao(
                movimentacao=movimento_cancelamento,
                quantidade=item.quantidade_gerada,
                codigo_lote=item.lote,
                exigir_lote=True,
            )
        else:
            reconciliar_lotes_reducao_inventario(
                produto=item.produto_destino,
                filial=desmembramento.filial,
                saldo_novo=estoque_destino.quantidade_atual,
                movimentacao=movimento_cancelamento,
            )

    estoque_origem.quantidade_atual += desmembramento.quantidade_origem
    estoque_origem.full_clean()
    estoque_origem.save()
    movimento_retorno_origem = MovimentacaoEstoque.objects.create(
        produto=desmembramento.produto_origem,
        filial=desmembramento.filial,
        tipo=TipoMovimentacaoEstoque.DESMEMBRAMENTO,
        quantidade=desmembramento.quantidade_origem,
        motivo=f"Cancelamento do desmembramento {desmembramento.id}: retorno da origem",
        referencia=f"desmembramento:{desmembramento.id}:cancelamento:origem",
        custo_unitario=desmembramento.custo_total_origem / desmembramento.quantidade_origem,
        custo_total=desmembramento.custo_total_origem,
        usuario=usuario,
    )
    movimento_baixa_origem = MovimentacaoEstoque.objects.filter(
        referencia=f"desmembramento:{desmembramento.id}:origem"
    ).first()
    if movimento_baixa_origem:
        restaurar_lotes_movimentacao(
            movimentacao_origem=movimento_baixa_origem,
            movimentacao_reversao=movimento_retorno_origem,
        )

    desmembramento.status = StatusDesmembramentoProduto.CANCELADO
    desmembramento.cancelado_em = timezone.now()
    desmembramento.observacao = f"{desmembramento.observacao}\nCancelado: {motivo}".strip()
    desmembramento.save(update_fields=["status", "cancelado_em", "observacao"])

    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="estoque",
        acao="CANCELAMENTO_DESMEMBRAMENTO",
        descricao=f"Desmembramento {desmembramento.id} cancelado. Motivo: {motivo}.{_autorizacao_texto(supervisor)}",
        objeto_tipo="DesmembramentoProduto",
        objeto_id=str(desmembramento.id),
        ip=ip,
    )
    return desmembramento
