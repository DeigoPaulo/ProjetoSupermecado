from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone
import secrets
import unicodedata
from decimal import Decimal
from uuid import uuid4

from apps.auditoria.models import LogAuditoria
from apps.estoque.models import TipoMovimentacaoEstoque, movimentar_estoque

from .models import (
    DevolucaoPedido, FormaPagamentoPedido, IntegracaoMarketplace, OrigemRecebimentoPedido, PagamentoPedido,
    PedidoOnline, PoliticaEntrega, StatusAcertoEntrega, StatusPagamentoPedido, StatusPedido, TipoEntrega,
)


def _log(pedido, usuario, acao, descricao, ip=None):
    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="marketplace",
        acao=acao,
        descricao=descricao,
        objeto_tipo="PedidoOnline",
        objeto_id=str(pedido.pk),
        ip=ip,
    )


def gerar_token_integracao(integracao):
    token = f"mk_{secrets.token_urlsafe(32)}"
    integracao.definir_token(token)
    integracao.save(update_fields=["token_prefixo", "token_hash"])
    return token


def _normalizar_texto(valor):
    texto = unicodedata.normalize("NFKD", str(valor or "").strip().lower())
    return "".join(caractere for caractere in texto if not unicodedata.combining(caractere))


def _lista_bairros(valor):
    return [bairro for bairro in (_normalizar_texto(parte) for parte in str(valor or "").replace("\n", ",").split(",")) if bairro]


def validar_bairro_entrega(*, politica, bairro=None):
    bairro_normalizado = _normalizar_texto(bairro)
    atendidos = _lista_bairros(politica.bairros_atendidos)
    bloqueados = _lista_bairros(politica.bairros_bloqueados)
    if bloqueados and bairro_normalizado in bloqueados:
        raise ValidationError("Bairro bloqueado para entrega nesta filial.")
    if atendidos and not bairro_normalizado:
        raise ValidationError("Informe o bairro para validar a área atendida pela filial.")
    if atendidos and bairro_normalizado not in atendidos:
        raise ValidationError("Bairro fora da área atendida pela filial.")


def calcular_taxa_entrega(*, politica, subtotal, distancia_km, bairro=None):
    validar_bairro_entrega(politica=politica, bairro=bairro)
    if subtotal < politica.valor_minimo_pedido:
        raise ValidationError(f"Pedido mínimo para entrega: R$ {politica.valor_minimo_pedido}.")
    if distancia_km > politica.raio_maximo_km:
        raise ValidationError(f"Endereço fora do raio máximo de {politica.raio_maximo_km} km.")
    if politica.frete_gratis_acima is not None and subtotal >= politica.frete_gratis_acima:
        return {
            "taxa": 0,
            "regra": f"Frete grátis acima de R$ {politica.frete_gratis_acima}",
            "faixa": None,
        }
    faixa = politica.faixas.filter(distancia_inicial_km__lte=distancia_km, distancia_final_km__gte=distancia_km).first()
    if not faixa:
        raise ValidationError("Nenhuma faixa de entrega atende a distância informada.")
    return {
        "taxa": faixa.taxa,
        "regra": f"Faixa de {faixa.distancia_inicial_km} a {faixa.distancia_final_km} km",
        "faixa": faixa,
    }


def calcular_entrega_pedido(*, pedido, distancia_km, bairro_entrega=""):
    if pedido.tipo_entrega != TipoEntrega.ENTREGA:
        pedido.distancia_entrega_km = None
        pedido.taxa_entrega = 0
        pedido.regra_entrega_aplicada = "Retirada na loja"
        pedido.recalcular()
        pedido.save(update_fields=["distancia_entrega_km", "taxa_entrega", "regra_entrega_aplicada", "atualizado_em"])
        return pedido
    politica = PoliticaEntrega.objects.filter(filial=pedido.filial, is_active=True).prefetch_related("faixas").first()
    if not politica:
        raise ValidationError("A filial não possui política de entrega ativa.")
    bairro_entrega = (bairro_entrega or pedido.bairro_entrega or "").strip()
    resultado = calcular_taxa_entrega(politica=politica, subtotal=pedido.subtotal, distancia_km=distancia_km, bairro=bairro_entrega)
    pedido.bairro_entrega = bairro_entrega
    pedido.distancia_entrega_km = distancia_km
    pedido.taxa_entrega = resultado["taxa"]
    pedido.regra_entrega_aplicada = resultado["regra"]
    pedido.recalcular()
    pedido.save(update_fields=["bairro_entrega", "distancia_entrega_km", "taxa_entrega", "regra_entrega_aplicada", "atualizado_em"])
    return pedido


