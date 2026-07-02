from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.accounts.permissions import SUPERVISAO, has_role

from .models import AcessoPdvNuvem, StatusAcessoPdvNuvem


def acesso_pdv_nuvem_aprovado(usuario, filial=None):
    queryset = AcessoPdvNuvem.objects.filter(usuario=usuario, status=StatusAcessoPdvNuvem.APROVADO)
    if filial:
        queryset = queryset.filter(filial=filial)
    return queryset.exists()


def solicitar_acesso_pdv_nuvem(*, usuario, filial=None, ip=None, user_agent="", justificativa=""):
    solicitacao = (
        AcessoPdvNuvem.objects.filter(usuario=usuario, filial=filial, status=StatusAcessoPdvNuvem.PENDENTE)
        .order_by("-criado_em")
        .first()
    )
    if solicitacao:
        return solicitacao, False
    solicitacao = AcessoPdvNuvem.objects.create(
        usuario=usuario,
        filial=filial,
        ip=ip,
        user_agent=(user_agent or "")[:255],
        justificativa=justificativa,
    )
    return solicitacao, True


def decidir_acesso_pdv_nuvem(*, solicitacao, admin, aprovar, justificativa=""):
    if not has_role(admin, SUPERVISAO):
        raise ValidationError("Apenas admin ou gerente pode decidir acesso ao PDV em nuvem.")
    if solicitacao.status != StatusAcessoPdvNuvem.PENDENTE:
        raise ValidationError("Esta solicitacao ja foi decidida.")
    solicitacao.status = StatusAcessoPdvNuvem.APROVADO if aprovar else StatusAcessoPdvNuvem.RECUSADO
    if justificativa:
        solicitacao.justificativa = justificativa
    solicitacao.decidido_por = admin
    solicitacao.decidido_em = timezone.now()
    solicitacao.save(update_fields=["status", "justificativa", "decidido_por", "decidido_em", "atualizado_em"])
    return solicitacao
