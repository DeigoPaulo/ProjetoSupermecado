from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone
import secrets
import unicodedata

from apps.auditoria.models import LogAuditoria
from apps.estoque.models import TipoMovimentacaoEstoque, movimentar_estoque

from .models import IntegracaoMarketplace, PedidoOnline, PoliticaEntrega, StatusPagamentoPedido, StatusPedido, TipoEntrega


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
    pedido = PedidoOnline.objects.select_for_update().get(pk=pedido.pk)
    if pedido.status != StatusPedido.RASCUNHO or pedido.estoque_reservado:
        raise ValidationError("Apenas pedidos em rascunho podem ser reservados.")
    itens = list(pedido.itens.select_related("produto"))
    if not itens:
        raise ValidationError("Inclua ao menos um item antes de iniciar a separação.")
    if pedido.tipo_entrega == TipoEntrega.ENTREGA and PoliticaEntrega.objects.filter(filial=pedido.filial, is_active=True).exists() and not pedido.regra_entrega_aplicada:
        raise ValidationError("Calcule a entrega antes de iniciar a separação.")
    for item in itens:
        movimentar_estoque(
            produto=item.produto,
            filial=pedido.filial,
            tipo=TipoMovimentacaoEstoque.RESERVA,
            quantidade=item.quantidade,
            usuario=usuario,
            motivo=f"Reserva para pedido online {pedido.pk}",
            referencia=f"pedido_online:{pedido.pk}",
        )
    pedido.estoque_reservado = True
    pedido.status = StatusPedido.EM_SEPARACAO
    pedido.save(update_fields=["estoque_reservado", "status", "atualizado_em"])
    _log(pedido, usuario, "RESERVA_PEDIDO", f"Estoque reservado para o pedido online {pedido.pk}.", ip)
    return pedido


@transaction.atomic
def alterar_status_pedido(*, pedido, destino, usuario, ip=None):
    pedido = PedidoOnline.objects.select_for_update().get(pk=pedido.pk)
    permitidos = {
        StatusPedido.EM_SEPARACAO: {StatusPedido.PRONTO},
        StatusPedido.PRONTO: {StatusPedido.SAIU_ENTREGA, StatusPedido.CONCLUIDO},
        StatusPedido.SAIU_ENTREGA: {StatusPedido.CONCLUIDO},
    }
    if destino not in permitidos.get(pedido.status, set()):
        raise ValidationError("Mudan?a de status não permitida para este pedido.")
    if destino == StatusPedido.PRONTO and pedido.itens.exclude(quantidade_separada=models.F("quantidade")).exists():
        raise ValidationError("Conclua a separação de todos os itens antes de marcar o pedido como pronto.")
    if destino == StatusPedido.CONCLUIDO and pedido.status_pagamento != StatusPagamentoPedido.PAGO:
        raise ValidationError("Registre o pagamento antes de concluir o pedido.")
    if destino == StatusPedido.CONCLUIDO:
        for item in pedido.itens.select_related("produto"):
            movimentar_estoque(produto=item.produto, filial=pedido.filial, tipo=TipoMovimentacaoEstoque.LIBERACAO_RESERVA, quantidade=item.quantidade, usuario=usuario, motivo=f"Conclusao do pedido online {pedido.pk}", referencia=f"pedido_online:{pedido.pk}")
            movimentar_estoque(produto=item.produto, filial=pedido.filial, tipo=TipoMovimentacaoEstoque.SAIDA, quantidade=item.quantidade, usuario=usuario, motivo=f"Saida do pedido online {pedido.pk}", referencia=f"pedido_online:{pedido.pk}")
        pedido.estoque_reservado = False
    pedido.status = destino
    pedido.save(update_fields=["status", "estoque_reservado", "atualizado_em"])
    _log(pedido, usuario, "STATUS_PEDIDO", f"Pedido online {pedido.pk} alterado para {pedido.get_status_display()}.", ip)
    return pedido


@transaction.atomic
def registrar_pagamento(*, pedido, forma_pagamento, valor_pago, referencia_pagamento="", usuario, ip=None):
    pedido = PedidoOnline.objects.select_for_update().get(pk=pedido.pk)
    referencia_pagamento = str(referencia_pagamento or "").strip()
    cartoes_na_entrega = {"CARTAO_CREDITO_ENTREGA", "CARTAO_DEBITO_ENTREGA"}
    if forma_pagamento in cartoes_na_entrega:
        if pedido.tipo_entrega != TipoEntrega.ENTREGA:
            raise ValidationError("Cartão pago na entrega é permitido somente para pedidos de entrega.")
        if pedido.status != StatusPedido.SAIU_ENTREGA:
            raise ValidationError("Confirme cart?o pago na entrega somente depois que o pedido sair para entrega.")
    if forma_pagamento in {"CARTAO", *cartoes_na_entrega} and not referencia_pagamento:
        raise ValidationError("Informe o NSU ou a referência da maquininha para confirmar o cart?o.")
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
def cancelar_pedido(*, pedido, usuario, ip=None):
    pedido = PedidoOnline.objects.select_for_update().get(pk=pedido.pk)
    if pedido.status in {StatusPedido.CONCLUIDO, StatusPedido.CANCELADO}:
        raise ValidationError("Este pedido não pode ser cancelado.")
    if pedido.estoque_reservado:
        for item in pedido.itens.select_related("produto"):
            movimentar_estoque(produto=item.produto, filial=pedido.filial, tipo=TipoMovimentacaoEstoque.LIBERACAO_RESERVA, quantidade=item.quantidade, usuario=usuario, motivo=f"Cancelamento do pedido online {pedido.pk}", referencia=f"pedido_online:{pedido.pk}")
    pedido.estoque_reservado = False
    pedido.status = StatusPedido.CANCELADO
    if pedido.status_pagamento == StatusPagamentoPedido.PAGO:
        pedido.status_pagamento = StatusPagamentoPedido.ESTORNADO
    pedido.save(update_fields=["estoque_reservado", "status", "status_pagamento", "atualizado_em"])
    _log(pedido, usuario, "CANCELAMENTO_PEDIDO", f"Pedido online {pedido.pk} cancelado e reserva liberada.", ip)
    return pedido
