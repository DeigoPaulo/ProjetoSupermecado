import hashlib

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.auditoria.models import LogAuditoria
from apps.estoque.models import Estoque, TipoMovimentacaoEstoque, movimentar_estoque

from .models import (
    CotacaoCompra,
    EntradaCompra,
    ItemCotacaoCompra,
    ItemEntradaCompra,
    ItemPedidoCompra,
    PedidoCompra,
    PrecoRespostaCotacao,
    RespostaCotacaoFornecedor,
    StatusCotacaoCompra,
    StatusEntradaCompra,
    StatusConferenciaEntrada,
    StatusPedidoCompra,
)


def criar_cotacao_reposicao(
    *, filial, itens, usuario, data_inicio, data_fim, dias_cobertura, ip=None,
):
    if not itens:
        raise ValidationError("Selecione ao menos um item sugerido para a cotação.")
    if len(itens) > 500:
        raise ValidationError("A cotação de reposição aceita no máximo 500 itens por vez.")

    normalizados = []
    produtos_ids = set()
    for item in itens:
        produto = item.get("produto")
        quantidade = Decimal(str(item.get("quantidade") or "0")).quantize(Decimal("0.001"))
        if not produto or produto.pk in produtos_ids or quantidade <= 0:
            raise ValidationError("A seleção de reposição contém item inválido ou duplicado.")
        produtos_ids.add(produto.pk)
        normalizados.append((produto, quantidade))
    if Estoque.objects.filter(filial=filial, produto_id__in=produtos_ids).count() != len(produtos_ids):
        raise ValidationError("Um produto selecionado não pertence ao estoque da filial.")

    assinatura = "|".join(
        [str(filial.pk), str(usuario.pk), str(data_inicio), str(data_fim), str(dias_cobertura)]
        + [f"{produto.pk}:{quantidade}" for produto, quantidade in sorted(normalizados, key=lambda linha: linha[0].pk)]
    )
    chave_idempotencia = hashlib.sha256(assinatura.encode("utf-8")).hexdigest()
    referencia = f"REPOS-{data_fim:%Y%m%d}-{chave_idempotencia[:12]}"

    with transaction.atomic():
        cotacao, criada = CotacaoCompra.objects.get_or_create(
            chave_idempotencia=chave_idempotencia,
            defaults={
                "filial": filial,
                "usuario": usuario,
                "referencia": referencia,
                "observacoes": (
                    f"Rascunho gerado da sugestão de reposição de {data_inicio:%d/%m/%Y} a "
                    f"{data_fim:%d/%m/%Y}, cobertura de {dias_cobertura} dia(s). "
                    "Revise quantidades e fornecedores antes de abrir a cotação."
                ),
                "status": StatusCotacaoCompra.RASCUNHO,
            },
        )
        if not criada:
            return cotacao, False
        ItemCotacaoCompra.objects.bulk_create(
            [
                ItemCotacaoCompra(cotacao=cotacao, produto=produto, quantidade=quantidade)
                for produto, quantidade in normalizados
            ]
        )
        LogAuditoria.objects.create(
            usuario=usuario,
            modulo="compras",
            acao="CRIACAO_COTACAO_REPOSICAO",
            descricao=(
                f"Cotação de reposição {cotacao.id} criada em rascunho para {filial} "
                f"com {len(normalizados)} item(ns); nenhum pedido, estoque ou financeiro foi alterado."
            ),
            objeto_tipo="CotacaoCompra",
            objeto_id=str(cotacao.pk),
            ip=ip,
        )
        return cotacao, True


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
                raise ValidationError("Custo previsto não pode ser negativo.")
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
        raise ValidationError("Este pedido não pode ser cancelado.")

    with transaction.atomic():
        pedido = PedidoCompra.objects.select_for_update().get(pk=pedido.pk)
        if pedido.status not in {StatusPedidoCompra.RASCUNHO, StatusPedidoCompra.ENVIADO}:
            raise ValidationError("Este pedido não pode ser cancelado.")
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
            raise ValidationError("Pedido sem itens não pode gerar entrada.")

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
            conferencia_status=StatusConferenciaEntrada.PENDENTE,
            conferencia_resumo="Pedido vinculado. Aguarda a importação da NF-e para concluir a conferência em três vias.",
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


