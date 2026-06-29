from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.auditoria.models import LogAuditoria
from apps.estoque.models import TipoMovimentacaoEstoque, movimentar_estoque
from apps.promocoes.services import preco_atual_produto

from .models import ItemVenda, PagamentoVenda, StatusVenda, Venda


def calcular_item(produto, quantidade):
    preco = preco_atual_produto(produto)
    return preco * quantidade


def finalizar_venda(*, caixa, usuario, itens, forma_pagamento, desconto=Decimal("0.00"), cliente=None):
    if not itens:
        raise ValidationError("Inclua ao menos um item na venda.")

    with transaction.atomic():
        venda = Venda.objects.create(
            filial=caixa.filial,
            caixa=caixa,
            cliente=cliente,
            usuario=usuario,
            desconto=desconto,
            status=StatusVenda.ABERTA,
        )

        total_bruto = Decimal("0.00")
        for item in itens:
            produto = item["produto"]
            quantidade = item["quantidade"]
            total_item = calcular_item(produto, quantidade)
            total_bruto += total_item

            ItemVenda.objects.create(
                venda=venda,
                produto=produto,
                quantidade=quantidade,
                preco_unitario_venda=preco_atual_produto(produto),
                desconto=Decimal("0.00"),
                total=total_item,
                custo_unitario_no_momento=produto.preco_custo,
            )
            movimentar_estoque(
                produto=produto,
                filial=caixa.filial,
                tipo=TipoMovimentacaoEstoque.VENDA,
                quantidade=quantidade,
                usuario=usuario,
                motivo="Venda PDV",
                referencia=f"venda:{venda.id}",
                custo_unitario=produto.preco_custo,
            )

        total_liquido = total_bruto - desconto
        if total_liquido < 0:
            raise ValidationError("Desconto nao pode ser maior que o total da venda.")

        venda.total_bruto = total_bruto
        venda.total_liquido = total_liquido
        venda.status = StatusVenda.FINALIZADA
        venda.save(update_fields=["total_bruto", "total_liquido", "status"])

        PagamentoVenda.objects.create(
            venda=venda,
            forma_pagamento=forma_pagamento,
            valor=total_liquido,
        )

        return venda


@transaction.atomic
def cancelar_venda(*, venda, usuario, motivo, ip=None):
    venda = Venda.objects.select_for_update().get(pk=venda.pk)
    if venda.status != StatusVenda.FINALIZADA:
        raise ValidationError("Apenas vendas finalizadas podem ser canceladas.")
    if not motivo:
        raise ValidationError("Informe o motivo do cancelamento.")

    for item in venda.itens.select_related("produto"):
        movimentar_estoque(
            produto=item.produto,
            filial=venda.filial,
            tipo=TipoMovimentacaoEstoque.DEVOLUCAO,
            quantidade=item.quantidade,
            usuario=usuario,
            motivo=f"Cancelamento de venda: {motivo}",
            referencia=f"cancelamento_venda:{venda.id}",
            custo_unitario=item.custo_unitario_no_momento,
        )

    venda.status = StatusVenda.CANCELADA
    venda.save(update_fields=["status"])

    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="vendas",
        acao="CANCELAMENTO_VENDA",
        descricao=f"Venda {venda.id} cancelada. Motivo: {motivo}",
        objeto_tipo="Venda",
        objeto_id=str(venda.id),
        ip=ip,
    )
    return venda
