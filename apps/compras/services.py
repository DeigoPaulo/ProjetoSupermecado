from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.auditoria.models import LogAuditoria
from apps.estoque.models import TipoMovimentacaoEstoque, movimentar_estoque

from .models import (
    EntradaCompra,
    ItemEntradaCompra,
    ItemPedidoCompra,
    PedidoCompra,
    PrecoRespostaCotacao,
    RespostaCotacaoFornecedor,
    StatusCotacaoCompra,
    StatusEntradaCompra,
    StatusPedidoCompra,
)


def abrir_cotacao_compra(cotacao, *, usuario, ip=None):
    with transaction.atomic():
        cotacao = cotacao.__class__.objects.select_for_update().get(pk=cotacao.pk)
        if cotacao.status != StatusCotacaoCompra.RASCUNHO:
            raise ValidationError("Apenas cotacoes em rascunho podem ser abertas.")
        if not cotacao.itens.exists():
            raise ValidationError("Inclua ao menos um item antes de abrir a cotacao.")
        cotacao.status = StatusCotacaoCompra.ABERTA
        cotacao.save(update_fields=["status", "updated_at"])
        LogAuditoria.objects.create(
            usuario=usuario,
            modulo="compras",
            acao="ABERTURA_COTACAO_COMPRA",
            descricao=f"Cotacao de compra {cotacao.id} aberta para propostas com {cotacao.itens.count()} item(ns).",
            objeto_tipo="CotacaoCompra",
            objeto_id=str(cotacao.id),
            ip=ip,
        )
        return cotacao


def gerar_pedido_da_resposta(resposta, *, usuario, ip=None):
    with transaction.atomic():
        resposta = (
            RespostaCotacaoFornecedor.objects.select_for_update()
            .select_related("cotacao", "fornecedor", "cotacao__filial")
            .get(pk=resposta.pk)
        )
        cotacao = resposta.cotacao.__class__.objects.select_for_update().get(pk=resposta.cotacao_id)
        if resposta.fornecedor.empresa_id and resposta.fornecedor.empresa_id != cotacao.filial.empresa_id:
            raise ValidationError("Fornecedor informado pertence a outra empresa.")
        if cotacao.status != StatusCotacaoCompra.ABERTA:
            raise ValidationError("Apenas cotacoes abertas podem gerar pedido.")
        if PedidoCompra.objects.filter(cotacao_origem=cotacao).exists():
            raise ValidationError("Esta cotacao ja possui um pedido vinculado.")

        itens_cotacao = list(cotacao.itens.select_related("produto"))
        precos = {
            preco.item_id: preco
            for preco in PrecoRespostaCotacao.objects.select_related("item", "item__produto").filter(resposta=resposta)
        }
        if not itens_cotacao or any(
            item.id not in precos
            or not precos[item.id].disponivel
            or precos[item.id].custo_unitario is None
            for item in itens_cotacao
        ):
            raise ValidationError("A proposta escolhida deve atender todos os itens da cotacao.")

        pedido = PedidoCompra.objects.create(
            cotacao_origem=cotacao,
            fornecedor=resposta.fornecedor,
            filial=cotacao.filial,
            usuario=usuario,
            referencia=f"COT-{cotacao.id}",
            observacoes=f"Pedido gerado da cotacao {cotacao.id}. {resposta.observacoes}".strip(),
            status=StatusPedidoCompra.RASCUNHO,
        )
        total = Decimal("0.00")
        itens_pedido = []
        for item in itens_cotacao:
            custo = precos[item.id].custo_unitario
            item_total = item.quantidade * custo
            total += item_total
            itens_pedido.append(
                ItemPedidoCompra(
                    pedido=pedido,
                    produto=item.produto,
                    quantidade=item.quantidade,
                    custo_unitario_previsto=custo,
                    total_previsto=item_total,
                )
            )
        ItemPedidoCompra.objects.bulk_create(itens_pedido)
        pedido.total_previsto = total
        pedido.save(update_fields=["total_previsto", "updated_at"])
        resposta.selecionada = True
        resposta.save(update_fields=["selecionada", "updated_at"])
        cotacao.status = StatusCotacaoCompra.ENCERRADA
        cotacao.save(update_fields=["status", "updated_at"])
        LogAuditoria.objects.create(
            usuario=usuario,
            modulo="compras",
            acao="SELECAO_PROPOSTA_COTACAO",
            descricao=(
                f"Proposta de {resposta.fornecedor} selecionada na cotacao {cotacao.id}; "
                f"pedido {pedido.id} criado em rascunho por R$ {total}."
            ),
            objeto_tipo="CotacaoCompra",
            objeto_id=str(cotacao.id),
            ip=ip,
        )
        return pedido


def enviar_pedido_compra(pedido, *, usuario, ip=None):
    if pedido.status != StatusPedidoCompra.RASCUNHO:
        raise ValidationError("Apenas pedidos em rascunho podem ser enviados.")

    with transaction.atomic():
        pedido = PedidoCompra.objects.select_for_update().get(pk=pedido.pk)
        if pedido.status != StatusPedidoCompra.RASCUNHO:
            raise ValidationError("Apenas pedidos em rascunho podem ser enviados.")

        itens = list(pedido.itens.select_related("produto"))
        if not itens:
            raise ValidationError("Inclua ao menos um item antes de enviar o pedido.")

        total = 0
        for item in itens:
            if item.quantidade <= 0:
                raise ValidationError("Quantidade deve ser maior que zero.")
            if item.custo_unitario_previsto < 0:
                raise ValidationError("Custo previsto nao pode ser negativo.")
            item.total_previsto = item.quantidade * item.custo_unitario_previsto
            item.save(update_fields=["total_previsto"])
            total += item.total_previsto

        pedido.total_previsto = total
        pedido.status = StatusPedidoCompra.ENVIADO
        pedido.enviado_em = timezone.now()
        pedido.save(update_fields=["total_previsto", "status", "enviado_em", "updated_at"])
        LogAuditoria.objects.create(
            usuario=usuario,
            modulo="compras",
            acao="ENVIO_PEDIDO_COMPRA",
            descricao=f"Pedido de compra {pedido.id} enviado ao fornecedor com {len(itens)} item(ns), total previsto R$ {total}.",
            objeto_tipo="PedidoCompra",
            objeto_id=str(pedido.id),
            ip=ip,
        )
        return pedido


