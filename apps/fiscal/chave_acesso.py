"""Formação e validação central da chave NF-e/NFC-e, sem serializar XML."""

import re

from .estrategia_normalizacao_cnpj import (
    calcular_dv_chave_acesso,
    canonicalizar_cnpj,
    validar_chave_acesso,
)


CONTRATO_CHAVE_ACESSO = "fiscal_access_key_alphanumeric_v1"


def _campo_numerico(nome, valor, tamanho):
    texto = str(valor or "").strip()
    if not re.fullmatch(rf"[0-9]{{{tamanho}}}", texto):
        raise ValueError(f"{nome} deve possuir {tamanho} dígitos.")
    return texto


def construir_chave_acesso(
    *,
    codigo_uf,
    aamm,
    cnpj_emitente,
    modelo,
    serie,
    numero,
    tipo_emissao,
    codigo_numerico,
):
    cnpj = canonicalizar_cnpj(str(cnpj_emitente or ""))
    if not cnpj:
        raise ValueError("CNPJ do emitente é obrigatório para formar a chave fiscal.")
    base = "".join((
        _campo_numerico("Código da UF", codigo_uf, 2),
        _campo_numerico("Ano e mês", aamm, 4),
        cnpj,
        _campo_numerico("Modelo", modelo, 2),
        _campo_numerico("Série", serie, 3),
        _campo_numerico("Número", numero, 9),
        _campo_numerico("Tipo de emissão", tipo_emissao, 1),
        _campo_numerico("Código numérico", codigo_numerico, 8),
    ))
    chave = base + calcular_dv_chave_acesso(base)
    if not validar_chave_acesso(chave):
        raise ValueError("A chave fiscal formada não passou na validação central.")
    return chave


def normalizar_chave_acesso(valor):
    if not isinstance(valor, str):
        return ""
    chave = valor.strip().upper()
    return chave if validar_chave_acesso(chave) else ""
