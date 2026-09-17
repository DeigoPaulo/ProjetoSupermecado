"""Normalizacao do documento no snapshot fiscal do pedido online."""

from django.core.exceptions import ValidationError

from apps.fiscal.estrategia_normalizacao_cnpj import (
    canonicalizar_cnpj,
    validar_dv_cnpj,
)
from apps.vendas.models import TipoDocumentoConsumidor


def _somente_digitos(valor):
    return "".join(caractere for caractere in str(valor or "") if caractere.isdigit())


def _cpf_valido(valor):
    cpf = _somente_digitos(valor)
    if len(cpf) != 11 or len(set(cpf)) == 1:
        return False
    numeros = [int(digito) for digito in cpf]
    for tamanho in (9, 10):
        soma = sum(
            numeros[indice] * (tamanho + 1 - indice)
            for indice in range(tamanho)
        )
        digito = (soma * 10) % 11
        if digito == 10:
            digito = 0
        if numeros[tamanho] != digito:
            return False
    return True


def _normalizar_cnpj(valor):
    try:
        cnpj = canonicalizar_cnpj(str(valor or ""))
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    if not cnpj or not validar_dv_cnpj(cnpj):
        raise ValidationError("Informe um CNPJ válido para o destinatário da NF-e.")
    return cnpj


def normalizar_documento_cliente(tipo, valor, *, inferir=False):
    """Preserva o tipo explícito e só infere identidades efetivamente válidas."""
    tipo = str(tipo or TipoDocumentoConsumidor.NAO_IDENTIFICADO).upper()
    original = str(valor or "").strip()
    if not original:
        return TipoDocumentoConsumidor.NAO_IDENTIFICADO, ""

    if tipo == TipoDocumentoConsumidor.CPF:
        cpf = _somente_digitos(original)
        if not _cpf_valido(cpf):
            raise ValidationError("Informe um CPF válido para o destinatário da NF-e.")
        return tipo, cpf
    if tipo == TipoDocumentoConsumidor.CNPJ:
        return tipo, _normalizar_cnpj(original)
    if tipo == TipoDocumentoConsumidor.ESTRANGEIRO:
        return tipo, original[:20]
    if not inferir:
        return TipoDocumentoConsumidor.NAO_IDENTIFICADO, original

    cpf = _somente_digitos(original)
    if _cpf_valido(cpf):
        return TipoDocumentoConsumidor.CPF, cpf
    try:
        cnpj = _normalizar_cnpj(original)
    except ValidationError:
        return TipoDocumentoConsumidor.NAO_IDENTIFICADO, original
    return TipoDocumentoConsumidor.CNPJ, cnpj
