from decimal import Decimal
from xml.etree import ElementTree as ET

from .calculo import totalizar_calculos


def _tag(namespace, nome):
    return f"{{{namespace}}}{nome}"


def _texto(parent, namespace, nome, valor):
    elemento = ET.SubElement(parent, _tag(namespace, nome))
    elemento.text = str(valor)
    return elemento


def _dinheiro(valor):
    return f"{valor:.2f}"


def _aliquota(valor):
    return f"{valor:.4f}"


def adicionar_grupo_item(imposto, calculo, *, namespace):
    ibs_cbs = ET.SubElement(imposto, _tag(namespace, "IBSCBS"))
    _texto(ibs_cbs, namespace, "CST", calculo.cst)
    _texto(ibs_cbs, namespace, "cClassTrib", calculo.cclass_trib)
    grupo = ET.SubElement(ibs_cbs, _tag(namespace, "gIBSCBS"))
    _texto(grupo, namespace, "vBC", _dinheiro(calculo.base))
    ibs_uf = ET.SubElement(grupo, _tag(namespace, "gIBSUF"))
    _texto(ibs_uf, namespace, "pIBSUF", _aliquota(calculo.aliquota_ibs_uf))
    _texto(ibs_uf, namespace, "vIBSUF", _dinheiro(calculo.valor_ibs_uf))
    ibs_mun = ET.SubElement(grupo, _tag(namespace, "gIBSMun"))
    _texto(ibs_mun, namespace, "pIBSMun", _aliquota(calculo.aliquota_ibs_municipio))
    _texto(ibs_mun, namespace, "vIBSMun", _dinheiro(calculo.valor_ibs_municipio))
    _texto(grupo, namespace, "vIBS", _dinheiro(calculo.valor_ibs))
    cbs = ET.SubElement(grupo, _tag(namespace, "gCBS"))
    _texto(cbs, namespace, "pCBS", _aliquota(calculo.aliquota_cbs))
    _texto(cbs, namespace, "vCBS", _dinheiro(calculo.valor_cbs))
    return ibs_cbs


def adicionar_totais(total, calculos, *, namespace):
    totais = totalizar_calculos(calculos)
    ibs_cbs = ET.SubElement(total, _tag(namespace, "IBSCBSTot"))
    _texto(ibs_cbs, namespace, "vBCIBSCBS", _dinheiro(totais["base"]))
    ibs = ET.SubElement(ibs_cbs, _tag(namespace, "gIBS"))
    ibs_uf = ET.SubElement(ibs, _tag(namespace, "gIBSUF"))
    _texto(ibs_uf, namespace, "vDif", "0.00")
    _texto(ibs_uf, namespace, "vDevTrib", "0.00")
    _texto(ibs_uf, namespace, "vIBSUF", _dinheiro(totais["valor_ibs_uf"]))
    ibs_mun = ET.SubElement(ibs, _tag(namespace, "gIBSMun"))
    _texto(ibs_mun, namespace, "vDif", "0.00")
    _texto(ibs_mun, namespace, "vDevTrib", "0.00")
    _texto(ibs_mun, namespace, "vIBSMun", _dinheiro(totais["valor_ibs_municipio"]))
    _texto(ibs, namespace, "vIBS", _dinheiro(totais["valor_ibs"]))
    _texto(ibs, namespace, "vCredPres", "0.00")
    _texto(ibs, namespace, "vCredPresCondSus", "0.00")
    cbs = ET.SubElement(ibs_cbs, _tag(namespace, "gCBS"))
    _texto(cbs, namespace, "vDif", "0.00")
    _texto(cbs, namespace, "vDevTrib", "0.00")
    _texto(cbs, namespace, "vCBS", _dinheiro(totais["valor_cbs"]))
    _texto(cbs, namespace, "vCredPres", "0.00")
    _texto(cbs, namespace, "vCredPresCondSus", "0.00")
    return totais


def reconciliar_xml(inf_nfe, *, namespace):
    caminho = lambda valor: f".//{{{namespace}}}{valor}"
    itens = inf_nfe.findall(caminho("det"))
    grupos = [item.find(f"{{{namespace}}}imposto/{{{namespace}}}IBSCBS") for item in itens]
    if not any(grupo is not None for grupo in grupos):
        return False
    if any(grupo is None for grupo in grupos):
        raise ValueError("XML IBS/CBS incompleto: todos os itens devem possuir IBSCBS")
    total = inf_nfe.find(f"{{{namespace}}}total/{{{namespace}}}IBSCBSTot")
    if total is None:
        raise ValueError("XML IBS/CBS incompleto: IBSCBSTot ausente")

    def soma(caminho_relativo):
        return sum(
            (Decimal(grupo.findtext(caminho_relativo, "0")) for grupo in grupos),
            Decimal("0.00"),
        )

    comparacoes = (
        (soma(f"{{{namespace}}}gIBSCBS/{{{namespace}}}vBC"), "vBCIBSCBS"),
        (soma(f"{{{namespace}}}gIBSCBS/{{{namespace}}}gIBSUF/{{{namespace}}}vIBSUF"), "gIBS/vIBSUF"),
        (soma(f"{{{namespace}}}gIBSCBS/{{{namespace}}}gIBSMun/{{{namespace}}}vIBSMun"), "gIBS/vIBSMun"),
        (soma(f"{{{namespace}}}gIBSCBS/{{{namespace}}}vIBS"), "gIBS/vIBS"),
        (soma(f"{{{namespace}}}gIBSCBS/{{{namespace}}}gCBS/{{{namespace}}}vCBS"), "gCBS/vCBS"),
    )
    caminhos_total = {
        "vBCIBSCBS": f"{{{namespace}}}vBCIBSCBS",
        "gIBS/vIBSUF": f"{{{namespace}}}gIBS/{{{namespace}}}gIBSUF/{{{namespace}}}vIBSUF",
        "gIBS/vIBSMun": f"{{{namespace}}}gIBS/{{{namespace}}}gIBSMun/{{{namespace}}}vIBSMun",
        "gIBS/vIBS": f"{{{namespace}}}gIBS/{{{namespace}}}vIBS",
        "gCBS/vCBS": f"{{{namespace}}}gCBS/{{{namespace}}}vCBS",
    }
    for soma_itens, nome in comparacoes:
        if soma_itens != Decimal(total.findtext(caminhos_total[nome], "0")):
            raise ValueError(f"SOMA_ITENS diverge de TOTAL_XML em {nome}")
    return True
