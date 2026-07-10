from __future__ import annotations

from decimal import Decimal, InvalidOperation
import os


class ErroBalanca(Exception):
    pass


def normalizar_configuracao_balanca(configuracao: dict | None) -> dict:
    configuracao = configuracao or {}
    leitura_automatica = bool(configuracao.get("leitura_automatica"))
    return {
        "contrato": configuracao.get("contrato") or "pdv_scale_v1",
        "opcional": bool(configuracao.get("opcional", True)),
        "habilitada": bool(configuracao.get("habilitada")),
        "protocolo": configuracao.get("protocolo") or "NAO_CONFIGURADO",
        "porta": configuracao.get("porta") or "",
        "modelo": configuracao.get("modelo") or "",
        "leitura_automatica": leitura_automatica,
        "unidade_padrao": configuracao.get("unidade_padrao") or "KG",
        "precisao_decimal": int(configuracao.get("precisao_decimal") or 3),
        "timeout_ms": int(configuracao.get("timeout_ms") or 3000),
        "fallback_manual": bool(configuracao.get("fallback_manual", True)),
        "status_operacional": configuracao.get("status_operacional") or ("habilitada" if leitura_automatica else "manual"),
    }


def _peso_simulado():
    valor = os.environ.get("SUPERMERCADO_PDV_PESO_SIMULADO", "").strip()
    if not valor:
        return None
    try:
        peso = Decimal(valor.replace(",", "."))
    except InvalidOperation as exc:
        raise ErroBalanca("Peso simulado invalido.") from exc
    if peso <= 0:
        raise ErroBalanca("Peso simulado deve ser maior que zero.")
    return peso


def ler_peso_balanca(configuracao: dict | None) -> dict:
    config = normalizar_configuracao_balanca(configuracao)
    if not config["habilitada"]:
        return {
            "status": "manual",
            "mensagem": "Balanca desabilitada para este terminal.",
            "fallback_manual": config["fallback_manual"],
            "unidade": config["unidade_padrao"],
        }
    if not config["leitura_automatica"]:
        return {
            "status": "manual",
            "mensagem": "Balanca sem protocolo automatico configurado.",
            "fallback_manual": config["fallback_manual"],
            "unidade": config["unidade_padrao"],
        }

    peso = _peso_simulado()
    if peso is None:
        return {
            "status": "erro",
            "mensagem": "Driver fisico da balanca ainda nao conectado neste app desktop.",
            "fallback_manual": config["fallback_manual"],
            "unidade": config["unidade_padrao"],
            "protocolo": config["protocolo"],
            "porta": config["porta"],
        }

    casas = config["precisao_decimal"]
    return {
        "status": "ok",
        "peso": f"{peso:.{casas}f}",
        "unidade": config["unidade_padrao"],
        "protocolo": config["protocolo"],
        "porta": config["porta"],
        "simulado": True,
    }