@transaction.atomic
def reservar_pedido(*, pedido, usuario, ip=None):
    from apps.estoque.models import Estoque

    pedido = PedidoOnline.objects.select_for_update().get(pk=pedido.pk)
    if pedido.status != StatusPedido.RASCUNHO or pedido.estoque_reservado:
        raise ValidationError("Apenas pedidos em rascunho podem ser reservados.")
    itens = list(pedido.itens.select_related("produto"))
    if not itens:
        raise ValidationError("Inclua ao menos um item antes de iniciar a separação.")
    if pedido.tipo_entrega == TipoEntrega.ENTREGA and PoliticaEntrega.objects.filter(filial=pedido.filial, is_active=True).exists() and not pedido.regra_entrega_aplicada:
        raise ValidationError("Calcule a entrega antes de iniciar a separação.")
    for item in itens:
        estoque, _ = Estoque.objects.select_for_update().get_or_create(
            produto=item.produto, filial=pedido.filial
        )
        if item.custo_unitario_no_momento is None:
            item.custo_unitario_no_momento = estoque.custo_medio or item.produto.preco_custo
            item.save(update_fields=["custo_unitario_no_momento"])
        movimentar_estoque(
            produto=item.produto,
            filial=pedido.filial,
            tipo=TipoMovimentacaoEstoque.RESERVA,
            quantidade=item.quantidade,
            usuario=usuario,
            motivo=f"Reserva para pedido online {pedido.pk}",
            referencia=f"pedido_online:{pedido.pk}",
            custo_unitario=item.custo_unitario_no_momento,
        )
    pedido.estoque_reservado = True
    pedido.status = StatusPedido.EM_SEPARACAO
    pedido.save(update_fields=["estoque_reservado", "status", "atualizado_em"])
    _log(pedido, usuario, "RESERVA_PEDIDO", f"Estoque reservado para o pedido online {pedido.pk}.", ip)
    return pedido


def situacao_fiscal_saida(pedido, *, bloquear=False):
    from apps.fiscal.models import DocumentoFiscal, StatusDocumentoFiscal, TipoDocumentoFiscal

    documentos = DocumentoFiscal.objects.filter(
        pedido_online_id=pedido.pk,
        filial_id=pedido.filial_id,
        tipo_documento=TipoDocumentoFiscal.NFE,
    ).exclude(status=StatusDocumentoFiscal.CANCELADO)
    if bloquear:
        documentos = documentos.select_for_update()
    documento = documentos.order_by("-criado_em", "-pk").first()
    if documento and (
        documento.status == StatusDocumentoFiscal.EMITIDO
        and documento.chave_acesso
        and documento.protocolo
        and not documento.aguardando_consulta_sefaz
    ):
        return "AUTORIZADA"
    if documento and documento.status in {StatusDocumentoFiscal.REJEITADO, StatusDocumentoFiscal.DENEGADO}:
        return "ERRO"
    return "PENDENTE"


