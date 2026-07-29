from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.auditoria.models import LogAuditoria
from apps.estoque.models import TipoMovimentacaoEstoque, movimentar_estoque
from apps.promocoes.services import preco_atual_produto

from .models import DevolucaoVenda, EstornoParcialPagamento, FormaPagamento, FormaPagamentoFilial, ItemDevolucaoVenda, ItemPreVenda, ItemVenda, PagamentoVenda, PreVenda, StatusEstornoParcial, StatusPagamento, StatusPreVenda, StatusVenda, TipoDocumentoConsumidor, Venda


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
    "VALE_ALIMENTACAO": "OUTRA",
    "VALE_REFEICAO": "OUTRA",
    "VALE": "OUTRA",
    "CONVENIO": "OUTRA",
    "OUTRO": "OUTRA",
}
FORMAS_ELETRONICAS = {
    "PIX",
    "CARTAO",
    "DEBITO",
    "CREDITO",
    "VALE_ALIMENTACAO",
    "VALE_REFEICAO",
}


def inicializar_formas_pagamento_filial(filial):
    formas_ids = FormaPagamento.objects.values_list("id", flat=True)
    existentes = set(
        FormaPagamentoFilial.objects.filter(filial=filial).values_list("forma_pagamento_id", flat=True)
    )
    FormaPagamentoFilial.objects.bulk_create(
        [
            FormaPagamentoFilial(filial=filial, forma_pagamento_id=forma_id, ativo=True)
            for forma_id in formas_ids
            if forma_id not in existentes
        ],
        ignore_conflicts=True,
    )


def formas_pagamento_disponiveis(filial):
    if not filial:
        return FormaPagamento.objects.none()
    inicializar_formas_pagamento_filial(filial)
    return FormaPagamento.objects.filter(
        ativo=True,
        configuracoes_filial__filial=filial,
        configuracoes_filial__ativo=True,
    ).distinct()

def forma_pagamento_disponivel(filial, forma_pagamento_id):
    return formas_pagamento_disponiveis(filial).filter(pk=forma_pagamento_id).first()

