from datetime import date
from decimal import Decimal, InvalidOperation

from .calculo import calcular_base_operacao_padrao, calcular_ibs_cbs_padrao
from .xml import reconciliar_xml


def _tag(namespace, nome):
    return f"{{{namespace}}}{nome}"


def _decimal(elemento, caminho, campo, *, obrigatorio=True):
    texto = elemento.findtext(caminho)
    if texto is None or not texto.strip():
        if obrigatorio:
            raise ValueError(f"XML IBS/CBS incompleto: {campo} ausente")
        return Decimal("0.00")
    try:
        valor = Decimal(texto)
    except InvalidOperation as exc:
        raise ValueError(f"XML IBS/CBS invalido: {campo} nao e decimal") from exc
    if not valor.is_finite():
        raise ValueError(f"XML IBS/CBS invalido: {campo} nao e finito")
    if valor < 0:
        raise ValueError(f"XML IBS/CBS invalido: {campo} nao pode ser negativo")
    return valor


def _validar_ausencias_contrato(item, imposto, *, namespace):
    prod = item.find(_tag(namespace, "prod"))
    if prod is None:
        raise ValueError("XML IBS/CBS incompleto: grupo prod ausente")
    for campo in ("vFrete", "vSeg", "vOutro"):
        if prod.find(_tag(namespace, campo)) is not None:
            raise ValueError(
                f"cenario IBS/CBS ainda nao suportado pelo contrato fiscal atual: {campo} no item"
            )
    for grupo in ("II", "ICMSUFDest", "ISSQN", "IS"):
        if imposto.find(_tag(namespace, grupo)) is not None:
            raise ValueError(
                f"cenario IBS/CBS ainda nao suportado pelo contrato fiscal atual: grupo {grupo}"
            )
    if any("mono" in elemento.tag.rsplit("}", 1)[-1].lower() for elemento in imposto.iter()):
        raise ValueError(
            "cenario IBS/CBS ainda nao suportado pelo contrato fiscal atual: ICMS monofasico"
        )


def validar_paridade_xml(inf_nfe, *, namespace, modelo, data_emissao):
    if not isinstance(data_emissao, date) or data_emissao.year != 2026:
        raise ValueError(
            "cenario IBS/CBS ainda nao suportado pelo contrato fiscal atual: "
            "aliquotas homologadas somente para 2026"
        )

    itens = inf_nfe.findall(_tag(namespace, "det"))
    for indice, item in enumerate(itens, start=1):
        imposto = item.find(_tag(namespace, "imposto"))
        grupo = (
            imposto.find(_tag(namespace, "IBSCBS"))
            if imposto is not None
            else None
        )
        if grupo is None:
            raise ValueError(f"XML IBS/CBS incompleto: item {indice} sem IBSCBS")
        _validar_ausencias_contrato(item, imposto, namespace=namespace)

        prod = item.find(_tag(namespace, "prod"))
        valor_produtos = _decimal(prod, _tag(namespace, "vProd"), "vProd")
        desconto = _decimal(
            prod, _tag(namespace, "vDesc"), "vDesc", obrigatorio=False
        )
        valor_pis = _decimal(
            imposto, f".//{_tag(namespace, 'vPIS')}", "vPIS", obrigatorio=False
        )
        valor_cofins = _decimal(
            imposto,
            f".//{_tag(namespace, 'vCOFINS')}",
            "vCOFINS",
            obrigatorio=False,
        )
        valor_icms = _decimal(
            imposto, f".//{_tag(namespace, 'vICMS')}", "vICMS", obrigatorio=False
        )
        valor_fcp = _decimal(
            imposto, f".//{_tag(namespace, 'vFCP')}", "vFCP", obrigatorio=False
        )
        base = calcular_base_operacao_padrao(
            valor_produtos=valor_produtos,
            desconto=desconto,
            valor_pis=valor_pis,
            valor_cofins=valor_cofins,
            valor_icms=valor_icms,
            valor_fcp=valor_fcp,
        )
        calculo = calcular_ibs_cbs_padrao(
            valor_operacao=base,
            cst=grupo.findtext(_tag(namespace, "CST")),
            cclass_trib=grupo.findtext(_tag(namespace, "cClassTrib")),
            modelo=modelo,
        )
        g_ibs_cbs = grupo.find(_tag(namespace, "gIBSCBS"))
        if g_ibs_cbs is None:
            raise ValueError(f"XML IBS/CBS incompleto: item {indice} sem gIBSCBS")

        campos = (
            ("vBC", _tag(namespace, "vBC"), calculo.base),
            (
                "pIBSUF",
                f"{_tag(namespace, 'gIBSUF')}/{_tag(namespace, 'pIBSUF')}",
                calculo.aliquota_ibs_uf,
            ),
            (
                "vIBSUF",
                f"{_tag(namespace, 'gIBSUF')}/{_tag(namespace, 'vIBSUF')}",
                calculo.valor_ibs_uf,
            ),
            (
                "pIBSMun",
                f"{_tag(namespace, 'gIBSMun')}/{_tag(namespace, 'pIBSMun')}",
                calculo.aliquota_ibs_municipio,
            ),
            (
                "vIBSMun",
                f"{_tag(namespace, 'gIBSMun')}/{_tag(namespace, 'vIBSMun')}",
                calculo.valor_ibs_municipio,
            ),
            ("vIBS", _tag(namespace, "vIBS"), calculo.valor_ibs),
            (
                "pCBS",
                f"{_tag(namespace, 'gCBS')}/{_tag(namespace, 'pCBS')}",
                calculo.aliquota_cbs,
            ),
            (
                "vCBS",
                f"{_tag(namespace, 'gCBS')}/{_tag(namespace, 'vCBS')}",
                calculo.valor_cbs,
            ),
        )
        for campo, caminho, esperado in campos:
            informado = _decimal(g_ibs_cbs, caminho, campo)
            if informado != esperado:
                raise ValueError(
                    f"Divergencia matematica IBS/CBS no item {indice}: "
                    f"{campo} informado {informado} difere de {esperado}"
                )

    reconciliar_xml(inf_nfe, namespace=namespace)
    return True
