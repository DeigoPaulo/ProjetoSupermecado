"""Leitura segura e tolerante de XML fiscal para o pacote do contador.

Os dados são extraídos da evidência XML armazenada, e não do cadastro atual do
produto, para preservar o retrato tributário existente no momento da emissão.
"""

from datetime import date
from xml.etree import ElementTree as ET


def _local_name(elemento):
    return elemento.tag.rsplit("}", 1)[-1]


def _filho(elemento, nome):
    if elemento is None:
        return None
    return next((item for item in elemento if _local_name(item) == nome), None)


def _primeiro(elemento, nome):
    if elemento is None:
        return None
    return next((item for item in elemento.iter() if _local_name(item) == nome), None)


def _texto(elemento, nome):
    filho = _filho(elemento, nome)
    return (filho.text or "").strip() if filho is not None else ""


def _grupo_imposto(imposto, nome):
    grupo = _filho(imposto, nome)
    return next(iter(grupo), None) if grupo is not None else None


def _data_iso(valor):
    try:
        return date.fromisoformat((valor or "")[:10])
    except ValueError:
        return None


def analisar_xml_nfe(xml_conteudo):
    """Retorna cabeçalho e itens de NF-e/NFC-e sem alterar ou validar o XML."""
    resultado = {
        "data_emissao": None,
        "data_autorizacao": None,
        "modelo": "",
        "finalidade": "",
        "chave_acesso": "",
        "emitente_cnpj": "",
        "destinatario_cnpj": "",
        "itens": [],
        "erro": "",
    }
    if not (xml_conteudo or "").strip():
        resultado["erro"] = "XML ausente"
        return resultado
    try:
        raiz = ET.fromstring(xml_conteudo)
    except (ET.ParseError, ValueError) as exc:
        resultado["erro"] = f"XML inválido: {exc}"
        return resultado

    inf_nfe = raiz if _local_name(raiz) == "infNFe" else _primeiro(raiz, "infNFe")
    if inf_nfe is None:
        resultado["erro"] = "Elemento infNFe não encontrado"
        return resultado
    identificador = (inf_nfe.get("Id") or "").strip()
    resultado["chave_acesso"] = identificador[3:] if identificador.startswith("NFe") else identificador
    ide = _filho(inf_nfe, "ide")
    resultado["modelo"] = _texto(ide, "mod")
    resultado["finalidade"] = _texto(ide, "finNFe")
    resultado["data_emissao"] = _data_iso(_texto(ide, "dhEmi") or _texto(ide, "dEmi"))
    resultado["emitente_cnpj"] = _texto(_filho(inf_nfe, "emit"), "CNPJ")
    resultado["destinatario_cnpj"] = _texto(_filho(inf_nfe, "dest"), "CNPJ")
    inf_prot = _primeiro(raiz, "infProt")
    resultado["data_autorizacao"] = _data_iso(_texto(inf_prot, "dhRecbto"))

    for det in (item for item in inf_nfe if _local_name(item) == "det"):
        produto = _filho(det, "prod")
        imposto = _filho(det, "imposto")
        icms = _grupo_imposto(imposto, "ICMS")
        pis = _grupo_imposto(imposto, "PIS")
        cofins = _grupo_imposto(imposto, "COFINS")
        ipi = _filho(imposto, "IPI")
        ipi_tributo = _filho(ipi, "IPITrib")
        if ipi_tributo is None:
            ipi_tributo = _filho(ipi, "IPINT")
        resultado["itens"].append(
            {
                "numero_item": (det.get("nItem") or "").strip(),
                "codigo_produto": _texto(produto, "cProd"),
                "descricao": _texto(produto, "xProd"),
                "ncm": _texto(produto, "NCM"),
                "cest": _texto(produto, "CEST"),
                "cfop": _texto(produto, "CFOP"),
                "unidade": _texto(produto, "uCom"),
                "quantidade": _texto(produto, "qCom"),
                "valor_unitario": _texto(produto, "vUnCom"),
                "valor_produto": _texto(produto, "vProd"),
                "valor_desconto": _texto(produto, "vDesc"),
                "origem_icms": _texto(icms, "orig"),
                "cst_icms": _texto(icms, "CST"),
                "csosn": _texto(icms, "CSOSN"),
                "cbenef": _texto(icms, "cBenef") or _texto(produto, "cBenef"),
                "base_icms": _texto(icms, "vBC"),
                "aliquota_icms": _texto(icms, "pICMS"),
                "valor_icms": _texto(icms, "vICMS"),
                "reducao_base_icms": _texto(icms, "pRedBC"),
                "base_icms_st": _texto(icms, "vBCST"),
                "aliquota_icms_st": _texto(icms, "pICMSST"),
                "valor_icms_st": _texto(icms, "vICMSST"),
                "mva_st": _texto(icms, "pMVAST"),
                "base_fcp": _texto(icms, "vBCFCP"),
                "aliquota_fcp": _texto(icms, "pFCP"),
                "valor_fcp": _texto(icms, "vFCP"),
                "base_fcp_st": _texto(icms, "vBCFCPST"),
                "aliquota_fcp_st": _texto(icms, "pFCPST"),
                "valor_fcp_st": _texto(icms, "vFCPST"),
                "cst_pis": _texto(pis, "CST"),
                "base_pis": _texto(pis, "vBC"),
                "aliquota_pis": _texto(pis, "pPIS"),
                "valor_pis": _texto(pis, "vPIS"),
                "cst_cofins": _texto(cofins, "CST"),
                "base_cofins": _texto(cofins, "vBC"),
                "aliquota_cofins": _texto(cofins, "pCOFINS"),
                "valor_cofins": _texto(cofins, "vCOFINS"),
                "cst_ipi": _texto(ipi_tributo, "CST"),
                "base_ipi": _texto(ipi_tributo, "vBC"),
                "aliquota_ipi": _texto(ipi_tributo, "pIPI"),
                "valor_ipi": _texto(ipi_tributo, "vIPI"),
            }
        )
    return resultado


def data_competencia_documento(documento, analise=None):
    """Prioriza dhEmi/dEmi; mantém fallback explícito para legados sem XML completo."""
    analise = analise or analisar_xml_nfe(documento.xml_conteudo)
    if analise["data_emissao"]:
        return analise["data_emissao"], "XML_DHEMI"
    if documento.xml_gerado_em:
        return documento.xml_gerado_em.date(), "XML_GERADO_EM"
    return documento.criado_em.date(), "CRIADO_EM"

