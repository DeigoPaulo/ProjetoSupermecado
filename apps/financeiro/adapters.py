from dataclasses import dataclass

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string


class ContabilAdapterError(Exception):
    pass


@dataclass(frozen=True)
class ContabilExportResult:
    status: str
    protocolo: str = ""
    mensagem: str = ""


def carregar_adaptador_contabil():
    adapter_path = getattr(settings, "FINANCEIRO_CONTABIL_ADAPTER", "").strip()
    if not adapter_path:
        raise ImproperlyConfigured("Nenhum adaptador contábil foi configurado.")
    try:
        adapter_class = import_string(adapter_path)
        adapter = adapter_class()
    except (ImportError, AttributeError, TypeError) as exc:
        raise ImproperlyConfigured("Não foi possível carregar o adaptador contábil configurado.") from exc
    if not callable(getattr(adapter, "exportar", None)):
        raise ImproperlyConfigured("O adaptador contábil deve implementar o método exportar.")
    return adapter


def diagnosticar_adaptador_contabil():
    adapter_path = getattr(settings, "FINANCEIRO_CONTABIL_ADAPTER", "").strip()
    base = {
        "contrato": "financial_accounting_adapter_readiness_v1",
        "adaptador": adapter_path,
    }
    if not adapter_path:
        return {**base, "configurado": False, "carregavel": False, "provedor": "", "erro": ""}
    try:
        adapter = carregar_adaptador_contabil()
    except ImproperlyConfigured as exc:
        return {**base, "configurado": True, "carregavel": False, "provedor": "", "erro": str(exc)}
    return {
        **base,
        "configurado": True,
        "carregavel": True,
        "provedor": str(getattr(adapter, "nome", adapter.__class__.__name__))[:120],
        "erro": "",
    }


def normalizar_retorno_exportacao(retorno):
    if not isinstance(retorno, dict):
        raise ContabilAdapterError("O adaptador contábil retornou um formato inválido.")
    status = str(retorno.get("status") or "").upper().strip()
    if status not in {"ENVIADO", "PENDENTE", "REJEITADO"}:
        raise ContabilAdapterError("O adaptador contábil retornou um status desconhecido.")
    resultado = ContabilExportResult(
        status=status,
        protocolo=str(retorno.get("protocolo") or "").strip()[:120],
        mensagem=str(retorno.get("mensagem") or "").strip()[:2000],
    )
    if status == "ENVIADO" and not resultado.protocolo:
        raise ContabilAdapterError("O envio contábil confirmado deve retornar um protocolo.")
    if status == "REJEITADO" and not resultado.mensagem:
        raise ContabilAdapterError("A rejeição contábil deve informar o motivo.")
    return resultado