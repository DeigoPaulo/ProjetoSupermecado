from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.auditoria.models import LogAuditoria

from .models import ConciliacaoLancamentoFinanceiro, ContaFinanceira, ContaMovimentoFinanceiro, LancamentoFinanceiro, StatusContaFinanceira, TipoContaFinanceira, TipoContaMovimento, TipoLancamentoFinanceiro, TransferenciaFinanceira


def _publicar_lancamento_sincronizacao(lancamento):
    from apps.empresas.services_sincronizacao import enfileirar_evento

    filial = lancamento.conta.filial
    usuario = lancamento.usuario
    enfileirar_evento(
        empresa=filial.empresa,
        filial=filial,
        tipo="financeiro.lancamento_registrado",
        objeto_tipo="LancamentoFinanceiro",
        objeto_id=lancamento.pk,
        chave_idempotencia=f"financeiro:lancamento:{filial.empresa_id}:{lancamento.pk}",
        payload={
            "contrato": "financeiro_lancamento_v1",
            "lancamento_id": str(lancamento.pk),
            "filial_cnpj": filial.cnpj,
            "filial_nome": filial.nome,
            "tipo": lancamento.tipo,
            "origem": lancamento.origem,
            "descricao": lancamento.descricao,
            "valor": str(lancamento.valor),
            "data": lancamento.data.isoformat(),
            "conta_movimento": {
                "nome": lancamento.conta.nome,
                "tipo": lancamento.conta.tipo,
            },
            "centro_custo": (
                {"codigo": lancamento.centro_custo.codigo, "nome": lancamento.centro_custo.nome}
                if lancamento.centro_custo_id else None
            ),
            "conta_contabil": (
                {
                    "codigo": lancamento.conta_contabil.codigo,
                    "nome": lancamento.conta_contabil.nome,
                    "natureza": lancamento.conta_contabil.natureza,
                }
                if lancamento.conta_contabil_id else None
            ),
            "conta_financeira_id": str(lancamento.conta_financeira_id or ""),
            "estorno_de_id": str(lancamento.estorno_de_id or ""),
            "usuario": usuario.get_username() if usuario else "",
            "criado_em": lancamento.criado_em.isoformat(),
        },
    )


def registrar_lancamento(*, conta, tipo, descricao, valor, data, usuario, origem, conta_financeira=None, centro_custo=None, conta_contabil=None, transferencia=None, estorno_de=None, pagamento_venda=None, sangria=None, suprimento=None):
    if centro_custo is None and conta_financeira is not None:
        centro_custo = conta_financeira.centro_custo
    if conta_contabil is None and conta_financeira is not None and conta_financeira.categoria_id:
        conta_contabil = conta_financeira.categoria.conta_contabil
    lancamento = LancamentoFinanceiro.objects.create(
        conta=conta,
        tipo=tipo,
        origem=origem,
        descricao=descricao,
        valor=valor,
        data=data,
        conta_financeira=conta_financeira,
        centro_custo=centro_custo,
        conta_contabil=conta_contabil,
        transferencia=transferencia,
        estorno_de=estorno_de,
        pagamento_venda=pagamento_venda,
        sangria=sangria,
        suprimento=suprimento,
        usuario=usuario,
    )
    _publicar_lancamento_sincronizacao(lancamento)
    return lancamento


def conta_caixa_pdv(filial):
    conta, _ = ContaMovimentoFinanceiro.objects.get_or_create(
        filial=filial,
        nome="Caixa PDV",
        defaults={"tipo": TipoContaMovimento.CAIXA, "saldo_inicial": 0, "ativa": True},
    )
    if not conta.ativa:
        conta.ativa = True
        conta.save(update_fields=["ativa", "atualizado_em"])
    return conta