@transaction.atomic
def alterar_status_pedido(*, pedido, destino, usuario, ip=None):
    pedido = PedidoOnline.objects.select_for_update().get(pk=pedido.pk)
    permitidos = {
        StatusPedido.EM_SEPARACAO: {StatusPedido.PRONTO},
        StatusPedido.PRONTO: {StatusPedido.SAIU_ENTREGA, StatusPedido.CONCLUIDO},
        StatusPedido.SAIU_ENTREGA: {StatusPedido.CONCLUIDO},
    }
    if destino not in permitidos.get(pedido.status, set()):
        raise ValidationError("Mudança de status não permitida para este pedido.")
    if (pedido.tipo_entrega == TipoEntrega.ENTREGA and pedido.status == StatusPedido.PRONTO
            and destino == StatusPedido.CONCLUIDO):
        raise ValidationError("Pedidos de entrega precisam ser despachados antes da conclusão.")
    if destino == StatusPedido.PRONTO and pedido.itens.exclude(quantidade_separada=models.F("quantidade")).exists():
        raise ValidationError("Conclua a separação de todos os itens antes de marcar o pedido como pronto.")
    if destino == StatusPedido.CONCLUIDO and pedido.status_pagamento != StatusPagamentoPedido.PAGO:
        raise ValidationError("Registre o pagamento antes de concluir o pedido.")
    if destino == StatusPedido.SAIU_ENTREGA and not pedido.estoque_reservado:
        raise ValidationError("O pedido precisa ter estoque reservado antes de sair para entrega.")
    if destino == StatusPedido.SAIU_ENTREGA:
        if pedido.status_pagamento != StatusPagamentoPedido.PAGO:
            raise ValidationError("Pagamento posterior ainda não possui configuração fiscal homologada. Não é possível liberar a entrega.")
        if situacao_fiscal_saida(pedido, bloquear=True) != "AUTORIZADA":
            raise ValidationError("Não é possível liberar a entrega. A NF-e ainda não foi autorizada.")
    if destino == StatusPedido.SAIU_ENTREGA or (
        destino == StatusPedido.CONCLUIDO and pedido.tipo_entrega == TipoEntrega.RETIRADA
        and pedido.estoque_reservado
    ):
        for item in pedido.itens.select_related("produto"):
            movimentar_estoque(produto=item.produto, filial=pedido.filial, tipo=TipoMovimentacaoEstoque.LIBERACAO_RESERVA, quantidade=item.quantidade, usuario=usuario, motivo=f"Baixa do pedido online {pedido.pk}", referencia=f"pedido_online:{pedido.pk}")
            movimentar_estoque(produto=item.produto, filial=pedido.filial, tipo=TipoMovimentacaoEstoque.SAIDA, quantidade=item.quantidade, usuario=usuario, motivo=f"Saida do pedido online {pedido.pk}", referencia=f"pedido_online:{pedido.pk}", custo_unitario=item.custo_unitario_no_momento)
        pedido.estoque_reservado = False
    if destino == StatusPedido.CONCLUIDO:
        if pedido.concluido_em is None:
            pedido.concluido_em = timezone.now()
    pedido.status = destino
    pedido.save(update_fields=["status", "estoque_reservado", "concluido_em", "atualizado_em"])
    _log(pedido, usuario, "STATUS_PEDIDO", f"Pedido online {pedido.pk} alterado para {pedido.get_status_display()}.", ip)
    return pedido


def _resumir_pagamentos_pedido(pedido):
    parcelas = list(pedido.pagamentos.filter(status="CONFIRMADO").select_related("forma_pagamento"))
    total = sum((parcela.valor for parcela in parcelas), Decimal("0.00"))
    tipos = {parcela.forma_pagamento.tipo.upper() for parcela in parcelas}
    pedido.valor_pago = total
    pedido.status_pagamento = (
        StatusPagamentoPedido.PAGO if total >= pedido.total else StatusPagamentoPedido.PENDENTE
    )
    pedido.forma_pagamento = {
        "PIX": FormaPagamentoPedido.PIX,
        "DINHEIRO": FormaPagamentoPedido.DINHEIRO,
        "CARTAO": FormaPagamentoPedido.CARTAO,
        "CREDITO": FormaPagamentoPedido.CARTAO,
        "DEBITO": FormaPagamentoPedido.CARTAO,
    }.get(next(iter(tipos)), FormaPagamentoPedido.OUTRO) if len(tipos) == 1 else FormaPagamentoPedido.OUTRO
    pedido.referencia_pagamento = " | ".join(
        parcela.nsu or parcela.transacao_externa_id
        for parcela in parcelas if parcela.nsu or parcela.transacao_externa_id
    )[:120]
    pedido.pago_em = (pedido.pago_em or timezone.now()) if pedido.status_pagamento == StatusPagamentoPedido.PAGO else None
    pedido.save(update_fields=[
        "valor_pago", "status_pagamento", "forma_pagamento", "referencia_pagamento", "pago_em", "atualizado_em"
    ])


