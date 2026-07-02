from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.auditoria.models import LogAuditoria

from .models import Estoque, InventarioEstoque, MovimentacaoEstoque, PerdaEstoque, StatusInventario, TipoMovimentacaoEstoque, movimentar_estoque


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
