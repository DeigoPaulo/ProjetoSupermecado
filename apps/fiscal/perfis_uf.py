"""Perfis estaduais oficiais usados na pré-validação fiscal.

O catálogo não calcula tributação. Ele guarda parâmetros técnicos publicados
pelas UFs e valida regras objetivas antes da geração do documento.
"""

import re
from decimal import Decimal


PERFIS_FISCAIS_UF = {
    "GO": {
        "nome": "Goiás",
        "fonte": "Informe Técnico 2025.003 e IN 1.518/22-GSE",
        "endpoints_nfce": {
            "HOMOLOGACAO": {
                "qrcode": "https://nfewebhomolog.sefaz.go.gov.br/nfeweb/sites/nfce/danfeNFCe",
                "consulta": "https://nfewebhomolog.sefaz.go.gov.br/nfeweb/sites/nfce/danfeNFCe",
            },
            "PRODUCAO": {
                "qrcode": "https://nfeweb.sefaz.go.gov.br/nfeweb/sites/nfce/danfeNFCe",
                "consulta": "https://nfeweb.sefaz.go.gov.br/nfeweb/sites/nfce/danfeNFCe",
            },
        },
        "cbenef_pattern": r"^GO\d{6}$",
    },
}


def perfil_fiscal_uf(uf):
    return PERFIS_FISCAIS_UF.get((uf or "").strip().upper())


def endpoints_nfce_uf(uf, ambiente):
    perfil = perfil_fiscal_uf(uf)
    if not perfil:
        return None
    return perfil["endpoints_nfce"].get((ambiente or "").strip().upper())


def aplicar_endpoints_nfce_uf(cleaned_data):
    """Preenche endpoints conhecidos quando o formulário os recebe vazios."""
    filial = cleaned_data.get("filial")
    endpoints = endpoints_nfce_uf(getattr(filial, "uf", ""), cleaned_data.get("ambiente"))
    if not endpoints:
        return None
    if not (cleaned_data.get("url_qrcode_nfce") or "").strip():
        cleaned_data["url_qrcode_nfce"] = endpoints["qrcode"]
    if not (cleaned_data.get("url_consulta_nfce") or "").strip():
        cleaned_data["url_consulta_nfce"] = endpoints["consulta"]
    return perfil_fiscal_uf(filial.uf)


def pendencias_endpoints_nfce(filial, configuracao):
    qrcode = (configuracao.url_qrcode_nfce or "").strip()
    consulta = (configuracao.url_consulta_nfce or "").strip()
    endpoints = endpoints_nfce_uf(getattr(filial, "uf", ""), configuracao.ambiente)
    if not endpoints:
        if not qrcode or not consulta:
            return ["Informe as URLs oficiais do QR Code e da consulta NFC-e para a UF e o ambiente."]
        return []

    pendencias = []
    if qrcode != endpoints["qrcode"]:
        pendencias.append(
            f"URL oficial do QR Code NFC-e para {filial.uf}/{configuracao.get_ambiente_display()} "
            f"deve ser {endpoints['qrcode']}."
        )
    if consulta != endpoints["consulta"]:
        pendencias.append(
            f"URL oficial de consulta NFC-e para {filial.uf}/{configuracao.get_ambiente_display()} "
            f"deve ser {endpoints['consulta']}."
        )
    return pendencias


def pendencias_produto_por_uf(produto, ufs=None):
    ufs = {(uf or "").strip().upper() for uf in (ufs or []) if uf}
    pendencias = []
    if "GO" not in ufs:
        return pendencias

    cbenef = (produto.codigo_beneficio_fiscal or "").strip().upper()
    reducao = produto.reducao_base_icms or Decimal("0")
    if cbenef and not re.fullmatch(PERFIS_FISCAIS_UF["GO"]["cbenef_pattern"], cbenef):
        pendencias.append("cBenef de Goiás no formato GO + 6 dígitos")
    if reducao > 0 and not cbenef:
        pendencias.append("cBenef obrigatório em Goiás para redução de base do ICMS")
    return pendencias
