from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.auditoria.models import LogAuditoria

from .models import (
    ComposicaoProduto,
    DesmembramentoProduto,
    Estoque,
    InventarioEstoque,
    ItemProducaoComposicaoProduto,
    ItemDesmembramentoProduto,
    MovimentacaoEstoque,
    PerdaEstoque,
    ProducaoComposicaoProduto,
    StatusDesmembramentoProduto,
    StatusInventario,
    StatusProducaoComposicao,
    TipoDesmembramentoProduto,
    TipoMovimentacaoEstoque,
    TipoPerdaEstoque,
    TipoSaidaDesmembramento,
    movimentar_estoque,
)


def _autorizacao_texto(supervisor):
    return f" Autorizado por: {supervisor}." if supervisor else ""


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
            MovimentacaoEstoque.objects.create(
                produto=item.produto,
                filial=inventario.filial,
                tipo=TipoMovimentacaoEstoque.AJUSTE,
                quantidade=item.diferenca,
                motivo=f"Inventario: {inventario.descricao}",
                referencia=f"inventario:{inventario.id}",
                usuario=usuario,
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
def confirmar_producao_composicao(*, composicao, filial, quantidade_final, usuario, motivo, observacao="", supervisor=None, ip=None):
    if not motivo:
        raise ValidationError("Informe o motivo da producao.")
    if quantidade_final <= 0:
        raise ValidationError("Quantidade final da composicao deve ser maior que zero.")

    composicao = (
        ComposicaoProduto.objects.select_for_update()
        .select_related("empresa", "filial", "produto_final")
        .prefetch_related("itens__produto_componente")
        .get(pk=composicao.pk)
    )
    if not composicao.is_active:
        raise ValidationError("Composicao inativa nao pode ser produzida.")
    if composicao.filial_id and composicao.filial_id != filial.id:
        raise ValidationError("Composicao pertence a outra filial.")

    itens_receita = list(composicao.itens.select_related("produto_componente"))
    if not itens_receita:
        raise ValidationError("Inclua ao menos um componente na composicao.")
    fator = quantidade_final / composicao.quantidade_final

    consumos = []
    custo_total = Decimal("0.00")
    for item_receita in itens_receita:
        if item_receita.produto_componente_id == composicao.produto_final_id:
            raise ValidationError("Produto final nao pode ser componente da propria composicao.")
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
        MovimentacaoEstoque.objects.create(
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

    estoque_final, _ = Estoque.objects.select_for_update().get_or_create(produto=composicao.produto_final, filial=filial)
    estoque_final.quantidade_atual += quantidade_final
    estoque_final.full_clean()
    estoque_final.save()
    MovimentacaoEstoque.objects.create(
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
        raise ValidationError("Produto final nao possui saldo suficiente para cancelar a composicao.")

    estoque_final.quantidade_atual -= producao.quantidade_final
    estoque_final.full_clean()
    estoque_final.save()
    MovimentacaoEstoque.objects.create(
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

    for item in producao.itens.select_related("produto_componente"):
        estoque_componente, _ = Estoque.objects.select_for_update().get_or_create(
            produto=item.produto_componente,
            filial=producao.filial,
        )
        estoque_componente.quantidade_atual += item.quantidade_consumida
        estoque_componente.full_clean()
        estoque_componente.save()
        MovimentacaoEstoque.objects.create(
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

    estoque_origem, _ = Estoque.objects.select_for_update().get_or_create(produto=produto_origem, filial=filial)
    if estoque_origem.quantidade_disponivel < quantidade_origem:
        raise ValidationError("Estoque insuficiente para desmembrar o produto origem.")

    custo_origem = Decimal(produto_origem.preco_custo)
    custo_total_origem = custo_origem * quantidade_origem
    quantidade_total_destinos = sum(destino["quantidade"] for destino in destinos)
    if quantidade_total_destinos <= 0:
        raise ValidationError("As quantidades do desmembramento devem ser maiores que zero.")
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
    MovimentacaoEstoque.objects.create(
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
            MovimentacaoEstoque.objects.create(
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


def simular_desmembramento_multidestino(*, filial, produto_origem, quantidade_origem, destinos, **_):
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
        raise ValidationError("Desmembramento sem itens de destino nao pode ser cancelado.")

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
        MovimentacaoEstoque.objects.create(
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

    estoque_origem.quantidade_atual += desmembramento.quantidade_origem
    estoque_origem.full_clean()
    estoque_origem.save()
    MovimentacaoEstoque.objects.create(
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