def cancelar_pedido_compra(pedido, *, usuario, motivo, ip=None):
    motivo = (motivo or "").strip()
    if not motivo:
        raise ValidationError("Informe o motivo do cancelamento.")
    if pedido.status not in {StatusPedidoCompra.RASCUNHO, StatusPedidoCompra.ENVIADO}:
        raise ValidationError("Este pedido nao pode ser cancelado.")

    with transaction.atomic():
        pedido = PedidoCompra.objects.select_for_update().get(pk=pedido.pk)
        if pedido.status not in {StatusPedidoCompra.RASCUNHO, StatusPedidoCompra.ENVIADO}:
            raise ValidationError("Este pedido nao pode ser cancelado.")
        pedido.status = StatusPedidoCompra.CANCELADO
        pedido.cancelado_em = timezone.now()
        pedido.save(update_fields=["status", "cancelado_em", "updated_at"])
        LogAuditoria.objects.create(
            usuario=usuario,
            modulo="compras",
            acao="CANCELAMENTO_PEDIDO_COMPRA",
            descricao=f"Pedido de compra {pedido.id} cancelado. Motivo: {motivo}.",
            objeto_tipo="PedidoCompra",
            objeto_id=str(pedido.id),
            ip=ip,
        )
        return pedido


def converter_pedido_em_entrada(pedido, *, usuario, ip=None):
    with transaction.atomic():
        pedido = PedidoCompra.objects.select_for_update().select_related("fornecedor", "filial").get(pk=pedido.pk)
        if pedido.fornecedor.empresa_id and pedido.fornecedor.empresa_id != pedido.filial.empresa_id:
            raise ValidationError("Fornecedor informado pertence a outra empresa.")
        if pedido.status != StatusPedidoCompra.ENVIADO:
            raise ValidationError("Apenas pedidos enviados podem gerar uma entrada.")
        if EntradaCompra.objects.filter(pedido_origem=pedido).exists():
            raise ValidationError("Este pedido ja possui uma entrada de compra vinculada.")

        itens_pedido = list(pedido.itens.select_related("produto"))
        if not itens_pedido:
            raise ValidationError("Pedido sem itens nao pode gerar entrada.")

        entrada = EntradaCompra.objects.create(
            pedido_origem=pedido,
            fornecedor=pedido.fornecedor,
            filial=pedido.filial,
            usuario=usuario,
            observacoes=(
                f"Entrada gerada a partir do pedido de compra {pedido.id}."
                + (f"\n{pedido.observacoes}" if pedido.observacoes else "")
            ),
            status=StatusEntradaCompra.RASCUNHO,
            total_produtos=pedido.total_previsto,
        )
        ItemEntradaCompra.objects.bulk_create(
            [
                ItemEntradaCompra(
                    entrada=entrada,
                    produto=item.produto,
                    quantidade=item.quantidade,
                    custo_unitario=item.custo_unitario_previsto,
                    total=item.quantidade * item.custo_unitario_previsto,
                    atualizar_preco_custo=True,
                )
                for item in itens_pedido
            ]
        )
        pedido.status = StatusPedidoCompra.CONVERTIDO
        pedido.save(update_fields=["status", "updated_at"])
        LogAuditoria.objects.create(
            usuario=usuario,
            modulo="compras",
            acao="CONVERSAO_PEDIDO_EM_ENTRADA",
            descricao=(
                f"Pedido de compra {pedido.id} convertido na entrada em rascunho {entrada.id}. "
                "Nenhum estoque ou financeiro foi movimentado."
            ),
            objeto_tipo="PedidoCompra",
            objeto_id=str(pedido.id),
            ip=ip,
        )
        return entrada


def finalizar_entrada_compra(entrada, *, supervisor=None, ip=None):
    if entrada.fornecedor.empresa_id and entrada.fornecedor.empresa_id != entrada.filial.empresa_id:
        raise ValidationError("Fornecedor informado pertence a outra empresa.")
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
                codigo_lote=item.codigo_lote,
                fabricacao=item.fabricacao,
                validade=item.validade,
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
                codigo_lote=item.codigo_lote,
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
    valor_financeiro = entrada.total_documento if entrada.total_documento is not None else entrada.total_produtos
    if not entrada.gerar_conta_financeira or valor_financeiro <= 0:
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
            "valor": valor_financeiro,
            "vencimento": vencimento,
            "usuario": entrada.usuario,
        },
    )
    if not criada:
        conta.descricao = f"Compra {entrada.id} - {entrada.fornecedor}"
        conta.categoria = categoria
        conta.filial = entrada.filial
        conta.fornecedor = entrada.fornecedor
        conta.valor = valor_financeiro
        conta.vencimento = vencimento
        conta.save(update_fields=["descricao", "categoria", "filial", "fornecedor", "valor", "vencimento", "atualizado_em"])
    return conta