@transaction.atomic
def registrar_parcelas_pedido(*, pedido, parcelas, origem_recebimento, usuario, caixa=None, ip=None):
    from apps.pdv.models import Caixa, StatusCaixa
    from apps.vendas.integracao_pagamentos import resolver_confirmacao_pagamento
    from apps.vendas.models import StatusPagamento
    from apps.vendas.services import FORMAS_ELETRONICAS, forma_pagamento_disponivel
    from apps.financeiro.services_recebiveis import registrar_reflexo_pagamento_pedido

    pedido = PedidoOnline.objects.select_for_update().get(pk=pedido.pk)
    if pedido.status in {StatusPedido.CONCLUIDO, StatusPedido.CANCELADO}:
        raise ValidationError("O pagamento deste pedido não pode mais ser alterado.")
    if pedido.status_pagamento == StatusPagamentoPedido.PAGO and not pedido.pagamentos.exists():
        raise ValidationError("Pedido legado já pago não pode receber parcelas adicionais.")
    if origem_recebimento not in OrigemRecebimentoPedido.values:
        raise ValidationError("Origem do recebimento inválida.")
    if origem_recebimento == OrigemRecebimentoPedido.CAIXA_PDV:
        if not caixa:
            raise ValidationError("Pagamento no PDV exige caixa aberto.")
        caixa = Caixa.objects.select_for_update().get(pk=caixa.pk)
        if caixa.status != StatusCaixa.ABERTO or caixa.filial_id != pedido.filial_id:
            raise ValidationError("O caixa informado não está aberto para esta filial.")
    elif caixa is not None:
        raise ValidationError("Pagamento recebido na entrega não pertence a um caixa PDV.")

    if not parcelas:
        raise ValidationError("Informe ao menos uma parcela.")
    criadas = []
    houve_criacao = False
    for dados in parcelas:
        forma = dados["forma_pagamento"]
        if not forma_pagamento_disponivel(pedido.filial, forma.pk):
            raise ValidationError("Forma de pagamento indisponível para a filial do pedido.")
        chave = str(dados.get("idempotency_key") or uuid4().hex)
        existente = PagamentoPedido.objects.filter(idempotency_key=chave).first()
        if existente:
            if (
                existente.pedido_id != pedido.pk
                or existente.forma_pagamento_id != forma.pk
                or existente.valor_informado != Decimal(str(dados["valor_informado"] if dados.get("valor_informado") is not None else dados["valor"]))
                or existente.origem_recebimento != origem_recebimento
                or existente.caixa_recebimento_id != (caixa.pk if caixa else None)
            ):
                raise ValidationError("Chave de pagamento reutilizada com dados diferentes.")
            criadas.append(existente)
            continue
        restante = pedido.total - sum(
            (item.valor for item in pedido.pagamentos.filter(status=StatusPagamento.CONFIRMADO)), Decimal("0.00")
        )
        if restante <= 0:
            raise ValidationError("O pedido já está integralmente pago.")
        informado = Decimal(str(dados.get("valor_informado") if dados.get("valor_informado") is not None else dados["valor"]))
        if informado <= 0:
            raise ValidationError("O valor da parcela deve ser maior que zero.")
        if informado > restante and not forma.permite_troco:
            raise ValidationError("Esta forma de pagamento não permite troco.")
        aplicado = min(informado, restante)
        tipo = (forma.tipo or "").upper()
        if tipo not in FORMAS_ELETRONICAS | {"DINHEIRO"}:
            raise ValidationError("Esta forma não é suportada para recebimento de pedido na entrega.")
        if tipo in FORMAS_ELETRONICAS and (
            dados.get("status") != StatusPagamento.CONFIRMADO
            or not all(dados.get(campo) for campo in ("transacao_externa_id", "nsu", "codigo_autorizacao"))
        ):
            raise ValidationError("Pagamento eletrônico exige confirmação, transação, NSU e autorização.")
        pagamento = dict(dados, valor=aplicado, valor_informado=informado)
        if origem_recebimento == OrigemRecebimentoPedido.CAIXA_PDV:
            pagamento = resolver_confirmacao_pagamento(pagamento, caixa=caixa)
        elif pagamento.get("confirmacao_integracao_id") or pagamento.get("tipo_integracao") == "1":
            raise ValidationError("Pagamento integrado na entrega exige confirmação confiável no servidor.")
        acerto = (
            StatusAcertoEntrega.PENDENTE
            if origem_recebimento == OrigemRecebimentoPedido.ENTREGA and tipo == "DINHEIRO"
            else StatusAcertoEntrega.NAO_APLICA
        )
        parcela = PagamentoPedido(
            pedido=pedido, forma_pagamento=forma, valor=aplicado, valor_informado=informado,
            status=StatusPagamento.CONFIRMADO, origem_recebimento=origem_recebimento,
            caixa_recebimento=caixa, usuario_recebimento=usuario, status_acerto=acerto,
            idempotency_key=chave, confirmacao_integracao=pagamento.get("confirmacao_integracao"),
            **{campo: pagamento.get(campo, "") for campo in (
                "transacao_externa_id", "nsu", "codigo_autorizacao", "tipo_integracao",
                "cnpj_instituicao_pagamento", "bandeira_cartao", "cnpj_beneficiario_pagamento",
                "identificador_terminal_pagamento", "mensagem_processadora",
            )},
        )
        parcela.full_clean()
        parcela.save()
        registrar_reflexo_pagamento_pedido(parcela)
        criadas.append(parcela)
        houve_criacao = True
    if houve_criacao:
        _resumir_pagamentos_pedido(pedido)
        _log(pedido, usuario, "PAGAMENTO_PEDIDO", f"{len(criadas)} parcela(s) registrada(s) no pedido {pedido.pk}.", ip)
    return pedido, criadas