def avaliar_conferencia_entrada(entrada):
    """Compara pedido, itens recebidos e XML já associado ao rascunho."""
    if not entrada.pedido_origem_id:
        entrada.conferencia_status = StatusConferenciaEntrada.NAO_APLICAVEL
        entrada.conferencia_resumo = (
            "Sem pedido de compra vinculado; a entrada pode ser revisada normalmente, mas não possui terceira via para comparar."
        )
        return entrada

    if not entrada.chave_acesso_xml:
        entrada.conferencia_status = StatusConferenciaEntrada.PENDENTE
        entrada.conferencia_resumo = "Pedido vinculado. Aguarda a importação da NF-e para concluir a conferência em três vias."
        return entrada

    itens_pedido = list(entrada.pedido_origem.itens.select_related("produto"))
    itens_entrada = list(entrada.itens.select_related("produto"))
    previstos = {item.produto_id: (item.quantidade, item.total_previsto) for item in itens_pedido}
    recebidos = {}
    for item in itens_entrada:
        quantidade, total = recebidos.get(item.produto_id, (Decimal("0.000"), Decimal("0.00")))
        recebidos[item.produto_id] = (quantidade + item.quantidade, total + item.total)

    nomes = {item.produto_id: str(item.produto) for item in itens_pedido + itens_entrada}
    divergencias = []
    for produto_id in sorted(set(previstos) | set(recebidos)):
        previsto = previstos.get(produto_id)
        recebido = recebidos.get(produto_id)
        nome = nomes.get(produto_id, str(produto_id))
        if previsto is None:
            divergencias.append(f"{nome}: item não previsto no pedido")
            continue
        if recebido is None:
            divergencias.append(f"{nome}: item previsto não recebido")
            continue
        if previsto[0] != recebido[0]:
            divergencias.append(f"{nome}: quantidade prevista {previsto[0]} e recebida {recebido[0]}")
        if previsto[1] != recebido[1]:
            divergencias.append(f"{nome}: total previsto R$ {previsto[1]:.2f} e XML R$ {recebido[1]:.2f}")

    if divergencias:
        entrada.conferencia_status = StatusConferenciaEntrada.DIVERGENTE
        entrada.conferencia_resumo = "Divergências: " + "; ".join(divergencias[:8])
    else:
        entrada.conferencia_status = StatusConferenciaEntrada.CONFERIDA
        entrada.conferencia_resumo = "Pedido, recebimento e NF-e conferidos sem divergências."
    return entrada

def itens_conferencia_entrada(entrada):
    """Retorna o comparativo visual entre pedido e recebimento da entrada."""
    if not entrada.pedido_origem_id:
        return []
    previstos = {item.produto_id: item for item in entrada.pedido_origem.itens.select_related("produto")}
    recebidos = {}
    for item in entrada.itens.select_related("produto"):
        atual = recebidos.get(item.produto_id)
        if atual is None:
            recebidos[item.produto_id] = {"produto": item.produto, "quantidade": item.quantidade, "total": item.total}
        else:
            atual["quantidade"] += item.quantidade
            atual["total"] += item.total
    linhas = []
    for produto_id in sorted(set(previstos) | set(recebidos)):
        previsto = previstos.get(produto_id)
        recebido = recebidos.get(produto_id)
        produto = previsto.produto if previsto else recebido["produto"]
        quantidade_prevista = previsto.quantidade if previsto else Decimal("0.000")
        quantidade_recebida = recebido["quantidade"] if recebido else Decimal("0.000")
        total_previsto = previsto.total_previsto if previsto else Decimal("0.00")
        total_recebido = recebido["total"] if recebido else Decimal("0.00")
        linhas.append({
            "produto": produto,
            "quantidade_prevista": quantidade_prevista,
            "quantidade_recebida": quantidade_recebida,
            "total_previsto": total_previsto,
            "total_recebido": total_recebido,
            "divergente": quantidade_prevista != quantidade_recebida or total_previsto != total_recebido,
        })
    return linhas


def confirmar_conferencia_fisica(entrada, *, usuario, observacoes="", ip=None):
    with transaction.atomic():
        entrada = EntradaCompra.objects.select_for_update().select_related("pedido_origem").get(pk=entrada.pk)
        if entrada.status != StatusEntradaCompra.RASCUNHO:
            raise ValidationError("Somente entradas em rascunho podem ter a conferência física registrada.")
        if not entrada.pedido_origem_id:
            raise ValidationError("A conferência física guiada exige um pedido de compra vinculado.")
        observacoes = (observacoes or "").strip()
        if entrada.conferencia_status == StatusConferenciaEntrada.DIVERGENTE and not observacoes:
            raise ValidationError("Descreva a conferência física quando houver divergências.")
        entrada.conferencia_fisica_em = timezone.now()
        entrada.conferencia_fisica_por = usuario
        entrada.conferencia_fisica_observacoes = observacoes
        entrada.save(update_fields=["conferencia_fisica_em", "conferencia_fisica_por", "conferencia_fisica_observacoes", "updated_at"])
        LogAuditoria.objects.create(
            usuario=usuario,
            modulo="compras",
            acao="CONFERENCIA_FISICA_ENTRADA",
            descricao=(
                f"Conferência física registrada na entrada {entrada.id}. "
                f"Situação documental: {entrada.get_conferencia_status_display()}. "
                f"Observações: {observacoes or '-'}"
            ),
            objeto_tipo="EntradaCompra",
            objeto_id=str(entrada.id),
            ip=ip,
        )
        return entrada


