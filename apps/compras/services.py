from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.auditoria.models import LogAuditoria
from apps.estoque.models import TipoMovimentacaoEstoque, movimentar_estoque

from .models import StatusEntradaCompra


def finalizar_entrada_compra(entrada, *, supervisor=None, ip=None):
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
        _criar_conta_pagar_compra(entrada)
        LogAuditoria.objects.create(
            usuario=entrada.usuario,
            modulo="compras",
            acao="FINALIZACAO_ENTRADA",
            descricao=(
                f"Entrada {entrada.id} finalizada com {len(itens)} item(ns), total R$ {total_produtos}. "
                f"Autorizado por: {supervisor or '-'}."
            ),
            objeto_tipo="EntradaCompra",
            objeto_id=str(entrada.id),
            ip=ip,
        )
        return entrada


def cancelar_entrada_compra(entrada, *, usuario, motivo, supervisor=None, ip=None):
    motivo = (motivo or "").strip()
    if not motivo:
        raise ValidationError("Informe o motivo do cancelamento.")
    if entrada.status != StatusEntradaCompra.FINALIZADA:
        raise ValidationError("Apenas entradas finalizadas podem ser canceladas.")

    itens = list(entrada.itens.select_related("produto"))
    if not itens:
        raise ValidationError("Entrada sem itens nao pode ser cancelada.")

    with transaction.atomic():
        entrada = entrada.__class__.objects.select_for_update().get(pk=entrada.pk)
        if entrada.status != StatusEntradaCompra.FINALIZADA:
            raise ValidationError("Apenas entradas finalizadas podem ser canceladas.")

        for conta in entrada.contas_financeiras.select_for_update():
            from apps.financeiro.services import cancelar_conta

            cancelar_conta(conta=conta, usuario=usuario, motivo=f"Cancelamento da entrada de compra {entrada.id}: {motivo}", ip=ip)

        for item in itens:
            movimentar_estoque(
                produto=item.produto,
                filial=entrada.filial,
                tipo=TipoMovimentacaoEstoque.SAIDA,
                quantidade=item.quantidade,
                usuario=usuario,
                motivo=f"Cancelamento da entrada de compra: {motivo}",
                referencia=f"entrada_compra_cancelamento:{entrada.id}",
                custo_unitario=item.custo_unitario,
            )

        entrada.status = StatusEntradaCompra.CANCELADA
        entrada.save(update_fields=["status", "updated_at"])
        LogAuditoria.objects.create(
            usuario=usuario,
            modulo="compras",
            acao="CANCELAMENTO_ENTRADA",
            descricao=(
                f"Entrada {entrada.id} cancelada com {len(itens)} item(ns). Motivo: {motivo}. "
                f"Autorizado por: {supervisor or '-'}."
            ),
            objeto_tipo="EntradaCompra",
            objeto_id=str(entrada.id),
            ip=ip,
        )
        return entrada


def _criar_conta_pagar_compra(entrada):
    if not entrada.gerar_conta_financeira or entrada.total_produtos <= 0:
        return None

    from apps.financeiro.models import CategoriaFinanceira, ContaFinanceira, TipoContaFinanceira

    categoria, _ = CategoriaFinanceira.objects.get_or_create(
        nome="Compras de mercadorias",
        defaults={"tipo": TipoContaFinanceira.PAGAR},
    )
    vencimento = entrada.vencimento_financeiro or entrada.data_emissao or timezone.localdate()
    conta, criada = ContaFinanceira.objects.get_or_create(
        entrada_compra=entrada,
        tipo=TipoContaFinanceira.PAGAR,
        defaults={
            "descricao": f"Compra {entrada.id} - {entrada.fornecedor}",
            "categoria": categoria,
            "filial": entrada.filial,
            "fornecedor": entrada.fornecedor,
            "valor": entrada.total_produtos,
            "vencimento": vencimento,
            "usuario": entrada.usuario,
        },
    )
    if not criada:
        conta.descricao = f"Compra {entrada.id} - {entrada.fornecedor}"
        conta.categoria = categoria
        conta.filial = entrada.filial
        conta.fornecedor = entrada.fornecedor
        conta.valor = entrada.total_produtos
        conta.vencimento = vencimento
        conta.save(update_fields=["descricao", "categoria", "filial", "fornecedor", "valor", "vencimento", "atualizado_em"])
    return conta