@transaction.atomic
def realizar_transferencia(*, conta_origem, conta_destino, valor, data, usuario, descricao="", ip=None):
    contas = {
        conta.pk: conta
        for conta in ContaMovimentoFinanceiro.objects.select_for_update().select_related("filial__empresa").filter(
            pk__in=[conta_origem.pk, conta_destino.pk]
        )
    }
    origem = contas.get(conta_origem.pk)
    destino = contas.get(conta_destino.pk)
    if not origem or not destino:
        raise ValidationError("Conta de origem ou destino não encontrada.")
    if origem.pk == destino.pk:
        raise ValidationError("As contas de origem e destino devem ser diferentes.")
    if not origem.ativa or not destino.ativa:
        raise ValidationError("A transferencia exige contas ativas.")
    if origem.filial.empresa_id != destino.filial.empresa_id:
        raise ValidationError("Transferências entre empresas diferentes não são permitidas.")
    if valor <= 0:
        raise ValidationError("Valor da transferencia deve ser maior que zero.")
    if origem.saldo_atual < valor:
        raise ValidationError("Saldo insuficiente na conta de origem.")

    transferencia = TransferenciaFinanceira.objects.create(
        conta_origem=origem,
        conta_destino=destino,
        valor=valor,
        data=data or timezone.localdate(),
        descricao=descricao,
        usuario=usuario,
    )
    texto = descricao or f"Transferencia entre {origem.nome} e {destino.nome}"
    registrar_lancamento(
        conta=origem, tipo=TipoLancamentoFinanceiro.SAIDA, descricao=texto, valor=valor,
        data=transferencia.data, usuario=usuario, origem="TRANSFERENCIA", transferencia=transferencia,
    )
    registrar_lancamento(
        conta=destino, tipo=TipoLancamentoFinanceiro.ENTRADA, descricao=texto, valor=valor,
        data=transferencia.data, usuario=usuario, origem="TRANSFERENCIA", transferencia=transferencia,
    )
    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="financeiro",
        acao="TRANSFERENCIA",
        descricao=f"Transferencia {transferencia.id}: {origem} para {destino}. Valor: {valor}.",
        objeto_tipo="TransferenciaFinanceira",
        objeto_id=str(transferencia.id),
        ip=ip,
    )
    return transferencia


@transaction.atomic
def estornar_lancamento(*, lancamento, usuario, motivo, data=None, ip=None):
    motivo = (motivo or "").strip()
    if not motivo:
        raise ValidationError("Informe o motivo do estorno.")

    lancamento = LancamentoFinanceiro.objects.select_for_update().select_related("conta").get(pk=lancamento.pk)
    if lancamento.estorno_de_id:
        raise ValidationError("Lançamento de estorno não pode ser estornado novamente.")
    if lancamento.estornos.exists():
        raise ValidationError("Este lançamento ja possui estorno registrado.")

    tipo_inverso = (
        TipoLancamentoFinanceiro.SAIDA
        if lancamento.tipo == TipoLancamentoFinanceiro.ENTRADA
        else TipoLancamentoFinanceiro.ENTRADA
    )
    estorno = registrar_lancamento(
        conta=lancamento.conta,
        tipo=tipo_inverso,
        descricao=f"Estorno do lancamento #{lancamento.id}: {motivo}",
        valor=lancamento.valor,
        data=data or timezone.localdate(),
        usuario=usuario,
        origem="ESTORNO",
        conta_financeira=lancamento.conta_financeira,
        centro_custo=lancamento.centro_custo,
        conta_contabil=lancamento.conta_contabil,
        transferencia=lancamento.transferencia,
        estorno_de=lancamento,
        pagamento_venda=lancamento.pagamento_venda,
        sangria=lancamento.sangria,
        suprimento=lancamento.suprimento,
    )
    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="financeiro",
        acao="ESTORNO_LANCAMENTO",
        descricao=f"Lancamento {lancamento.id} estornado pelo lancamento {estorno.id}. Motivo: {motivo}",
        objeto_tipo="LancamentoFinanceiro",
        objeto_id=str(lancamento.id),
        ip=ip,
    )
    return estorno


