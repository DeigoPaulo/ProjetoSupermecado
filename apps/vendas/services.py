from decimal import Decimal
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.auditoria.models import LogAuditoria
from apps.estoque.models import TipoMovimentacaoEstoque, movimentar_estoque
from apps.promocoes.services import preco_atual_produto

from .models import DevolucaoVenda, ItemDevolucaoVenda, ItemPreVenda, ItemVenda, PagamentoVenda, PreVenda, StatusPagamento, StatusPreVenda, StatusVenda, Venda


def calcular_item(produto, quantidade):
    preco = preco_atual_produto(produto)
    return preco * quantidade


def quantidade_devolvida_item(item_venda):
    return sum((item.quantidade for item in item_venda.itens_devolucao.all()), Decimal("0.000"))


FORMAS_PRAZO = {"CREDIARIO", "FIADO", "PRAZO"}
TIPO_CONTA_POR_FORMA = {
    "DINHEIRO": "CAIXA",
    "PIX": "PIX",
    "CARTAO": "BANCO",
    "DEBITO": "BANCO",
    "CREDITO": "BANCO",
    "VALE": "OUTRA",
    "CONVENIO": "OUTRA",
    "OUTRO": "OUTRA",
}
FORMAS_ELETRONICAS = {"PIX", "CARTAO", "DEBITO", "CREDITO"}


def finalizar_venda(*, caixa, usuario, itens, forma_pagamento=None, desconto=Decimal("0.00"), cliente=None, pagamentos=None, vencimento_financeiro=None):
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

        if not pagamentos and forma_pagamento:
            pagamentos = [{"forma_pagamento": forma_pagamento, "valor": total_liquido}]
        if not pagamentos:
            raise ValidationError("Informe ao menos uma forma de pagamento.")
        pagamentos_nao_confirmados = [
            item for item in pagamentos if item.get("status", StatusPagamento.CONFIRMADO) != StatusPagamento.CONFIRMADO
        ]
        if pagamentos_nao_confirmados:
            raise ValidationError("Todos os pagamentos devem estar confirmados antes de finalizar a venda.")
        total_pagamentos = sum((item["valor"] for item in pagamentos), Decimal("0.00"))
        if total_pagamentos != total_liquido:
            raise ValidationError("A soma dos pagamentos deve ser igual ao total da venda.")

        total_prazo = sum(
            (item["valor"] for item in pagamentos if item["forma_pagamento"].tipo in FORMAS_PRAZO),
            Decimal("0.00"),
        )
        if total_prazo > 0 and not cliente:
            raise ValidationError("Venda a prazo exige cliente identificado.")

        pagamentos_criados = []
        for pagamento in pagamentos:
            if pagamento["valor"] <= 0:
                continue
            pagamento = _normalizar_pagamento_eletronico(pagamento)
            pagamento_venda = PagamentoVenda.objects.create(
                venda=venda,
                forma_pagamento=pagamento["forma_pagamento"],
                valor=pagamento["valor"],
                status=pagamento.get("status", StatusPagamento.CONFIRMADO),
                transacao_externa_id=pagamento.get("transacao_externa_id", ""),
                nsu=pagamento.get("nsu", ""),
                codigo_autorizacao=pagamento.get("codigo_autorizacao", ""),
                mensagem_processadora=pagamento.get("mensagem_processadora", ""),
            )
            pagamentos_criados.append(pagamento_venda)
        _criar_conta_receber_venda(venda, total_prazo, vencimento_financeiro)
        _registrar_lancamentos_pdv_venda(venda, pagamentos_criados)

        return venda


def _normalizar_pagamento_eletronico(pagamento):
    forma = pagamento["forma_pagamento"]
    tipo_forma = (forma.tipo or "").upper()
    if tipo_forma not in FORMAS_ELETRONICAS:
        return pagamento
    if pagamento.get("status", StatusPagamento.CONFIRMADO) != StatusPagamento.CONFIRMADO:
        return pagamento
    if pagamento.get("transacao_externa_id") and pagamento.get("nsu") and pagamento.get("codigo_autorizacao"):
        return pagamento

    referencia = uuid4().hex.upper()
    pagamento = pagamento.copy()
    pagamento.setdefault("transacao_externa_id", f"TEF-SIM-{referencia[:16]}")
    pagamento.setdefault("nsu", referencia[16:28])
    pagamento.setdefault("codigo_autorizacao", referencia[28:34])
    pagamento.setdefault("mensagem_processadora", "Autorizacao eletronica simulada. Substituir pelo adaptador TEF/API no app desktop.")
    return pagamento


