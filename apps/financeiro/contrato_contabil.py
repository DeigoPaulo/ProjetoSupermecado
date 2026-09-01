from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Max

from apps.auditoria.models import LogAuditoria
from apps.empresas.models import Empresa

from .models import (
    ContratoIntegracaoContabil,
    StatusContratoIntegracaoContabil,
)


def resumo_contrato_contabil(empresa):
    if not empresa:
        return {
            "contrato": "accounting_integration_agreement_v1",
            "configurado": False,
            "validado": False,
            "status": "NAO_CONFIGURADO",
        }
    versoes = ContratoIntegracaoContabil.objects.filter(empresa=empresa)
    ultima = versoes.order_by("-versao").first()
    validada = versoes.filter(status=StatusContratoIntegracaoContabil.VALIDADO).order_by("-versao").first()
    base = {
        "contrato": "accounting_integration_agreement_v1",
        "configurado": bool(ultima),
        "validado": bool(validada),
        "status": validada.status if validada else (ultima.status if ultima else "NAO_CONFIGURADO"),
        "ultima_versao": ultima.versao if ultima else None,
        "versao_validada": validada.versao if validada else None,
    }
    if not validada:
        if not ultima:
            return base
        return {
            **base,
            "software_contabil": ultima.software_contabil,
            "formato_entrega": ultima.formato_entrega,
            "formato_entrega_descricao": ultima.get_formato_entrega_display(),
            "contrato_tecnico": ultima.contrato_tecnico,
            "responsavel_efd_icms_ipi": ultima.responsavel_efd_icms_ipi,
            "responsavel_efd_descricao": ultima.get_responsavel_efd_icms_ipi_display(),
            "responsavel_efd_nome": ultima.responsavel_efd_nome,
        }
    return {
        **base,
        "software_contabil": validada.software_contabil,
        "formato_entrega": validada.formato_entrega,
        "formato_entrega_descricao": validada.get_formato_entrega_display(),
        "contrato_tecnico": validada.contrato_tecnico,
        "responsavel_efd_icms_ipi": validada.responsavel_efd_icms_ipi,
        "responsavel_efd_descricao": validada.get_responsavel_efd_icms_ipi_display(),
        "responsavel_efd_nome": validada.responsavel_efd_nome,
        "aceite_referencia": validada.aceite_referencia,
    }


@transaction.atomic
def registrar_contrato_contabil(
    *, empresa, usuario, software_contabil, formato_entrega,
    responsavel_efd_icms_ipi, responsavel_efd_nome="",
    aceite_referencia="", observacoes="", validar=False, ip=None,
):
    if not usuario or not usuario.is_active or not usuario.is_superuser:
        raise PermissionDenied("Somente o Master pode registrar ou validar o contrato contábil.")
    empresa = Empresa.objects.select_for_update().get(pk=empresa.pk)
    ultima_versao = (
        ContratoIntegracaoContabil.objects.filter(empresa=empresa).aggregate(maior=Max("versao"))["maior"]
        or 0
    )
    contrato = ContratoIntegracaoContabil(
        empresa=empresa,
        versao=ultima_versao + 1,
        software_contabil=(software_contabil or "").strip(),
        formato_entrega=formato_entrega,
        responsavel_efd_icms_ipi=responsavel_efd_icms_ipi,
        responsavel_efd_nome=(responsavel_efd_nome or "").strip(),
        aceite_referencia=(aceite_referencia or "").strip(),
        observacoes=(observacoes or "").strip(),
        status=(
            StatusContratoIntegracaoContabil.VALIDADO
            if validar
            else StatusContratoIntegracaoContabil.RASCUNHO
        ),
        criado_por=usuario,
    )
    contrato.save()
    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="financeiro",
        acao="VALIDAR_CONTRATO_CONTABIL" if validar else "CRIAR_RASCUNHO_CONTRATO_CONTABIL",
        descricao=(
            f"Contrato contábil v{contrato.versao} registrado para {empresa.nome_fantasia}; "
            f"estado {contrato.status}."
        ),
        objeto_tipo="ContratoIntegracaoContabil",
        objeto_id=str(contrato.pk),
        ip=ip,
    )
    return contrato