def finalizar_venda(*, caixa, usuario, itens, forma_pagamento=None, desconto=Decimal("0.00"), cliente=None, pagamentos=None, vencimento_financeiro=None, preparar_fiscal=True, documento_consumidor_tipo=TipoDocumentoConsumidor.NAO_IDENTIFICADO, documento_consumidor=""):
    if not itens:
        raise ValidationError("Inclua ao menos um item na venda.")
    if cliente and cliente.empresa_id != caixa.filial.empresa_id:
        raise ValidationError("Cliente informado pertence a outra empresa.")
    formas_informadas = [
        item.get("forma_pagamento") for item in (pagamentos or []) if item.get("forma_pagamento")
    ]
    if forma_pagamento:
        formas_informadas.append(forma_pagamento)
    formas_permitidas = set(formas_pagamento_disponiveis(caixa.filial).values_list("id", flat=True))
    if any(forma.id not in formas_permitidas for forma in formas_informadas):
        raise ValidationError("Forma de pagamento nao habilitada para esta filial.")
    documento_consumidor_tipo, documento_consumidor, observacao_fiscal_consumidor = _normalizar_documento_consumidor(
        documento_consumidor_tipo,
        documento_consumidor,
        preparar_fiscal=preparar_fiscal,
    )

    with transaction.atomic():
        venda = Venda.objects.create(
            filial=caixa.filial,
            caixa=caixa,
            cliente=cliente,
            documento_consumidor_tipo=documento_consumidor_tipo,
            documento_consumidor=documento_consumidor,
            observacao_fiscal_consumidor=observacao_fiscal_consumidor,
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
        if preparar_fiscal:
            _preparar_documento_fiscal_pos_venda(venda)

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


def _somente_digitos(valor):
    return "".join(caractere for caractere in str(valor or "") if caractere.isdigit())


def _normalizar_documento_consumidor(tipo, documento, *, preparar_fiscal):
    tipo = (tipo or TipoDocumentoConsumidor.NAO_IDENTIFICADO).upper()
    documento = str(documento or "").strip()
    if not documento:
        return TipoDocumentoConsumidor.NAO_IDENTIFICADO, "", ""
    if tipo not in {TipoDocumentoConsumidor.CPF, TipoDocumentoConsumidor.CNPJ, TipoDocumentoConsumidor.ESTRANGEIRO}:
        tipo = TipoDocumentoConsumidor.CPF if len(_somente_digitos(documento)) <= 11 else TipoDocumentoConsumidor.CNPJ
    if tipo in {TipoDocumentoConsumidor.CPF, TipoDocumentoConsumidor.CNPJ}:
        documento = _somente_digitos(documento)
    if tipo == TipoDocumentoConsumidor.CPF and len(documento) != 11:
        raise ValidationError("CPF na nota deve conter 11 digitos.")
    if tipo == TipoDocumentoConsumidor.CNPJ and len(documento) != 14:
        raise ValidationError("CNPJ na nota deve conter 14 digitos.")
    if tipo == TipoDocumentoConsumidor.CNPJ and preparar_fiscal:
        raise ValidationError("Para consumidor identificado por CNPJ, use o fluxo de NF-e modelo 55 em vez de NFC-e automatica.")
    if tipo == TipoDocumentoConsumidor.ESTRANGEIRO and len(documento) > 20:
        raise ValidationError("Documento estrangeiro deve ter no maximo 20 caracteres.")
    observacao = ""
    if tipo == TipoDocumentoConsumidor.CNPJ:
        observacao = "Consumidor solicitou CNPJ na nota; emissao fiscal deve seguir NF-e modelo 55."
    return tipo, documento, observacao


def _conta_movimento_para_pagamento(filial, forma_pagamento):
    from apps.financeiro.models import ContaMovimentoFinanceiro, TipoContaMovimento

    configuracao = (
        FormaPagamentoFilial.objects.select_related("conta_movimento_padrao")
        .filter(filial=filial, forma_pagamento=forma_pagamento, ativo=True)
        .first()
    )
    if configuracao and configuracao.conta_movimento_padrao_id:
        return configuracao.conta_movimento_padrao
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


def _preparar_documento_fiscal_pos_venda(venda):
    from apps.fiscal.services import tentar_preparar_documento_pos_venda

    tentar_preparar_documento_pos_venda(venda, venda.usuario)


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
    if cliente and cliente.empresa_id != filial.empresa_id:
        raise ValidationError("Cliente informado pertence a outra empresa.")

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
    _ratear_estorno_financeiro_devolucao(devolucao, usuario=usuario, motivo=motivo)

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


def _quantizar_moeda(valor):
    return Decimal(valor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _ratear_estorno_financeiro_devolucao(devolucao, *, usuario, motivo):
    from apps.financeiro.models import LancamentoFinanceiro, TipoLancamentoFinanceiro

    valor_devolver = _quantizar_moeda(devolucao.valor_total)
    if valor_devolver <= 0:
        return
    pagamentos = list(
        PagamentoVenda.objects.select_related("forma_pagamento")
        .filter(venda=devolucao.venda, status=StatusPagamento.CONFIRMADO)
        .order_by("id")
    )
    total_pagamentos = _quantizar_moeda(sum((pagamento.valor for pagamento in pagamentos), Decimal("0.00")))
    if total_pagamentos <= 0:
        return
    restante_rateio = valor_devolver
    for indice, pagamento in enumerate(pagamentos):
        lancamento = (
            LancamentoFinanceiro.objects.filter(
                pagamento_venda=pagamento,
                origem="PDV_VENDA",
                tipo=TipoLancamentoFinanceiro.ENTRADA,
                estorno_de__isnull=True,
            )
            .order_by("id")
            .first()
        )
        if not lancamento:
            continue
        valor_proporcional = restante_rateio if indice == len(pagamentos) - 1 else _quantizar_moeda(valor_devolver * pagamento.valor / total_pagamentos)
        if valor_proporcional <= 0:
            continue
        valor_estornado = _total_estornado_lancamento(lancamento)
        if pagamento.transacao_externa_id:
            valor_parcial_comprometido = sum(
                (
                    estorno.valor
                    for estorno in pagamento.estornos_parciais.exclude(status=StatusEstornoParcial.RECUSADO)
                ),
                Decimal("0.00"),
            )
            valor_estornado = max(valor_estornado, _quantizar_moeda(valor_parcial_comprometido))
        saldo_lancamento = _quantizar_moeda(lancamento.valor - valor_estornado)
        valor_estornar = min(valor_proporcional, saldo_lancamento, restante_rateio)
        if valor_estornar <= 0:
            continue
        if pagamento.transacao_externa_id:
            EstornoParcialPagamento.objects.create(
                pagamento=pagamento,
                devolucao=devolucao,
                valor=valor_estornar,
                motivo=motivo,
            )
        else:
            _registrar_estorno_lancamento_parcial(
                lancamento=lancamento,
                valor=valor_estornar,
                usuario=usuario,
                motivo=f"Devolucao {devolucao.id}: {motivo}",
            )
        restante_rateio = _quantizar_moeda(restante_rateio - valor_estornar)
        if restante_rateio <= 0:
            break


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
    if venda.devolucoes.exists():
        raise ValidationError(
            "Venda com devolução parcial não pode ser cancelada integralmente; devolva somente os itens restantes."
        )

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


@transaction.atomic
def confirmar_estorno_pagamento_eletronico(*, pagamento, usuario, motivo="", autorizacao="", mensagem_processadora="", ip=None):
    pagamento = PagamentoVenda.objects.select_for_update().select_related("venda", "forma_pagamento").get(pk=pagamento.pk)
    if pagamento.status != StatusPagamento.ESTORNO_PENDENTE:
        raise ValidationError("Apenas pagamentos com estorno pendente podem ser confirmados.")
    if not pagamento.transacao_externa_id:
        raise ValidationError("Pagamento sem transacao externa deve ser estornado pelo fluxo local.")
    autorizacao = autorizacao.strip() if autorizacao else ""
    mensagem_processadora = mensagem_processadora.strip() if mensagem_processadora else ""
    if not (autorizacao or mensagem_processadora):
        raise ValidationError("Informe a autorizacao ou o retorno da adquirente antes de confirmar o estorno.")
    agora = timezone.now()
    mensagem = mensagem_processadora or "Estorno confirmado pela operadora."
    if autorizacao:
        mensagem = f"{mensagem} Autorizacao: {autorizacao}."
    pagamento.status = StatusPagamento.ESTORNADO
    pagamento.estornado_em = agora
    if motivo:
        pagamento.motivo_estorno = motivo
    pagamento.mensagem_processadora = mensagem
    pagamento.save(update_fields=["status", "estornado_em", "motivo_estorno", "mensagem_processadora"])
    _estornar_lancamento_pagamento(pagamento, usuario=usuario, motivo=motivo or pagamento.motivo_estorno or "Estorno eletrônico confirmado")
    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="vendas",
        acao="CONFIRMACAO_ESTORNO_TEF",
        descricao=(
            f"Estorno do pagamento {pagamento.id} confirmado para venda {pagamento.venda_id}. "
            f"Transacao: {pagamento.transacao_externa_id}. {mensagem}"
        ),
        objeto_tipo="PagamentoVenda",
        objeto_id=str(pagamento.id),
        ip=ip,
    )
    return pagamento

@transaction.atomic
def confirmar_estorno_parcial_eletronico(
    *,
    estorno,
    usuario,
    autorizacao="",
    transacao_estorno_id="",
    mensagem_processadora="",
    ip=None,
):
    estorno = (
        EstornoParcialPagamento.objects.select_for_update()
        .select_related("pagamento__venda", "pagamento__forma_pagamento", "devolucao")
        .get(pk=estorno.pk)
    )
    if estorno.status != StatusEstornoParcial.PENDENTE:
        raise ValidationError("Apenas estornos parciais pendentes podem ser confirmados.")
    autorizacao = autorizacao.strip() if autorizacao else ""
    transacao_estorno_id = transacao_estorno_id.strip() if transacao_estorno_id else ""
    mensagem_processadora = mensagem_processadora.strip() if mensagem_processadora else ""
    if not (autorizacao or transacao_estorno_id or mensagem_processadora):
        raise ValidationError("Informe a autorização ou o retorno da adquirente antes de confirmar o estorno.")

    lancamento = (
        estorno.pagamento.lancamentos_financeiros.filter(
            origem="PDV_VENDA",
            estorno_de__isnull=True,
        )
        .order_by("id")
        .first()
    )
    if not lancamento:
        raise ValidationError("O lançamento financeiro original deste pagamento não foi localizado.")
    saldo_lancamento = _quantizar_moeda(lancamento.valor - _total_estornado_lancamento(lancamento))
    if estorno.valor > saldo_lancamento:
        raise ValidationError("O valor do estorno parcial excede o saldo financeiro disponível.")

    mensagem = mensagem_processadora or "Estorno parcial confirmado pela operadora."
    _registrar_estorno_lancamento_parcial(
        lancamento=lancamento,
        valor=estorno.valor,
        usuario=usuario,
        motivo=f"Devolução {estorno.devolucao_id}: {estorno.motivo}",
    )
    estorno.status = StatusEstornoParcial.CONFIRMADO
    estorno.codigo_autorizacao = autorizacao
    estorno.transacao_estorno_id = transacao_estorno_id
    estorno.mensagem_processadora = mensagem
    estorno.confirmado_em = timezone.now()
    estorno.usuario_confirmacao = usuario
    estorno.save(
        update_fields=[
            "status",
            "codigo_autorizacao",
            "transacao_estorno_id",
            "mensagem_processadora",
            "confirmado_em",
            "usuario_confirmacao",
        ]
    )
    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="vendas",
        acao="CONFIRMACAO_ESTORNO_PARCIAL_TEF",
        descricao=(
            f"Estorno parcial {estorno.id} confirmado para o pagamento {estorno.pagamento_id}, "
            f"venda {estorno.pagamento.venda_id}, no valor de R$ {estorno.valor}. "
            f"Transação original: {estorno.pagamento.transacao_externa_id}."
        ),
        objeto_tipo="EstornoParcialPagamento",
        objeto_id=str(estorno.id),
        ip=ip,
    )
    return estorno


