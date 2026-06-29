from django.core.exceptions import ValidationError
from django.db import transaction

from apps.estoque.models import TipoMovimentacaoEstoque, movimentar_estoque

from .models import StatusEntradaCompra


def finalizar_entrada_compra(entrada):
    if entrada.status != StatusEntradaCompra.RASCUNHO:
        raise ValidationError("Apenas entradas em rascunho podem ser finalizadas.")

    itens = list(entrada.itens.select_related("produto"))
    if not itens:
        raise ValidationError("Inclua ao menos um item antes de finalizar a entrada.")

    with transaction.atomic():
        total_produtos = 0
        for item in itens:
            if item.quantidade <= 0:
                raise ValidationError("Quantidade deve ser maior que zero.")
            if item.custo_unitario < 0:
                raise ValidationError("Custo unitario nao pode ser negativo.")

            item.total = item.quantidade * item.custo_unitario
            item.save(update_fields=["total"])
            total_produtos += item.total

            movimentar_estoque(
                produto=item.produto,
                filial=entrada.filial,
                tipo=TipoMovimentacaoEstoque.ENTRADA,
                quantidade=item.quantidade,
                usuario=entrada.usuario,
                motivo="Entrada de compra",
                referencia=f"entrada_compra:{entrada.id}",
                custo_unitario=item.custo_unitario,
            )

            if item.atualizar_preco_custo:
                item.produto.preco_custo = item.custo_unitario
                item.produto.save(update_fields=["preco_custo", "updated_at"])

        entrada.total_produtos = total_produtos
        entrada.status = StatusEntradaCompra.FINALIZADA
        entrada.save(update_fields=["total_produtos", "status", "updated_at"])
        return entrada
