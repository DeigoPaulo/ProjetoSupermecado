"""Política única de compatibilidade entre canal fiscal, UF e operação."""

from django.core.exceptions import ValidationError


CANAL_PILOTO_GO = "SEFAZ_DIRETA_GO"
OPERACOES_FISCAIS_CANONICAS = (
    "AUTORIZACAO", "CONSULTA", "REJEICAO", "CANCELAMENTO",
    "INUTILIZACAO", "EVENTOS", "DFE",
)


def diagnosticar_compatibilidade_canal_uf(canal, uf):
    canal = str(canal or "").strip().upper()
    uf = str(uf or "").strip().upper()
    valido = canal != CANAL_PILOTO_GO or uf == "GO"
    return {
        "contrato": "fiscal_channel_state_compatibility_v1",
        "canal": canal, "uf": uf, "valido": valido,
        "motivo": "" if valido else "A conexão direta SEFAZ está disponível somente para filiais de Goiás.",
    }


def validar_compatibilidade_canal_uf(canal, uf):
    diagnostico = diagnosticar_compatibilidade_canal_uf(canal, uf)
    if not diagnostico["valido"]:
        raise ValidationError(diagnostico["motivo"])
    return diagnostico