def _estornar_lancamento_pagamento(pagamento, *, usuario, motivo):
    from apps.financeiro.models import LancamentoFinanceiro

    lancamentos = LancamentoFinanceiro.objects.filter(
        pagamento_venda=pagamento,
        estorno_de__isnull=True,
    )
    for lancamento in lancamentos:
        saldo_lancamento = _quantizar_moeda(lancamento.valor - _total_estornado_lancamento(lancamento))
        if saldo_lancamento <= 0:
            continue
        _registrar_estorno_lancamento_parcial(
            lancamento=lancamento,
            valor=saldo_lancamento,
            usuario=usuario,
            motivo=f"Estorno do pagamento {pagamento.id}: {motivo}",
        )


def _estornar_lancamentos_pagamentos_locais(venda, *, motivo):
    from apps.financeiro.models import LancamentoFinanceiro

    lancamentos = LancamentoFinanceiro.objects.select_related("pagamento_venda").filter(
        pagamento_venda__venda=venda,
        pagamento_venda__status=StatusPagamento.ESTORNADO,
        estorno_de__isnull=True,
    )
    for lancamento in lancamentos:
        saldo_lancamento = _quantizar_moeda(lancamento.valor - _total_estornado_lancamento(lancamento))
        if saldo_lancamento <= 0:
            continue
        _registrar_estorno_lancamento_parcial(
            lancamento=lancamento,
            valor=saldo_lancamento,
            usuario=venda.usuario,
            motivo=f"Cancelamento da venda {venda.id}: {motivo}",
        )


