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


@dataclass(frozen=True)
class SefazCancellationResult:
    status: str
    protocolo: str = ""
    mensagem: str = ""


@dataclass(frozen=True)
class SefazInutilizationResult:
    status: str
    protocolo: str = ""
    mensagem: str = ""


@dataclass(frozen=True)
class SefazQueryResult:
    status: str
    protocolo: str = ""
    protocolo_cancelamento: str = ""
    mensagem: str = ""


def carregar_adaptador_sefaz():
    adapter_path = getattr(settings, "FISCAL_SEFAZ_ADAPTER", "").strip()
    if not adapter_path:
        raise ImproperlyConfigured("Nenhum adaptador SEFAZ oficial foi configurado.")
    try:
        adapter_class = import_string(adapter_path)
        adapter = adapter_class()
    except (ImportError, AttributeError, TypeError) as exc:
        raise ImproperlyConfigured("Não foi possível carregar o adaptador SEFAZ configurado.") from exc
    if not callable(getattr(adapter, "transmitir", None)):
        raise ImproperlyConfigured("O adaptador SEFAZ deve implementar o método transmitir.")
    return adapter


def diagnosticar_adaptador_sefaz():
    adapter_path = getattr(settings, "FISCAL_SEFAZ_ADAPTER", "").strip()
    if not adapter_path:
        return {
            "configurado": False,
            "carregavel": False,
            "assina_xml": False,
            "valida_schema": False,
            "cancela_documento": False,
            "inutiliza_numeracao": False,
            "consulta_documento": False,
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
            "cancela_documento": False,
            "inutiliza_numeracao": False,
            "consulta_documento": False,
            "adaptador": adapter_path,
            "erro": str(exc),
        }
    assina_xml = bool(getattr(adapter, "assina_xml", False))
    valida_schema = bool(getattr(adapter, "valida_schema", False))
    cancela_documento = callable(getattr(adapter, "cancelar", None))
    inutiliza_numeracao = callable(getattr(adapter, "inutilizar", None))
    consulta_documento = callable(getattr(adapter, "consultar", None))
    return {
        "configurado": True,
        "carregavel": True,
        "assina_xml": assina_xml,
        "valida_schema": valida_schema,
        "cancela_documento": cancela_documento,
        "inutiliza_numeracao": inutiliza_numeracao,
        "consulta_documento": consulta_documento,
        "adaptador": adapter_path,
        "erro": "" if assina_xml else "O adaptador não declarou capacidade de assinatura XML.",
    }

def normalizar_retorno_transmissao(retorno):
    if not isinstance(retorno, dict):
        raise SefazAdapterError("O adaptador SEFAZ retornou um formato inválido.")

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
            raise SefazAdapterError("A autorização SEFAZ não retornou uma chave de acesso valida.")
        if not resultado.protocolo:
            raise SefazAdapterError("A autorização SEFAZ não retornou protocolo.")
    if status == "REJEITADO" and not resultado.mensagem:
        raise SefazAdapterError("A rejeicao SEFAZ deve informar o motivo.")
    return resultado


def normalizar_retorno_cancelamento(retorno):
    if not isinstance(retorno, dict):
        raise SefazAdapterError("O adaptador SEFAZ retornou cancelamento em formato inválido.")

    status = str(retorno.get("status") or "").upper().strip()
    if status not in {"CANCELADO", "REJEITADO", "PENDENTE"}:
        raise SefazAdapterError("O adaptador SEFAZ retornou status de cancelamento desconhecido.")

    resultado = SefazCancellationResult(
        status=status,
        protocolo=str(retorno.get("protocolo") or "").strip(),
        mensagem=str(retorno.get("mensagem") or "").strip()[:2000],
    )
    if status == "CANCELADO" and not resultado.protocolo:
        raise SefazAdapterError("O cancelamento autorizado não retornou protocolo.")
    if status == "REJEITADO" and not resultado.mensagem:
        raise SefazAdapterError("A rejeição do cancelamento deve informar o motivo.")
    return resultado


def normalizar_retorno_inutilizacao(retorno):
    if not isinstance(retorno, dict):
        raise SefazAdapterError("O adaptador SEFAZ retornou inutilização em formato inválido.")

    status = str(retorno.get("status") or "").upper().strip()
    if status not in {"INUTILIZADA", "REJEITADA", "PENDENTE"}:
        raise SefazAdapterError("O adaptador SEFAZ retornou status de inutilização desconhecido.")

    resultado = SefazInutilizationResult(
        status=status,
        protocolo=str(retorno.get("protocolo") or "").strip(),
        mensagem=str(retorno.get("mensagem") or "").strip()[:2000],
    )
    if status == "INUTILIZADA" and not resultado.protocolo:
        raise SefazAdapterError("A inutilização autorizada não retornou protocolo.")
    if status == "REJEITADA" and not resultado.mensagem:
        raise SefazAdapterError("A rejeição da inutilização deve informar o motivo.")
    return resultado


def normalizar_retorno_consulta(retorno):
    if not isinstance(retorno, dict):
        raise SefazAdapterError("O adaptador SEFAZ retornou consulta em formato inválido.")

    status = str(retorno.get("status") or "").upper().strip()
    permitidos = {"AUTORIZADO", "CANCELADO", "DENEGADO", "NAO_LOCALIZADO", "PENDENTE"}
    if status not in permitidos:
        raise SefazAdapterError("O adaptador SEFAZ retornou status de consulta desconhecido.")

    resultado = SefazQueryResult(
        status=status,
        protocolo=str(retorno.get("protocolo") or "").strip(),
        protocolo_cancelamento=str(retorno.get("protocolo_cancelamento") or "").strip(),
        mensagem=str(retorno.get("mensagem") or "").strip()[:2000],
    )
    if status in {"AUTORIZADO", "DENEGADO"} and not resultado.protocolo:
        raise SefazAdapterError("A consulta SEFAZ não retornou o protocolo do documento.")
    if status == "CANCELADO" and not resultado.protocolo_cancelamento:
        raise SefazAdapterError("A consulta SEFAZ não retornou o protocolo de cancelamento.")
    if status in {"NAO_LOCALIZADO", "PENDENTE"} and not resultado.mensagem:
        raise SefazAdapterError("A consulta SEFAZ deve informar a situação encontrada.")
    return resultado
