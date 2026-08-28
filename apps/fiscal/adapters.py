from dataclasses import dataclass
from inspect import signature

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ObjectDoesNotExist
from django.utils.module_loading import import_string


PROVEDOR_ADAPTER_PATHS = {
    "FOCUS": "apps.fiscal.focus_sefaz_adapter.FocusNFeSefazAdapter",
    "SEFAZ_DIRETA_GO": "apps.fiscal.sefaz_direta.SefazDiretaAdapter",
}


class SefazAdapterError(Exception):
    pass


@dataclass(frozen=True)
class SefazTransmissionResult:
    status: str
    chave_acesso: str = ""
    protocolo: str = ""
    mensagem: str = ""
    xml_autorizado: str = ""


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
    chave_acesso: str = ""
    protocolo: str = ""
    protocolo_cancelamento: str = ""
    mensagem: str = ""
    xml_autorizado: str = ""


def caminho_adaptador_sefaz(*, filial=None):
    if filial is not None:
        try:
            configuracao = filial.configuracao_fiscal
        except ObjectDoesNotExist:
            configuracao = None
        if configuracao is not None:
            selecao = str(
                getattr(configuracao, "provedor_emissao", "PADRAO_SERVIDOR")
                or "PADRAO_SERVIDOR"
            )
            if selecao == "DESATIVADO":
                return ""
            if selecao in PROVEDOR_ADAPTER_PATHS:
                if (
                    selecao == "SEFAZ_DIRETA_GO"
                    and str(getattr(filial, "uf", "") or "").upper() != "GO"
                ):
                    raise ImproperlyConfigured(
                        "A conexão direta SEFAZ está disponível somente para filiais de Goiás."
                    )
                return PROVEDOR_ADAPTER_PATHS[selecao]
    return getattr(settings, "FISCAL_SEFAZ_ADAPTER", "").strip()


def carregar_adaptador_sefaz(*, filial=None):
    adapter_path = caminho_adaptador_sefaz(filial=filial)
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


def _diagnosticar_configuracao_operacional(adapter=None, *, filial=None):
    resultado = {
        "diagnostico_disponivel": False,
        "pronto": False,
        "provedor": "",
        "ambiente": "",
        "credenciais_configuradas": None,
        "rede_habilitada": None,
        "producao_habilitada": None,
        "mensagem": "O adaptador não expõe diagnóstico operacional seguro.",
    }
    if adapter is None:
        return resultado
    diagnosticar = getattr(adapter, "diagnosticar", None)
    if not callable(diagnosticar):
        return resultado
    resultado["diagnostico_disponivel"] = True
    resultado["provedor"] = str(
        getattr(adapter, "nome", adapter.__class__.__name__) or ""
    )[:120]
    try:
        parametros = signature(diagnosticar).parameters
        detalhes = (
            diagnosticar(filial=filial)
            if filial is not None and "filial" in parametros
            else diagnosticar()
        ) or {}
    except Exception:
        resultado["mensagem"] = "O diagnóstico operacional do adaptador falhou."
        return resultado
    if not isinstance(detalhes, dict):
        resultado["mensagem"] = "O adaptador retornou diagnóstico operacional inválido."
        return resultado
    resultado["pronto"] = bool(detalhes.get("pronto", False))
    resultado["provedor"] = str(
        detalhes.get("provedor") or resultado["provedor"]
    )[:120]
    resultado["ambiente"] = str(detalhes.get("ambiente") or "")[:40]
    for destino, origem in (
        ("credenciais_configuradas", "token_configurado"),
        ("rede_habilitada", "rede_habilitada"),
        ("producao_habilitada", "producao_habilitada"),
    ):
        if isinstance(detalhes.get(origem), bool):
            resultado[destino] = detalhes[origem]
    if resultado["pronto"]:
        resultado["mensagem"] = "Configuração operacional declarada pronta pelo adaptador."
    elif resultado["credenciais_configuradas"] is False:
        resultado["mensagem"] = "Credenciais do provedor não estão configuradas."
    elif resultado["rede_habilitada"] is False:
        resultado["mensagem"] = "A rede do adaptador permanece bloqueada."
    else:
        resultado["mensagem"] = "Configuração operacional incompleta."
    return resultado


