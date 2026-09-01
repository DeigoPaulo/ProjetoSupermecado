"""Catálogo versionado da Nomenclatura Comum do Mercosul (NCM)."""

import html
import json
import re
from datetime import date, datetime
from pathlib import Path

from django.db import models
from django.utils import timezone

from .cbenef import sha256_arquivo


FONTE_NCM_OFICIAL = (
    "https://portalunico.siscomex.gov.br/classif/api/publico/"
    "nomenclatura/download/json"
)


def _data_br(valor):
    try:
        return datetime.strptime(str(valor or ""), "%d/%m/%Y").date()
    except ValueError as exc:
        raise ValueError(f"Data inválida na tabela NCM: {valor!r}.") from exc


def _texto_plano(valor):
    valor = html.unescape(str(valor or ""))
    return " ".join(re.sub(r"<[^>]+>", "", valor).split())


def ler_catalogo_ncm_json(caminho):
    """Lê o JSON oficial e devolve apenas códigos finais de oito dígitos."""
    caminho = Path(caminho)
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Arquivo não é um JSON NCM válido em UTF-8.") from exc

    if not isinstance(dados, dict) or not isinstance(dados.get("Nomenclaturas"), list):
        raise ValueError("JSON NCM sem a lista oficial Nomenclaturas.")
    referencia_match = re.search(
        r"(\d{2}/\d{2}/\d{4})",
        str(dados.get("Data_Ultima_Atualizacao_NCM") or ""),
    )
    if not referencia_match:
        raise ValueError("JSON NCM sem data oficial de referência.")
    referencia_em = _data_br(referencia_match.group(1))
    ato = _texto_plano(dados.get("Ato"))
    if not ato:
        raise ValueError("JSON NCM sem ato normativo.")

    itens = {}
    for linha in dados["Nomenclaturas"]:
        if not isinstance(linha, dict):
            raise ValueError("JSON NCM contém linha em formato inválido.")
        codigo_formatado = str(linha.get("Codigo") or "").strip()
        codigo = re.sub(r"\D", "", codigo_formatado)
        if not re.fullmatch(r"\d{8}", codigo):
            continue
        if codigo in itens:
            raise ValueError(f"JSON NCM contém código final duplicado: {codigo}.")
        descricao = _texto_plano(linha.get("Descricao"))
        if not descricao:
            raise ValueError(f"NCM {codigo} sem descrição.")
        inicio = _data_br(linha.get("Data_Inicio"))
        fim = _data_br(linha.get("Data_Fim"))
        if fim < inicio:
            raise ValueError(f"NCM {codigo} possui vigência final anterior à inicial.")
        ato_inicio = " ".join(
            parte
            for parte in [
                _texto_plano(linha.get("Tipo_Ato_Ini")),
                _texto_plano(linha.get("Numero_Ato_Ini")),
                _texto_plano(linha.get("Ano_Ato_Ini")),
            ]
            if parte
        )
        itens[codigo] = {
            "codigo": codigo,
            "codigo_formatado": codigo_formatado,
            "descricao": descricao,
            "vigencia_inicio": inicio,
            "vigencia_fim": fim,
            "ato_inicio": ato_inicio,
        }

    if not itens:
        raise ValueError("Nenhum código NCM final de oito dígitos foi encontrado.")
    return {
        "referencia_em": referencia_em,
        "ato": ato,
        "itens": list(itens.values()),
        "quantidade_linhas_origem": len(dados["Nomenclaturas"]),
    }


def catalogo_ncm_vigente(data_referencia=None):
    from .models import CatalogoNCM

    data_referencia = data_referencia or timezone.localdate()
    if isinstance(data_referencia, str):
        data_referencia = date.fromisoformat(data_referencia)
    return (
        CatalogoNCM.objects.filter(ativo=True, referencia_em__lte=data_referencia)
        .order_by("-referencia_em", "-importado_em")
        .first()
    )


def queryset_codigos_ncm_vigentes(data_referencia=None):
    from .models import ItemNCM

    data_referencia = data_referencia or timezone.localdate()
    catalogo = catalogo_ncm_vigente(data_referencia)
    if not catalogo:
        return None
    return ItemNCM.objects.filter(
        catalogo=catalogo,
        vigencia_inicio__lte=data_referencia,
        vigencia_fim__gte=data_referencia,
    ).values("codigo")


def validar_ncm(codigo, data_referencia=None):
    """Valida formato e, quando instalado, o snapshot oficial ativo."""
    codigo = re.sub(r"\D", "", str(codigo or ""))
    if not re.fullmatch(r"\d{8}", codigo):
        return "NCM com 8 dígitos"
    catalogo = catalogo_ncm_vigente(data_referencia)
    if not catalogo:
        return None
    data_referencia = data_referencia or timezone.localdate()
    if not catalogo.itens.filter(
        codigo=codigo,
        vigencia_inicio__lte=data_referencia,
        vigencia_fim__gte=data_referencia,
    ).exists():
        return f"NCM {codigo} não consta no catálogo oficial vigente"
    return None