@transaction.atomic
def acertar_dinheiro_entrega(*, pagamento, caixa, usuario, ip=None):
    from apps.pdv.models import Caixa, StatusCaixa
    from apps.financeiro.services_recebiveis import registrar_reflexo_pagamento_pedido

    pagamento = PagamentoPedido.objects.select_for_update().select_related("pedido").get(pk=pagamento.pk)
    caixa = Caixa.objects.select_for_update().get(pk=caixa.pk)
    if pagamento.status_acerto == StatusAcertoEntrega.ACERTADO:
        if pagamento.caixa_acerto_id == caixa.pk:
            return pagamento
        raise ValidationError("O dinheiro já foi acertado em outro caixa.")
    if pagamento.status_acerto != StatusAcertoEntrega.PENDENTE:
        raise ValidationError("Este pagamento não possui acerto pendente.")
    if caixa.status != StatusCaixa.ABERTO or caixa.filial_id != pagamento.pedido.filial_id:
        raise ValidationError("Selecione um caixa aberto da filial do pedido.")
    pagamento.caixa_acerto = caixa
    pagamento.usuario_acerto = usuario
    pagamento.acertado_em = timezone.now()
    pagamento.status_acerto = StatusAcertoEntrega.ACERTADO
    pagamento.full_clean()
    pagamento.save(update_fields=["caixa_acerto", "usuario_acerto", "acertado_em", "status_acerto"])
    registrar_reflexo_pagamento_pedido(pagamento, acerto=True)
    _log(pagamento.pedido, usuario, "ACERTO_ENTREGA", f"Acerto de entrega #{pagamento.pedido_id} no caixa {caixa.pk}.", ip)
    return pagamento