def _conta_movimento_para_pagamento(filial, forma_pagamento):
    from apps.financeiro.models import ContaMovimentoFinanceiro, TipoContaMovimento

    if forma_pagamento.conta_movimento_padrao_id and forma_pagamento.conta_movimento_padrao.filial_id == filial.id:
        return forma_pagamento.conta_movimento_padrao

    tipo_forma = (forma_pagamento.tipo or "").upper()
    tipo_conta = TIPO_CONTA_POR_FORMA.get(tipo_forma)
    if not tipo_conta:
        return None
    nome_tipo = {
        TipoContaMovimento.CAIXA: "Caixa PDV",
        TipoContaMovimento.PIX: "PIX PDV",
        TipoContaMovimento.BANCO: "Banco/cartao PDV",
        TipoContaMovimento.OUTRA: "Outros recebimentos PDV",
    }[tipo_conta]
    conta, _ = ContaMovimentoFinanceiro.objects.get_or_create(
        filial=filial,
        nome=nome_tipo,
        defaults={"tipo": tipo_conta, "saldo_inicial": Decimal("0.00"), "ativa": True},
    )
    if not conta.ativa:
        conta.ativa = True
        conta.save(update_fields=["ativa", "atualizado_em"])
    return conta


def _registrar_lancamentos_pdv_venda(venda, pagamentos):
    from apps.financeiro.models import LancamentoFinanceiro, TipoLancamentoFinanceiro
    from apps.financeiro.services import registrar_lancamento

    for pagamento in pagamentos:
        if pagamento.status != StatusPagamento.CONFIRMADO or pagamento.forma_pagamento.tipo in FORMAS_PRAZO:
            continue
        if LancamentoFinanceiro.objects.filter(pagamento_venda=pagamento).exists():
            continue
        conta_movimento = _conta_movimento_para_pagamento(venda.filial, pagamento.forma_pagamento)
        if not conta_movimento:
            continue
        registrar_lancamento(
            conta=conta_movimento,
            tipo=TipoLancamentoFinanceiro.ENTRADA,
            descricao=f"Recebimento PDV venda #{venda.id} - {pagamento.forma_pagamento.nome}",
            valor=pagamento.valor,
            data=timezone.localdate(),
            usuario=venda.usuario,
            origem="PDV_VENDA",
            pagamento_venda=pagamento,
        )


def _criar_conta_receber_venda(venda, valor, vencimento_financeiro=None):
    if valor <= 0:
        return None
    from apps.financeiro.models import CategoriaFinanceira, ContaFinanceira, TipoContaFinanceira

    categoria, _ = CategoriaFinanceira.objects.get_or_create(
        nome="Crediario de clientes",
        defaults={"tipo": TipoContaFinanceira.RECEBER},
    )
    conta, criada = ContaFinanceira.objects.get_or_create(
        venda=venda,
        tipo=TipoContaFinanceira.RECEBER,
        defaults={
            "descricao": f"Crediario venda {venda.id} - {venda.cliente}",
            "categoria": categoria,
            "filial": venda.filial,
            "cliente": venda.cliente,
            "valor": valor,
            "vencimento": vencimento_financeiro or timezone.localdate(),
            "usuario": venda.usuario,
        },
    )
    if not criada:
        conta.descricao = f"Crediario venda {venda.id} - {venda.cliente}"
        conta.categoria = categoria
        conta.filial = venda.filial
        conta.cliente = venda.cliente
        conta.valor = valor
        conta.vencimento = vencimento_financeiro or timezone.localdate()
        conta.save(update_fields=["descricao", "categoria", "filial", "cliente", "valor", "vencimento", "atualizado_em"])
    return conta