def _total_estornado_lancamento(lancamento):
    from django.db.models import Sum

    total = lancamento.estornos.aggregate(total=Sum("valor"))["total"] or Decimal("0.00")
    return _quantizar_moeda(total)


def _registrar_estorno_lancamento_parcial(*, lancamento, valor, usuario, motivo):
    from apps.financeiro.models import TipoLancamentoFinanceiro
    from apps.financeiro.services import registrar_lancamento

    valor = _quantizar_moeda(valor)
    if valor <= 0:
        return None
    tipo_inverso = (
        TipoLancamentoFinanceiro.SAIDA
        if lancamento.tipo == TipoLancamentoFinanceiro.ENTRADA
        else TipoLancamentoFinanceiro.ENTRADA
    )
    return registrar_lancamento(
        conta=lancamento.conta,
        tipo=tipo_inverso,
        descricao=f"Estorno do lancamento #{lancamento.id}: {motivo}",
        valor=valor,
        data=timezone.localdate(),
        usuario=usuario,
        origem="ESTORNO",
        conta_financeira=lancamento.conta_financeira,
        transferencia=lancamento.transferencia,
        estorno_de=lancamento,
        pagamento_venda=lancamento.pagamento_venda,
        sangria=lancamento.sangria,
        suprimento=lancamento.suprimento,
    )


def _cancelar_contas_receber_venda(venda, *, usuario, motivo, ip=None):
    from apps.financeiro.models import StatusContaFinanceira
    from apps.financeiro.services import cancelar_conta

    for conta in venda.contas_financeiras.filter(status=StatusContaFinanceira.ABERTA):
        cancelar_conta(conta=conta, usuario=usuario, motivo=f"Cancelamento da venda {venda.id}: {motivo}", ip=ip)