@transaction.atomic
def registrar_pagamento(*, pedido, forma_pagamento, valor_pago, referencia_pagamento="", usuario, ip=None):
    pedido = PedidoOnline.objects.select_for_update().get(pk=pedido.pk)
    referencia_pagamento = str(referencia_pagamento or "").strip()
    cartoes_na_entrega = {"CARTAO_CREDITO_ENTREGA", "CARTAO_DEBITO_ENTREGA"}
    if forma_pagamento in cartoes_na_entrega:
        if pedido.tipo_entrega != TipoEntrega.ENTREGA:
            raise ValidationError("Cartão pago na entrega é permitido somente para pedidos de entrega.")
        if pedido.status != StatusPedido.SAIU_ENTREGA:
            raise ValidationError("Confirme cartão pago na entrega somente depois que o pedido sair para entrega.")
    if forma_pagamento in {"CARTAO", *cartoes_na_entrega} and not referencia_pagamento:
        raise ValidationError("Informe o NSU ou a referência da maquininha para confirmar o cartão.")
    if pedido.status in {StatusPedido.CONCLUIDO, StatusPedido.CANCELADO}:
        raise ValidationError("O pagamento deste pedido não pode mais ser alterado.")
    if valor_pago < pedido.total:
        raise ValidationError("O valor pago não pode ser menor que o total do pedido.")
    pedido.forma_pagamento = forma_pagamento
    pedido.valor_pago = valor_pago
    pedido.referencia_pagamento = referencia_pagamento
    pedido.status_pagamento = StatusPagamentoPedido.PAGO
    pedido.pago_em = timezone.now()
    pedido.save(update_fields=["forma_pagamento", "valor_pago", "referencia_pagamento", "status_pagamento", "pago_em", "atualizado_em"])
    referencia_log = f" Ref.: {referencia_pagamento}." if referencia_pagamento else ""
    _log(pedido, usuario, "PAGAMENTO_PEDIDO", f"Pagamento do pedido online {pedido.pk} registrado: {pedido.get_forma_pagamento_display()} - R$ {valor_pago}.{referencia_log}", ip)
    return pedido


@transaction.atomic
def cancelar_pedido(*, pedido, usuario, motivo, ip=None):
    pedido = PedidoOnline.objects.select_for_update().get(pk=pedido.pk)
    motivo = str(motivo or "").strip()
    if not motivo:
        raise ValidationError("Informe o motivo do cancelamento da entrega.")
    if len(motivo) > 255:
        raise ValidationError("O motivo do cancelamento deve ter no máximo 255 caracteres.")
    if pedido.status in {StatusPedido.CONCLUIDO, StatusPedido.CANCELADO}:
        raise ValidationError("Este pedido não pode ser cancelado.")
    if pedido.status == StatusPedido.SAIU_ENTREGA:
        raise ValidationError("Pedido já saiu para entrega. Registre o retorno físico antes de tratar o cancelamento.")
    if pedido.status_pagamento == StatusPagamentoPedido.PAGO or pedido.pagamentos.exists():
        raise ValidationError("Pedido com pagamento confirmado exige fluxo de estorno financeiro antes do cancelamento.")
    if pedido.estoque_reservado:
        for item in pedido.itens.select_related("produto"):
            movimentar_estoque(produto=item.produto, filial=pedido.filial, tipo=TipoMovimentacaoEstoque.LIBERACAO_RESERVA, quantidade=item.quantidade, usuario=usuario, motivo=f"Cancelamento do pedido online {pedido.pk}: {motivo}"[:255], referencia=f"pedido_online:{pedido.pk}")
    pedido.estoque_reservado = False
    pedido.status = StatusPedido.CANCELADO
    pedido.save(update_fields=["estoque_reservado", "status", "atualizado_em"])
    _log(pedido, usuario, "CANCELAMENTO_PEDIDO", f"Pedido online {pedido.pk} cancelado por {usuario}. Motivo: {motivo}. Reserva liberada.", ip)
    return pedido


