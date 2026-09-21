"""Perfis estaduais oficiais usados na pré-validação fiscal.

O catálogo não calcula tributação. Ele guarda parâmetros técnicos publicados
pelas UFs e valida regras objetivas antes da geração do documento.
"""

from decimal import Decimal

from .cbenef import validar_cbenef_go


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


def parametrizacao_beneficio_produto(produto, natureza_operacao):
    if not natureza_operacao or not getattr(produto, "pk", None):
        return None
    return produto.parametrizacoes_beneficio_fiscal.filter(natureza_operacao=natureza_operacao).first()


def codigo_beneficio_produto_operacao(produto, natureza_operacao, *, uf="", crt=""):
    """Resolve o cBenef pela mesma regra usada na validacao e na geracao do XML.

    Em GO, nos regimes normal e excesso de sublimite, a decisao por natureza e
    obrigatoria. Fora desse recorte, o campo legado continua sendo respeitado
    ate que a transicao cadastral seja concluida.
    """
    exige_decisao_por_operacao = (uf or "").strip().upper() == "GO" and str(crt) in {"2", "3"}
    if exige_decisao_por_operacao:
        parametrizacao = parametrizacao_beneficio_produto(produto, natureza_operacao)
        if not parametrizacao or parametrizacao.situacao == "INDEFINIDO":
            return ""
        return (parametrizacao.codigo_beneficio_fiscal or "").strip().upper()
    return (produto.codigo_beneficio_fiscal or "").strip().upper()


def pendencias_produto_por_uf(produto, ufs=None, crts=None, data_referencia=None, natureza_operacao=None):
    ufs = {(uf or "").strip().upper() for uf in (ufs or []) if uf}
    pendencias = []
    if "GO" not in ufs:
        return pendencias

    crts = {str(crt) for crt in (crts or []) if crt}
    exige_regime_normal = not crts or bool(crts & {"2", "3"})
    parametrizacao = parametrizacao_beneficio_produto(produto, natureza_operacao)
    if natureza_operacao and exige_regime_normal:
        if not parametrizacao or parametrizacao.situacao == "INDEFINIDO":
            pendencias.append("defina se há benefício fiscal de ICMS para o produto nesta natureza de operação")
            return pendencias
        cbenef = codigo_beneficio_produto_operacao(
            produto,
            natureza_operacao,
            uf="GO",
            crt="3",
        )
        if parametrizacao.situacao == "COM_BENEFICIO" and not cbenef:
            pendencias.append("cBenef obrigatório para a decisão com benefício fiscal")
        if parametrizacao.situacao == "SEM_BENEFICIO" and cbenef not in {"", "SEM CBENEF"}:
            pendencias.append("decisão sem benefício não pode utilizar um cBenef de benefício")
    else:
        cbenef = codigo_beneficio_produto_operacao(produto, natureza_operacao)
    reducao = produto.reducao_base_icms or Decimal("0")
    if reducao > 0 and not cbenef and exige_regime_normal:
        pendencias.append("cBenef obrigatório em Goiás para redução de base do ICMS")
    if cbenef:
        pendencia_catalogo = validar_cbenef_go(
            cbenef,
            produto.cst_icms if exige_regime_normal else None,
            data_referencia,
        )
        if pendencia_catalogo:
            pendencias.append(pendencia_catalogo)
    return pendencias
