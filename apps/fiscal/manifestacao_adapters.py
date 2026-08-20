from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.utils.module_loading import import_string


CONTRATO_MANIFESTACAO_DESTINATARIO = "fiscal_dfe_manifestation_v1"
STATUS_MANIFESTACAO = {"AUTORIZADA", "REJEITADA", "PENDENTE"}


def carregar_adaptador_manifestacao():
    referencia = (getattr(settings, "FISCAL_MANIFESTACAO_ADAPTER", "") or "").strip()
    if not referencia:
        return None
    try:
        classe = import_string(referencia)
        adaptador = classe()
    except Exception as exc:
        raise ImproperlyConfigured(
            "Não foi possível carregar FISCAL_MANIFESTACAO_ADAPTER."
        ) from exc
    if not callable(getattr(adaptador, "manifestar", None)):
        raise ImproperlyConfigured(
            "O adaptador de manifestação deve implementar manifestar(documento, tipo, justificativa, idempotency_key)."
        )
    return adaptador


def diagnostico_adaptador_manifestacao():
    referencia = (getattr(settings, "FISCAL_MANIFESTACAO_ADAPTER", "") or "").strip()
    if not referencia:
        return {
            "contrato": CONTRATO_MANIFESTACAO_DESTINATARIO,
            "configurado": False,
            "disponivel": False,
            "adaptador": "",
            "mensagem": "Configure FISCAL_MANIFESTACAO_ADAPTER para transmitir manifestações.",
        }
    try:
        adaptador = carregar_adaptador_manifestacao()
    except ImproperlyConfigured as exc:
        return {
            "contrato": CONTRATO_MANIFESTACAO_DESTINATARIO,
            "configurado": True,
            "disponivel": False,
            "adaptador": referencia,
            "mensagem": str(exc),
        }
    resultado = {
        "contrato": CONTRATO_MANIFESTACAO_DESTINATARIO,
        "configurado": True,
        "disponivel": True,
        "adaptador": referencia,
        "provedor": getattr(adaptador, "nome", adaptador.__class__.__name__),
        "mensagem": "Adaptador disponível para manifestação controlada.",
    }
    diagnosticar = getattr(adaptador, "diagnosticar", None)
    if callable(diagnosticar):
        try:
            detalhes = diagnosticar() or {}
        except Exception:
            detalhes = {"disponivel": False, "mensagem": "O diagnóstico do adaptador falhou."}
        for chave in ("disponivel", "mensagem", "ambiente"):
            if chave in detalhes:
                resultado[chave] = detalhes[chave]
    return resultado


def normalizar_retorno_manifestacao(retorno):
    if not isinstance(retorno, dict):
        raise ValidationError("O adaptador retornou uma manifestação inválida.")
    if retorno.get("contrato") != CONTRATO_MANIFESTACAO_DESTINATARIO:
        raise ValidationError(
            f"Contrato de manifestação incompatível: esperado {CONTRATO_MANIFESTACAO_DESTINATARIO}."
        )
    status = str(retorno.get("status") or "").strip().upper()
    if status not in STATUS_MANIFESTACAO:
        raise ValidationError("O adaptador retornou um status de manifestação inválido.")
    return {
        "status": status,
        "codigo_status": str(retorno.get("codigo_status") or "")[:10],
        "protocolo": str(retorno.get("protocolo") or "")[:80],
        "mensagem": str(retorno.get("mensagem") or "")[:2000],
        "xml_envio": str(retorno.get("xml_envio") or ""),
        "xml_retorno": str(retorno.get("xml_retorno") or ""),
    }
