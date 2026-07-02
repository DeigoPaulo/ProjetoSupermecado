from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.auditoria.models import LogAuditoria

from .models import ContaFinanceira, StatusContaFinanceira


@transaction.atomic
def baixar_conta(*, conta, usuario, data_pagamento, valor_pago, forma_pagamento="", ip=None):
    conta = ContaFinanceira.objects.select_for_update().get(pk=conta.pk)
    if conta.status != StatusContaFinanceira.ABERTA:
        raise ValidationError("Apenas contas abertas podem receber baixa.")
    if valor_pago <= 0:
        raise ValidationError("Valor da baixa deve ser maior que zero.")
    conta.status = StatusContaFinanceira.PAGA
    conta.data_pagamento = data_pagamento or timezone.localdate()
    conta.valor_pago = valor_pago
    conta.forma_pagamento = forma_pagamento
    conta.save(update_fields=["status", "data_pagamento", "valor_pago", "forma_pagamento", "atualizado_em"])
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
        raise ValidationError("Conta paga nao pode ser cancelada.")
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