def diagnosticar_adaptador_sefaz(*, filial=None):
    try:
        adapter_path = caminho_adaptador_sefaz(filial=filial)
    except ImproperlyConfigured as exc:
        return {
            "configurado": True,
            "carregavel": False,
            "assina_xml": False,
            "valida_schema": False,
            "cancela_documento": False,
            "inutiliza_numeracao": False,
            "consulta_documento": False,
            "adaptador": "",
            "erro": str(exc),
            "configuracao_operacional": _diagnosticar_configuracao_operacional(),
        }
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
            "configuracao_operacional": _diagnosticar_configuracao_operacional(),
        }
    try:
        adapter = carregar_adaptador_sefaz(filial=filial)
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
            "configuracao_operacional": _diagnosticar_configuracao_operacional(),
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
        "configuracao_operacional": _diagnosticar_configuracao_operacional(
            adapter, filial=filial
        ),
    }

def diagnosticar_contrato_adaptador_sefaz():
    """Expõe capacidades técnicas sem registrar chaves, XMLs ou credenciais."""
    diagnostico = diagnosticar_adaptador_sefaz()
    requisitos = {
        "transmissao": bool(diagnostico["carregavel"]),
        "cancelamento": bool(diagnostico["cancela_documento"]),
        "inutilizacao": bool(diagnostico["inutiliza_numeracao"]),
        "consulta": bool(diagnostico["consulta_documento"]),
        "assinatura_pelo_provedor": bool(diagnostico["assina_xml"]),
        "validacao_schema_pelo_provedor": bool(diagnostico["valida_schema"]),
    }
    pendencias = []
    if not diagnostico["configurado"]:
        pendencias.append("Defina FISCAL_SEFAZ_ADAPTER com a classe do provedor fiscal.")
    elif not diagnostico["carregavel"]:
        pendencias.append(diagnostico["erro"] or "O adaptador fiscal não pôde ser carregado.")
    for chave, titulo in (
        ("cancelamento", "cancelamento"),
        ("inutilizacao", "inutilização"),
        ("consulta", "consulta de protocolo"),
    ):
        if diagnostico["carregavel"] and not requisitos[chave]:
            pendencias.append(f"O adaptador não implementa {titulo}.")
    return {
        "contrato": "sefaz_adapter_contract_v1",
        "adaptador": diagnostico["adaptador"],
        "configurado": diagnostico["configurado"],
        "carregavel": diagnostico["carregavel"],
        "requisitos": requisitos,
        "configuracao_operacional": diagnostico["configuracao_operacional"],
        "pendencias": pendencias,
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
        xml_autorizado=str(retorno.get("xml_autorizado") or "").strip(),
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
        chave_acesso=str(retorno.get("chave_acesso") or "").strip(),
        protocolo=str(retorno.get("protocolo") or "").strip(),
        protocolo_cancelamento=str(retorno.get("protocolo_cancelamento") or "").strip(),
        mensagem=str(retorno.get("mensagem") or "").strip()[:2000],
        xml_autorizado=str(retorno.get("xml_autorizado") or "").strip(),
    )
    if resultado.chave_acesso and (
        len(resultado.chave_acesso) != 44 or not resultado.chave_acesso.isdigit()
    ):
        raise SefazAdapterError("A consulta SEFAZ retornou uma chave de acesso inválida.")
    if status in {"AUTORIZADO", "DENEGADO"} and not resultado.protocolo:
        raise SefazAdapterError("A consulta SEFAZ não retornou o protocolo do documento.")
    if status == "CANCELADO" and not resultado.protocolo_cancelamento:
        raise SefazAdapterError("A consulta SEFAZ não retornou o protocolo de cancelamento.")
    if status in {"NAO_LOCALIZADO", "PENDENTE"} and not resultado.mensagem:
        raise SefazAdapterError("A consulta SEFAZ deve informar a situação encontrada.")
    return resultado