@transaction.atomic
def baixar_conta(*, conta, usuario, data_pagamento, valor_pago, forma_pagamento="", conta_movimento=None, ip=None):
    conta = ContaFinanceira.objects.select_for_update().get(pk=conta.pk)
    if conta.status != StatusContaFinanceira.ABERTA:
        raise ValidationError("Apenas contas abertas podem receber baixa.")
    if valor_pago <= 0:
        raise ValidationError("Valor da baixa deve ser maior que zero.")
    conta.status = StatusContaFinanceira.PAGA
    conta.data_pagamento = data_pagamento or timezone.localdate()
    conta.valor_pago = valor_pago
    conta.forma_pagamento = forma_pagamento
    conta.conta_movimento = conta_movimento
    conta.save(update_fields=["status", "data_pagamento", "valor_pago", "forma_pagamento", "conta_movimento", "atualizado_em"])
    if conta_movimento:
        if conta_movimento.filial_id != conta.filial_id:
            raise ValidationError("A conta de movimento deve pertencer a mesma filial da conta financeira.")
        tipo_lancamento = TipoLancamentoFinanceiro.ENTRADA if conta.tipo == TipoContaFinanceira.RECEBER else TipoLancamentoFinanceiro.SAIDA
        registrar_lancamento(
            conta=conta_movimento,
            tipo=tipo_lancamento,
            descricao=conta.descricao,
            valor=valor_pago,
            data=conta.data_pagamento,
            usuario=usuario,
            origem="BAIXA_CONTA",
            conta_financeira=conta,
        )
    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="financeiro",
        acao="BAIXA_CONTA",
        descricao=f"Conta {conta.id} baixada. Valor: {valor_pago}.",
        objeto_tipo="ContaFinanceira",
        objeto_id=str(conta.id),
        ip=ip,
    )
    return conta


@transaction.atomic
def cancelar_conta(*, conta, usuario, motivo="", ip=None):
    conta = ContaFinanceira.objects.select_for_update().get(pk=conta.pk)
    if conta.status == StatusContaFinanceira.CANCELADA:
        return conta
    if conta.status == StatusContaFinanceira.PAGA:
        raise ValidationError("Conta paga não pode ser cancelada.")
    conta.status = StatusContaFinanceira.CANCELADA
    conta.observacoes = f"{conta.observacoes}\nCancelada: {motivo}".strip()
    conta.save(update_fields=["status", "observacoes", "atualizado_em"])
    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="financeiro",
        acao="CANCELAMENTO_CONTA",
        descricao=f"Conta {conta.id} cancelada. Motivo: {motivo or '-'}",
        objeto_tipo="ContaFinanceira",
        objeto_id=str(conta.id),
        ip=ip,
    )
    return conta

@transaction.atomic
def conciliar_lancamento(*, lancamento, data_conciliacao, referencia_externa, usuario, observacao="", ip=None):
    lancamento = LancamentoFinanceiro.objects.select_for_update().select_related("conta").get(pk=lancamento.pk)
    referencia_externa = (referencia_externa or "").strip()
    if not referencia_externa:
        raise ValidationError("Informe a referência do extrato ou comprovante.")
    if ConciliacaoLancamentoFinanceiro.objects.filter(lancamento=lancamento).exists():
        raise ValidationError("Este lançamento ja foi conciliado.")
    conciliacao = ConciliacaoLancamentoFinanceiro.objects.create(
        lancamento=lancamento,
        data_conciliacao=data_conciliacao,
        referencia_externa=referencia_externa,
        observacao=(observacao or "").strip(),
        usuario=usuario,
    )
    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="financeiro",
        acao="CONCILIA_LANCAMENTO_FINANCEIRO",
        descricao=f"Lancamento #{lancamento.pk} conciliado com a referencia {referencia_externa}.",
        objeto_tipo="ConciliacaoLancamentoFinanceiro",
        objeto_id=str(conciliacao.pk),
        ip=ip,
    )
    return conciliacao