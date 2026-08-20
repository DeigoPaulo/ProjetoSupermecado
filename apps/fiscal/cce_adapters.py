from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.utils.module_loading import import_string


CONTRATO_CARTA_CORRECAO = "fiscal_cce_v1"
STATUS_CARTA_CORRECAO = {"AUTORIZADA", "REJEITADA", "PENDENTE"}


def carregar_adaptador_cce():
    referencia = (getattr(settings, "FISCAL_CCE_ADAPTER", "") or "").strip()
    if not referencia:
        return None
    try:
        classe = import_string(referencia)
        adaptador = classe()
    except Exception as exc:
        raise ImproperlyConfigured("Não foi possível carregar FISCAL_CCE_ADAPTER.") from exc
    if not callable(getattr(adaptador, "corrigir", None)):
        raise ImproperlyConfigured(
            "O adaptador de CC-e deve implementar corrigir(documento, sequencia, correcao, idempotency_key)."
        )
    return adaptador


def diagnostico_adaptador_cce():
    referencia = (getattr(settings, "FISCAL_CCE_ADAPTER", "") or "").strip()
    if not referencia:
        return {
            "contrato": CONTRATO_CARTA_CORRECAO,
            "configurado": False,
            "disponivel": False,
            "adaptador": "",
            "mensagem": "Configure FISCAL_CCE_ADAPTER para transmitir a CC-e.",
        }
    try:
        adaptador = carregar_adaptador_cce()
    except ImproperlyConfigured as exc:
        return {
            "contrato": CONTRATO_CARTA_CORRECAO,
            "configurado": True,
            "disponivel": False,
            "adaptador": referencia,
            "mensagem": str(exc),
        }
    resultado = {
        "contrato": CONTRATO_CARTA_CORRECAO,
        "configurado": True,
        "disponivel": True,
        "adaptador": referencia,
        "provedor": getattr(adaptador, "nome", adaptador.__class__.__name__),
        "mensagem": "Adaptador disponível para CC-e controlada.",
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


def normalizar_retorno_cce(retorno):
    if not isinstance(retorno, dict):
        raise ValidationError("O adaptador retornou uma Carta de Correção inválida.")
    if retorno.get("contrato") != CONTRATO_CARTA_CORRECAO:
        raise ValidationError(
            f"Contrato de CC-e incompatível: esperado {CONTRATO_CARTA_CORRECAO}."
        )
    status = str(retorno.get("status") or "").strip().upper()
    if status not in STATUS_CARTA_CORRECAO:
        raise ValidationError("O adaptador retornou um status de CC-e inválido.")
    return {
        "status": status,
        "codigo_status": str(retorno.get("codigo_status") or "")[:10],
        "protocolo": str(retorno.get("protocolo") or "")[:80],
        "mensagem": str(retorno.get("mensagem") or "")[:2000],
        "xml_envio": str(retorno.get("xml_envio") or ""),
        "xml_retorno": str(retorno.get("xml_retorno") or ""),
    }