def criar_pre_venda(*, filial, usuario, itens, desconto=Decimal("0.00"), cliente=None, observacao="", validade=None):
    if not itens:
        raise ValidationError("Inclua ao menos um item na pre-venda.")

    with transaction.atomic():
        pre_venda = PreVenda.objects.create(
            filial=filial,
            cliente=cliente,
            usuario=usuario,
            desconto=desconto,
            observacao=observacao,
            validade=validade,
            status=StatusPreVenda.ABERTA,
        )

        total_bruto = Decimal("0.00")
        for item in itens:
            produto = item["produto"]
            quantidade = item["quantidade"]
            preco_unitario = preco_atual_produto(produto)
            total_item = preco_unitario * quantidade
            total_bruto += total_item
            ItemPreVenda.objects.create(
                pre_venda=pre_venda,
                produto=produto,
                quantidade=quantidade,
                preco_unitario=preco_unitario,
                desconto=Decimal("0.00"),
                total=total_item,
            )

        total_liquido = total_bruto - desconto
        if total_liquido < 0:
            raise ValidationError("Desconto nao pode ser maior que o total da pre-venda.")

        pre_venda.total_bruto = total_bruto
        pre_venda.total_liquido = total_liquido
        pre_venda.save(update_fields=["total_bruto", "total_liquido"])
    return pre_venda


@transaction.atomic
def registrar_devolucao_venda(*, venda, usuario, itens, motivo, supervisor=None, ip=None):
    venda = Venda.objects.select_for_update().get(pk=venda.pk)
    if venda.status != StatusVenda.FINALIZADA:
        raise ValidationError("Apenas vendas finalizadas podem receber devolucao.")
    if not motivo:
        raise ValidationError("Informe o motivo da devolucao.")

    itens_validos = []
    for item in itens:
        quantidade = item["quantidade"]
        if quantidade <= 0:
            continue
        item_venda = (
            ItemVenda.objects.select_for_update()
            .select_related("produto")
            .prefetch_related("itens_devolucao")
            .get(pk=item["item_venda"].pk, venda=venda)
        )
        quantidade_disponivel = item_venda.quantidade - quantidade_devolvida_item(item_venda)
        if quantidade > quantidade_disponivel:
            raise ValidationError(f"Quantidade de devolucao maior que o disponivel para {item_venda.produto}.")
        itens_validos.append((item_venda, quantidade))

    if not itens_validos:
        raise ValidationError("Informe ao menos um item para devolver.")

    devolucao = DevolucaoVenda.objects.create(venda=venda, usuario=usuario, motivo=motivo)
    valor_total = Decimal("0.00")

    for item_venda, quantidade in itens_validos:
        valor_item = item_venda.preco_unitario_venda * quantidade
        valor_total += valor_item
        ItemDevolucaoVenda.objects.create(
            devolucao=devolucao,
            item_venda=item_venda,
            produto=item_venda.produto,
            quantidade=quantidade,
            valor_unitario=item_venda.preco_unitario_venda,
            valor_total=valor_item,
        )
        movimentar_estoque(
            produto=item_venda.produto,
            filial=venda.filial,
            tipo=TipoMovimentacaoEstoque.DEVOLUCAO,
            quantidade=quantidade,
            usuario=usuario,
            motivo=f"Devolucao de venda: {motivo}",
            referencia=f"devolucao_venda:{devolucao.id}",
            custo_unitario=item_venda.custo_unitario_no_momento,
        )

    devolucao.valor_total = valor_total
    devolucao.save(update_fields=["valor_total"])

    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="vendas",
        acao="DEVOLUCAO_VENDA",
        descricao=f"Devolucao {devolucao.id} registrada para venda {venda.id}. Motivo: {motivo}. Autorizado por: {supervisor or '-'}.",
        objeto_tipo="DevolucaoVenda",
        objeto_id=str(devolucao.id),
        ip=ip,
    )
    return devolucao


