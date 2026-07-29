from dataclasses import dataclass

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string


class SefazAdapterError(Exception):
    pass


@dataclass(frozen=True)
class SefazTransmissionResult:
    status: str
    chave_acesso: str = ""
    protocolo: str = ""
    mensagem: str = ""


def carregar_adaptador_sefaz():
    adapter_path = getattr(settings, "FISCAL_SEFAZ_ADAPTER", "").strip()
    if not adapter_path:
        raise ImproperlyConfigured("Nenhum adaptador SEFAZ oficial foi configurado.")
    try:
        adapter_class = import_string(adapter_path)
        adapter = adapter_class()
    except (ImportError, AttributeError, TypeError) as exc:
        raise ImproperlyConfigured("Nao foi possivel carregar o adaptador SEFAZ configurado.") from exc
    if not callable(getattr(adapter, "transmitir", None)):
        raise ImproperlyConfigured("O adaptador SEFAZ deve implementar o metodo transmitir.")
    return adapter


def diagnosticar_adaptador_sefaz():
    adapter_path = getattr(settings, "FISCAL_SEFAZ_ADAPTER", "").strip()
    if not adapter_path:
        return {
            "configurado": False,
            "carregavel": False,
            "assina_xml": False,
            "valida_schema": False,
            "adaptador": "",
            "erro": "",
        }
    try:
        adapter = carregar_adaptador_sefaz()
    except ImproperlyConfigured as exc:
        return {
            "configurado": True,
            "carregavel": False,
            "assina_xml": False,
            "valida_schema": False,
            "adaptador": adapter_path,
            "erro": str(exc),
        }
    assina_xml = bool(getattr(adapter, "assina_xml", False))
    valida_schema = bool(getattr(adapter, "valida_schema", False))
    return {
        "configurado": True,
        "carregavel": True,
        "assina_xml": assina_xml,
        "valida_schema": valida_schema,
        "adaptador": adapter_path,
        "erro": "" if assina_xml else "O adaptador nao declarou capacidade de assinatura XML.",
    }

def normalizar_retorno_transmissao(retorno):
    if not isinstance(retorno, dict):
        raise SefazAdapterError("O adaptador SEFAZ retornou um formato invalido.")

    status = str(retorno.get("status") or "").upper().strip()
    if status not in {"AUTORIZADO", "REJEITADO", "PENDENTE"}:
        raise SefazAdapterError("O adaptador SEFAZ retornou um status desconhecido.")

    resultado = SefazTransmissionResult(
        status=status,
        chave_acesso=str(retorno.get("chave_acesso") or "").strip(),
        protocolo=str(retorno.get("protocolo") or "").strip(),
        mensagem=str(retorno.get("mensagem") or "").strip()[:2000],
    )
    if status == "AUTORIZADO":
        if len(resultado.chave_acesso) != 44 or not resultado.chave_acesso.isdigit():
            raise SefazAdapterError("A autorizacao SEFAZ nao retornou uma chave de acesso valida.")
        if not resultado.protocolo:
            raise SefazAdapterError("A autorizacao SEFAZ nao retornou protocolo.")
    if status == "REJEITADO" and not resultado.mensagem:
        raise SefazAdapterError("A rejeicao SEFAZ deve informar o motivo.")
    return resultado
