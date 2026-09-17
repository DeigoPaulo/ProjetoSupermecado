from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.utils.module_loading import import_string

from .chave_acesso import canonicalizar_chave_acesso_estrutural
from .roteamento_operacoes_fiscais import resolver_adaptador_operacao

CONTRATO_DISTRIBUICAO_DFE = "fiscal_dfe_distribution_v1"


def caminho_adaptador_dfe(*, filial=None):
    return resolver_adaptador_operacao(
        filial=filial,
        operacao="DFE",
        fallback=getattr(settings, "FISCAL_DFE_ADAPTER", ""),
    )


def carregar_adaptador_dfe(*, filial=None):
    referencia = caminho_adaptador_dfe(filial=filial)["adaptador"]
    if not referencia:
        return None
    try:
        classe = import_string(referencia)
        adaptador = classe()
    except Exception as exc:
        raise ImproperlyConfigured(
            "Não foi possível carregar FISCAL_DFE_ADAPTER."
        ) from exc
    if not callable(getattr(adaptador, "consultar", None)):
        raise ImproperlyConfigured(
            "O adaptador DF-e deve implementar consultar(cnpj, ultimo_nsu, limite)."
        )
    return adaptador


def diagnostico_adaptador_dfe(*, filial=None):
    try:
        roteamento = caminho_adaptador_dfe(filial=filial)
    except ImproperlyConfigured as exc:
        return {"contrato": CONTRATO_DISTRIBUICAO_DFE, "configurado": True, "disponivel": False, "adaptador": "", "mensagem": str(exc)}
    referencia = roteamento["adaptador"]
    if not referencia:
        return {
            "contrato": CONTRATO_DISTRIBUICAO_DFE,
            "configurado": False,
            "disponivel": False,
            "adaptador": "",
            "mensagem": "Configure FISCAL_DFE_ADAPTER para consultar documentos recebidos.",
        }
    try:
        adaptador = carregar_adaptador_dfe(filial=filial)
    except ImproperlyConfigured as exc:
        return {
            "contrato": CONTRATO_DISTRIBUICAO_DFE,
            "configurado": True,
            "disponivel": False,
            "adaptador": referencia,
            "mensagem": str(exc),
        }
    resultado = {
        "contrato": CONTRATO_DISTRIBUICAO_DFE,
        "configurado": True,
        "disponivel": True,
        "adaptador": referencia,
        "mensagem": "Adaptador disponível para consulta controlada.",
        "provedor": getattr(adaptador, "nome", adaptador.__class__.__name__),
        "canal": roteamento["provedor"],
    }
    diagnosticar = getattr(adaptador, "diagnosticar", None)
    if callable(diagnosticar):
        try:
            detalhes = diagnosticar() or {}
        except Exception:
            detalhes = {
                "disponivel": False,
                "mensagem": "O diagnóstico do adaptador DF-e falhou.",
            }
        for chave in ("disponivel", "mensagem", "ambiente"):
            if chave in detalhes:
                resultado[chave] = detalhes[chave]
    return resultado


def normalizar_lote_dfe(retorno):
    if not isinstance(retorno, dict):
        raise ValidationError("O adaptador DF-e retornou um lote inválido.")
    contrato = retorno.get("contrato")
    if contrato != CONTRATO_DISTRIBUICAO_DFE:
        raise ValidationError(
            f"Contrato DF-e incompatível: esperado {CONTRATO_DISTRIBUICAO_DFE}."
        )
    documentos = retorno.get("documentos", [])
    if not isinstance(documentos, list):
        raise ValidationError("A lista de documentos do adaptador DF-e é inválida.")
    ultimo_nsu = str(retorno.get("ultimo_nsu") or "").strip()
    max_nsu = str(retorno.get("max_nsu") or ultimo_nsu).strip()
    if ultimo_nsu and not ultimo_nsu.isdigit():
        raise ValidationError("O último NSU retornado pelo adaptador é inválido.")
    if max_nsu and not max_nsu.isdigit():
        raise ValidationError("O maior NSU retornado pelo adaptador é inválido.")
    for item in documentos:
        if not isinstance(item, dict):
            raise ValidationError("Um documento do lote DF-e possui formato inválido.")
        tipo_documento = str(item.get("tipo_documento") or "NFE").strip().upper()
        if tipo_documento not in {"NFE", "EVENTO"}:
            raise ValidationError("O tipo de documento do lote DF-e é inválido.")
        nsu = str(item.get("nsu") or "").strip()
        if nsu and not nsu.isdigit():
            raise ValidationError("Um documento do lote DF-e possui NSU inválido.")
        xml = item.get("xml")
        chave = canonicalizar_chave_acesso_estrutural(
            str(item.get("chave_acesso") or "")
        )
        if tipo_documento == "EVENTO" and (not xml or not chave):
            raise ValidationError(
                "Evento do lote DF-e deve informar XML e chave de acesso válida com 44 caracteres."
            )
        if not xml and not chave:
            raise ValidationError(
                "Documento resumido do lote DF-e deve informar uma chave de acesso válida com 44 caracteres."
            )
        item["tipo_documento"] = tipo_documento
        if chave:
            item["chave_acesso"] = chave
    try:
        aguardar_segundos = int(retorno.get("aguardar_segundos") or 0)
    except (TypeError, ValueError) as exc:
        raise ValidationError("O intervalo de espera do lote DF-e é inválido.") from exc
    if not 0 <= aguardar_segundos <= 86400:
        raise ValidationError("O intervalo de espera do lote DF-e deve ficar entre 0 e 86400 segundos.")
    return {
        "contrato": contrato,
        "documentos": documentos,
        "ultimo_nsu": ultimo_nsu,
        "max_nsu": max_nsu,
        "aguardar_segundos": aguardar_segundos,
        "mensagem": str(retorno.get("mensagem") or "").strip(),
    }