@transaction.atomic
def converter_pre_venda(*, pre_venda, venda):
    pre_venda = PreVenda.objects.select_for_update().get(pk=pre_venda.pk)
    if pre_venda.status != StatusPreVenda.ABERTA:
        raise ValidationError("Apenas pre-vendas abertas podem ser convertidas.")
    pre_venda.status = StatusPreVenda.CONVERTIDA
    pre_venda.venda = venda
    pre_venda.convertida_em = timezone.now()
    pre_venda.save(update_fields=["status", "venda", "convertida_em", "atualizada_em"])
    return pre_venda


@transaction.atomic
def cancelar_pre_venda(*, pre_venda, usuario, motivo, supervisor=None, ip=None):
    pre_venda = PreVenda.objects.select_for_update().get(pk=pre_venda.pk)
    if pre_venda.status != StatusPreVenda.ABERTA:
        raise ValidationError("Apenas pre-vendas abertas podem ser canceladas.")
    if not motivo:
        raise ValidationError("Informe o motivo do cancelamento.")

    pre_venda.status = StatusPreVenda.CANCELADA
    pre_venda.observacao = f"{pre_venda.observacao}\nCancelada: {motivo}".strip()
    pre_venda.save(update_fields=["status", "observacao", "atualizada_em"])

    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="pdv",
        acao="CANCELAMENTO_PRE_VENDA",
        descricao=f"Pre-venda {pre_venda.id} cancelada. Motivo: {motivo}. Autorizado por: {supervisor or '-'}.",
        objeto_tipo="PreVenda",
        objeto_id=str(pre_venda.id),
        ip=ip,
    )
    return pre_venda


@transaction.atomic
def cancelar_venda(*, venda, usuario, motivo, supervisor=None, ip=None):
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
    _solicitar_estorno_pagamentos(venda, motivo=motivo)
    _cancelar_contas_receber_venda(venda, usuario=usuario, motivo=motivo, ip=ip)

    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="vendas",
        acao="CANCELAMENTO_VENDA",
        descricao=f"Venda {venda.id} cancelada. Motivo: {motivo}. Autorizado por: {supervisor or '-'}.",
        objeto_tipo="Venda",
        objeto_id=str(venda.id),
        ip=ip,
    )
    return venda


def _solicitar_estorno_pagamentos(venda, *, motivo):
    agora = timezone.now()
    for pagamento in venda.pagamentos.select_for_update().filter(status=StatusPagamento.CONFIRMADO):
        pagamento.motivo_estorno = motivo
        pagamento.estorno_solicitado_em = agora
        if pagamento.transacao_externa_id:
            pagamento.status = StatusPagamento.ESTORNO_PENDENTE
            pagamento.mensagem_processadora = "Aguardando confirmacao de estorno pela operadora."
            campos = ["status", "motivo_estorno", "estorno_solicitado_em", "mensagem_processadora"]
        else:
            pagamento.status = StatusPagamento.ESTORNADO
            pagamento.estornado_em = agora
            campos = ["status", "motivo_estorno", "estorno_solicitado_em", "estornado_em"]
        pagamento.save(update_fields=campos)
    _estornar_lancamentos_pagamentos_locais(venda, motivo=motivo)


def _estornar_lancamentos_pagamentos_locais(venda, *, motivo):
    from apps.financeiro.models import LancamentoFinanceiro
    from apps.financeiro.services import estornar_lancamento

    lancamentos = LancamentoFinanceiro.objects.select_related("pagamento_venda").filter(
        pagamento_venda__venda=venda,
        pagamento_venda__status=StatusPagamento.ESTORNADO,
        estorno_de__isnull=True,
    )
    for lancamento in lancamentos:
        if lancamento.estornos.exists():
            continue
        estornar_lancamento(
            lancamento=lancamento,
            usuario=venda.usuario,
            motivo=f"Cancelamento da venda {venda.id}: {motivo}",
            data=timezone.localdate(),
        )


def _cancelar_contas_receber_venda(venda, *, usuario, motivo, ip=None):
    from apps.financeiro.models import StatusContaFinanceira
    from apps.financeiro.services import cancelar_conta

    for conta in venda.contas_financeiras.filter(status=StatusContaFinanceira.ABERTA):
        cancelar_conta(conta=conta, usuario=usuario, motivo=f"Cancelamento da venda {venda.id}: {motivo}", ip=ip)
