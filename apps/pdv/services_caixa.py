from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.financeiro.models import TipoLancamentoFinanceiro
from apps.financeiro.services import conta_caixa_pdv, registrar_lancamento

from .models import Caixa, Sangria, StatusCaixa, Suprimento


def _caixa_aberto_bloqueado(caixa):
    caixa_bloqueado = (
        Caixa.objects.select_for_update()
        .select_related("filial", "filial__empresa")
        .get(pk=caixa.pk)
    )
    if caixa_bloqueado.status != StatusCaixa.ABERTO:
        raise ValidationError("Este caixa não está aberto.")
    return caixa_bloqueado


@transaction.atomic
def registrar_sangria_caixa(*, caixa, usuario, valor, motivo):
    caixa = _caixa_aberto_bloqueado(caixa)
    sangria = Sangria.objects.create(
        caixa=caixa,
        usuario=usuario,
        valor=valor,
        motivo=motivo,
    )
    registrar_lancamento(
        conta=conta_caixa_pdv(caixa.filial),
        tipo=TipoLancamentoFinanceiro.SAIDA,
        descricao=f"Sangria caixa #{caixa.id}: {sangria.motivo}",
        valor=sangria.valor,
        data=timezone.localdate(),
        usuario=usuario,
        origem="PDV_SANGRIA",
        sangria=sangria,
    )
    return sangria


@transaction.atomic
def registrar_suprimento_caixa(*, caixa, usuario, valor, motivo):
    caixa = _caixa_aberto_bloqueado(caixa)
    suprimento = Suprimento.objects.create(
        caixa=caixa,
        usuario=usuario,
        valor=valor,
        motivo=motivo,
    )
    registrar_lancamento(
        conta=conta_caixa_pdv(caixa.filial),
        tipo=TipoLancamentoFinanceiro.ENTRADA,
        descricao=f"Suprimento caixa #{caixa.id}: {suprimento.motivo}",
        valor=suprimento.valor,
        data=timezone.localdate(),
        usuario=usuario,
        origem="PDV_SUPRIMENTO",
        suprimento=suprimento,
    )
    return suprimento


@transaction.atomic
def fechar_caixa_operacional(*, caixa, usuario, valor_final):
    caixa = _caixa_aberto_bloqueado(caixa)
    caixa.valor_final = valor_final
    caixa.usuario_fechamento = usuario
    caixa.data_fechamento = timezone.now()
    caixa.status = StatusCaixa.FECHADO
    caixa.save(
        update_fields=[
            "valor_final",
            "usuario_fechamento",
            "data_fechamento",
            "status",
        ]
    )
    return caixa
