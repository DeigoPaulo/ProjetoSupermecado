from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.utils.module_loading import import_string


CONTRATO_CONSULTA_CADASTRO = "fiscal_consulta_cadastro_v1"
STATUS_CONSULTA_CADASTRO = {"SUCESSO", "REJEITADA"}


def carregar_adaptador_consulta_cadastro():
    referencia = (
        getattr(settings, "FISCAL_CONSULTA_CADASTRO_ADAPTER", "") or ""
    ).strip()
    if not referencia:
        return None
    try:
        classe = import_string(referencia)
        adaptador = classe()
    except Exception as exc:
        raise ImproperlyConfigured(
            "Não foi possível carregar FISCAL_CONSULTA_CADASTRO_ADAPTER."
        ) from exc
    if not callable(getattr(adaptador, "consultar", None)):
        raise ImproperlyConfigured(
            "O adaptador de cadastro deve implementar "
            "consultar(filial, uf, tipo_documento, documento)."
        )
    return adaptador


def diagnostico_adaptador_consulta_cadastro():
    referencia = (
        getattr(settings, "FISCAL_CONSULTA_CADASTRO_ADAPTER", "") or ""
    ).strip()
    if not referencia:
        return {
            "contrato": CONTRATO_CONSULTA_CADASTRO,
            "configurado": False,
            "disponivel": False,
            "adaptador": "",
            "mensagem": "Configure o adaptador para consultar o cadastro estadual.",
        }
    try:
        adaptador = carregar_adaptador_consulta_cadastro()
    except ImproperlyConfigured as exc:
        return {
            "contrato": CONTRATO_CONSULTA_CADASTRO,
            "configurado": True,
            "disponivel": False,
            "adaptador": referencia,
            "mensagem": str(exc),
        }
    resultado = {
        "contrato": CONTRATO_CONSULTA_CADASTRO,
        "configurado": True,
        "disponivel": True,
        "adaptador": referencia,
        "provedor": getattr(adaptador, "nome", adaptador.__class__.__name__),
        "mensagem": "Adaptador disponível para consulta cadastral controlada.",
    }
    diagnosticar = getattr(adaptador, "diagnosticar", None)
    if callable(diagnosticar):
        try:
            detalhes = diagnosticar() or {}
        except Exception:
            detalhes = {
                "disponivel": False,
                "mensagem": "O diagnóstico do adaptador falhou.",
            }
        for chave in ("disponivel", "mensagem", "ambiente", "ufs"):
            if chave in detalhes:
                resultado[chave] = detalhes[chave]
    return resultado


def normalizar_retorno_consulta_cadastro(retorno):
    if not isinstance(retorno, dict):
        raise ValidationError("O adaptador retornou uma consulta cadastral inválida.")
    if retorno.get("contrato") != CONTRATO_CONSULTA_CADASTRO:
        raise ValidationError(
            f"Contrato cadastral incompatível: esperado {CONTRATO_CONSULTA_CADASTRO}."
        )
    status = str(retorno.get("status") or "").strip().upper()
    if status not in STATUS_CONSULTA_CADASTRO:
        raise ValidationError("O adaptador retornou um status cadastral inválido.")
    ocorrencias = retorno.get("ocorrencias") or []
    if not isinstance(ocorrencias, list):
        raise ValidationError("As ocorrências cadastrais retornadas são inválidas.")
    return {
        "status": status,
        "codigo_status": str(retorno.get("codigo_status") or "")[:10],
        "mensagem": str(retorno.get("mensagem") or "")[:2000],
        "ocorrencias": ocorrencias[:50],
        "xml_envio": str(retorno.get("xml_envio") or ""),
        "xml_retorno": str(retorno.get("xml_retorno") or ""),
    }