def vincular_xml_a_pedido_manual(entrada, pedido, *, usuario, supervisor, justificativa, ip=None):
    """Vincula uma NF-e divergente ao pedido correto sem movimentar estoque."""
    justificativa = (justificativa or "").strip()
    if not justificativa:
        raise ValidationError("Informe a justificativa para o vínculo manual do XML.")

    with transaction.atomic():
        entrada = EntradaCompra.objects.select_for_update().select_related("fornecedor", "filial").get(pk=entrada.pk)
        pedido = PedidoCompra.objects.select_for_update().select_related("fornecedor", "filial").get(pk=pedido.pk)
        if entrada.status != StatusEntradaCompra.RASCUNHO:
            raise ValidationError("Somente entradas em rascunho podem receber vínculo manual de XML.")
        if not entrada.chave_acesso_xml:
            raise ValidationError("O vínculo manual é exclusivo para entradas importadas de XML.")
        if entrada.pedido_origem_id:
            raise ValidationError("Esta entrada já possui pedido de compra vinculado.")
        if pedido.status != StatusPedidoCompra.ENVIADO:
            raise ValidationError("Somente pedidos enviados ao fornecedor podem ser vinculados.")
        if EntradaCompra.objects.filter(pedido_origem=pedido).exists():
            raise ValidationError("Este pedido já possui uma entrada de compra vinculada.")
        if pedido.fornecedor_id != entrada.fornecedor_id or pedido.filial_id != entrada.filial_id:
            raise ValidationError("O pedido deve ter o mesmo fornecedor e a mesma filial da NF-e.")

        entrada.pedido_origem = pedido
        avaliar_conferencia_entrada(entrada)
        entrada.save(update_fields=["pedido_origem", "conferencia_status", "conferencia_resumo", "updated_at"])
        pedido.status = StatusPedidoCompra.CONVERTIDO
        pedido.save(update_fields=["status", "updated_at"])
        LogAuditoria.objects.create(
            usuario=usuario,
            modulo="compras",
            acao="VINCULO_MANUAL_XML_PEDIDO",
            descricao=(
                f"NF-e da entrada {entrada.id} vinculada manualmente ao pedido {pedido.id}. "
                f"Conferência: {entrada.get_conferencia_status_display()}. "
                f"Justificativa: {justificativa}. Autorizado por: {supervisor}."
            ),
            objeto_tipo="EntradaCompra",
            objeto_id=str(entrada.id),
            ip=ip,
        )
        return entrada

def finalizar_entrada_compra(entrada, *, supervisor=None, ip=None):
    entrada = EntradaCompra.objects.select_related("fornecedor", "filial__empresa").get(pk=entrada.pk)
    if entrada.fornecedor.empresa_id and entrada.fornecedor.empresa_id != entrada.filial.empresa_id:
        raise ValidationError("Fornecedor informado pertence a outra empresa.")
    if entrada.status != StatusEntradaCompra.RASCUNHO:
        raise ValidationError("Apenas entradas em rascunho podem ser finalizadas.")
    if (
        entrada.pedido_origem_id
        and entrada.conferencia_status == StatusConferenciaEntrada.DIVERGENTE
        and entrada.filial.empresa.bloquear_finalizacao_entrada_divergente
        and not entrada.conferencia_fisica_em
    ):
        raise ValidationError(
            "A entrada possui divergências. Registre a conferência física antes de finalizar ou ajuste a política da empresa."
        )

    itens = list(entrada.itens.select_related("produto"))
    if not itens:
        raise ValidationError("Inclua ao menos um item antes de finalizar a entrada.")

    with transaction.atomic():
        total_produtos = 0
        for item in itens:
            if item.quantidade <= 0:
                raise ValidationError("Quantidade deve ser maior que zero.")
            if item.custo_unitario < 0:
                raise ValidationError("Custo unitario não pode ser negativo.")

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
    entrada = EntradaCompra.objects.get(pk=entrada.pk)
    motivo = (motivo or "" ).strip()
    if not motivo:
        raise ValidationError("Informe o motivo do cancelamento.")
    if entrada.status != StatusEntradaCompra.FINALIZADA:
        raise ValidationError("Apenas entradas finalizadas podem ser canceladas.")

    itens = list(entrada.itens.select_related("produto"))
    if not itens:
        raise ValidationError("Entrada sem itens não pode ser cancelada.")

    with transaction.atomic():
        entrada = entrada.__class__.objects.select_for_update().get(pk=entrada.pk)
        if entrada.status != StatusEntradaCompra.FINALIZADA:
            raise ValidationError("Apenas entradas finalizadas podem ser canceladas.")
        from apps.fiscal.models import (
            RascunhoDevolucaoFornecedor,
            StatusRascunhoDevolucaoFornecedor,
        )

        if RascunhoDevolucaoFornecedor.objects.filter(
            entrada_compra=entrada,
            status__in=[
                StatusRascunhoDevolucaoFornecedor.RASCUNHO,
                StatusRascunhoDevolucaoFornecedor.AGUARDANDO_REVISAO,
            ],
        ).exists():
            raise ValidationError(
                "Cancele a preparação fiscal da devolução antes de cancelar a entrada."
            )

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
        empresa=entrada.filial.empresa,
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