@transaction.atomic
def registrar_retorno_recusado(*, pedido, usuario, motivo, produto_apto_venda, valor_devolvido_confirmado, ip=None):
    from apps.estoque.models import MovimentacaoEstoque
    from apps.financeiro.models import LancamentoFinanceiro
    from apps.financeiro.services import estornar_lancamento
    from apps.fiscal.models import DocumentoFiscal
    from apps.vendas.models import StatusPagamento

    pedido = PedidoOnline.objects.select_for_update().get(pk=pedido.pk)
    motivo = str(motivo or "").strip()
    if not motivo or len(motivo) > 255:
        raise ValidationError("Informe o motivo da recusa com no máximo 255 caracteres.")
    if pedido.tipo_entrega != TipoEntrega.ENTREGA or pedido.status not in {StatusPedido.SAIU_ENTREGA, StatusPedido.CONCLUIDO}:
        raise ValidationError("Somente entrega que saiu para transporte pode ter retorno por recusa.")
    if DevolucaoPedido.objects.filter(pedido=pedido).exists():
        raise ValidationError("O retorno deste pedido já foi registrado.")
    if not produto_apto_venda or not valor_devolvido_confirmado:
        raise ValidationError("Confirme o retorno físico apto para venda e a devolução integral do pagamento.")
    if DocumentoFiscal.objects.filter(pedido_online=pedido).exclude(status="CANCELADO").exists():
        raise ValidationError("Pedido com documento fiscal exige tratamento fiscal antes do retorno.")
    parcelas = list(PagamentoPedido.objects.select_for_update().select_related("forma_pagamento").filter(pedido=pedido))
    if (pedido.status_pagamento != StatusPagamentoPedido.PAGO or len(parcelas) != 1
            or parcelas[0].status != StatusPagamento.CONFIRMADO
            or parcelas[0].forma_pagamento.tipo != "DINHEIRO"
            or parcelas[0].status_acerto != StatusAcertoEntrega.ACERTADO
            or parcelas[0].valor != pedido.total):
        raise ValidationError("Retorno automático exige pagamento integral em dinheiro já acertado; outros pagamentos exigem tratamento específico.")
    parcela = parcelas[0]
    lancamentos = list(LancamentoFinanceiro.objects.select_for_update().filter(pagamento_pedido=parcela, estorno_de__isnull=True))
    if len(lancamentos) != 1 or lancamentos[0].estornos.exists():
        raise ValidationError("O lançamento financeiro do pedido não está íntegro para estorno.")
    itens = list(pedido.itens.select_related("produto"))
    if not itens or any(
        MovimentacaoEstoque.objects.filter(
            filial=pedido.filial, produto=item.produto, tipo=TipoMovimentacaoEstoque.SAIDA,
            referencia=f"pedido_online:{pedido.pk}", quantidade=item.quantidade,
        ).count() != 1 for item in itens
    ):
        raise ValidationError("Não foi encontrada uma saída de estoque íntegra para todos os itens.")

    devolucao = DevolucaoPedido.objects.create(
        pedido=pedido, usuario=usuario, motivo=motivo,
        valor_devolvido=pedido.total, produto_apto_venda=True,
    )
    for item in itens:
        movimentar_estoque(
            produto=item.produto, filial=pedido.filial, tipo=TipoMovimentacaoEstoque.DEVOLUCAO,
            quantidade=item.quantidade, usuario=usuario,
            motivo=f"Retorno recusado do pedido {pedido.pk}: {motivo}"[:255],
            referencia=f"devolucao_pedido:{pedido.pk}",
            custo_unitario=item.custo_unitario_no_momento,
        )
    estornar_lancamento(lancamento=lancamentos[0], usuario=usuario, motivo=motivo, ip=ip)
    parcela.status = StatusPagamento.ESTORNADO
    parcela.save(update_fields=["status"])
    pedido.status_pagamento = StatusPagamentoPedido.ESTORNADO
    pedido.valor_pago = Decimal("0.00")
    pedido.save(update_fields=["status_pagamento", "valor_pago", "atualizado_em"])
    _log(pedido, usuario, "RETORNO_RECUSADO", f"Pedido {pedido.pk}: retorno físico e estorno de R$ {devolucao.valor_devolvido}. Motivo: {motivo}.", ip)
    return devolucao
