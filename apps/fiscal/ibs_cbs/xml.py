from decimal import Decimal
from xml.etree import ElementTree as ET

from .calculo import totalizar_calculos
from .estrutura import ler_item_ibs_cbs, ler_total_ibs_cbs, obter_unico


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
    estruturas = []
    for indice, item in enumerate(itens, start=1):
        imposto = obter_unico(
            item,
            namespace=namespace,
            nome="imposto",
            contexto=f"item {indice} grupo imposto",
        )
        estruturas.append(
            ler_item_ibs_cbs(
                imposto,
                namespace=namespace,
                indice=indice,
                obrigatorio=False,
            )
        )
    if not any(estrutura is not None for estrutura in estruturas):
        return False
    if any(estrutura is None for estrutura in estruturas):
        raise ValueError("XML IBS/CBS incompleto: todos os itens devem possuir IBSCBS")
    total = ler_total_ibs_cbs(inf_nfe, namespace=namespace)

    def soma(campo):
        return sum(
            (Decimal(estrutura[campo]) for estrutura in estruturas),
            Decimal("0.00"),
        )

    comparacoes = (
        (soma("vBC"), "vBCIBSCBS"),
        (soma("vIBSUF"), "vIBSUF"),
        (soma("vIBSMun"), "vIBSMun"),
        (soma("vIBS"), "vIBS"),
        (soma("vCBS"), "vCBS"),
    )
    for soma_itens, nome in comparacoes:
        if soma_itens != Decimal(total[nome]):
            raise ValueError(f"SOMA_ITENS diverge de TOTAL_XML em {nome}")
    return True
