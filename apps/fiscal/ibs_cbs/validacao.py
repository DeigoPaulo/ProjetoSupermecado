from datetime import date
from decimal import Decimal, InvalidOperation

from .calculo import calcular_base_operacao_padrao, calcular_ibs_cbs_padrao
from .estrutura import ler_item_ibs_cbs, nome_local, obter_unico, texto_unico
from .xml import reconciliar_xml


def _tag(namespace, nome):
    return f"{{{namespace}}}{nome}"


def _decimal_texto(texto, campo, *, obrigatorio=True):
    if texto is None:
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


def _decimal_unico(
    pai, nome, campo, *, namespace, obrigatorio=True, permitido=True
):
    texto = texto_unico(
        pai,
        namespace=namespace,
        nome=nome,
        contexto=campo,
        obrigatorio=obrigatorio,
    )
    if texto is not None and not permitido:
        raise ValueError(f"XML IBS/CBS ambiguo: {campo} incompativel com a variante")
    return _decimal_texto(texto, campo, obrigatorio=obrigatorio)


def _grupo_variante_unico(container, *, grupo, permitidos, indice):
    variantes = list(container)
    contexto = f"item {indice} {grupo}"
    if not variantes:
        raise ValueError(f"XML IBS/CBS incompleto: {contexto} sem variante")
    if len(variantes) > 1:
        nomes = ", ".join(nome_local(elemento) for elemento in variantes)
        raise ValueError(
            f"XML IBS/CBS ambiguo: {contexto} possui variantes simultaneas ({nomes})"
        )
    variante = variantes[0]
    nome = nome_local(variante)
    if nome not in permitidos:
        raise ValueError(
            "cenario IBS/CBS ainda nao suportado pelo contrato fiscal atual: "
            f"variante {nome} em {grupo}"
        )
    return variante, nome


def _validar_grupos_legados(imposto, *, namespace, indice):
    icms = obter_unico(
        imposto,
        namespace=namespace,
        nome="ICMS",
        contexto=f"item {indice} grupo ICMS",
    )
    variante_icms, nome_icms = _grupo_variante_unico(
        icms,
        grupo="ICMS",
        permitidos={"ICMS00", "ICMS20", "ICMS40"},
        indice=indice,
    )
    valor_icms = _decimal_unico(
        variante_icms,
        "vICMS",
        f"item {indice} ICMS/{nome_icms}/vICMS",
        namespace=namespace,
        obrigatorio=nome_icms in {"ICMS00", "ICMS20"},
        permitido=nome_icms in {"ICMS00", "ICMS20"},
    )
    valor_fcp = _decimal_unico(
        variante_icms,
        "vFCP",
        f"item {indice} ICMS/{nome_icms}/vFCP",
        namespace=namespace,
        obrigatorio=False,
        permitido=nome_icms in {"ICMS00", "ICMS20"},
    )

    valores = {"ICMS": valor_icms, "FCP": valor_fcp}
    for grupo in ("PIS", "COFINS"):
        container = obter_unico(
            imposto,
            namespace=namespace,
            nome=grupo,
            contexto=f"item {indice} grupo {grupo}",
        )
        permitidos = {f"{grupo}Aliq", f"{grupo}NT", f"{grupo}Outr"}
        variante, nome_variante = _grupo_variante_unico(
            container,
            grupo=grupo,
            permitidos=permitidos,
            indice=indice,
        )
        campo = f"v{grupo}"
        valores[grupo] = _decimal_unico(
            variante,
            campo,
            f"item {indice} {grupo}/{nome_variante}/{campo}",
            namespace=namespace,
            obrigatorio=nome_variante != f"{grupo}NT",
            permitido=nome_variante != f"{grupo}NT",
        )
    return valores


def _validar_ausencias_contrato(item, imposto, *, namespace):
    prod = item.find(_tag(namespace, "prod"))
    if prod is None:
        raise ValueError("XML IBS/CBS incompleto: grupo prod ausente")
    for campo in ("vFrete", "vSeg", "vOutro"):
        if prod.find(_tag(namespace, campo)) is not None:
            raise ValueError(
                f"cenario IBS/CBS ainda nao suportado pelo contrato fiscal atual: {campo} no item"
            )
    for grupo in ("II", "ICMSUFDest", "ISSQN", "IS", "PISST", "COFINSST"):
        if imposto.find(_tag(namespace, grupo)) is not None:
            raise ValueError(
                f"cenario IBS/CBS ainda nao suportado pelo contrato fiscal atual: grupo {grupo}"
            )
    for elemento in imposto.iter():
        nome = nome_local(elemento)
        if nome in {"vFCPUFDest", "vICMSUFDest"}:
            raise ValueError(
                f"cenario IBS/CBS ainda nao suportado pelo contrato fiscal atual: {nome}"
            )
        if "mono" in nome.lower():
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
        imposto = obter_unico(
            item,
            namespace=namespace,
            nome="imposto",
            contexto=f"item {indice} grupo imposto",
        )
        estrutura = ler_item_ibs_cbs(
            imposto, namespace=namespace, indice=indice
        )
        _validar_ausencias_contrato(item, imposto, namespace=namespace)

        cst = estrutura["CST"]
        cclass_trib = estrutura["cClassTrib"]
        prod = obter_unico(
            item,
            namespace=namespace,
            nome="prod",
            contexto=f"item {indice} grupo prod",
        )
        valor_produtos = _decimal_unico(
            prod,
            "vProd",
            f"item {indice} prod/vProd",
            namespace=namespace,
        )
        desconto = _decimal_unico(
            prod,
            "vDesc",
            f"item {indice} prod/vDesc",
            namespace=namespace,
            obrigatorio=False,
        )
        legados = _validar_grupos_legados(
            imposto, namespace=namespace, indice=indice
        )
        base = calcular_base_operacao_padrao(
            valor_produtos=valor_produtos,
            desconto=desconto,
            valor_pis=legados["PIS"],
            valor_cofins=legados["COFINS"],
            valor_icms=legados["ICMS"],
            valor_fcp=legados["FCP"],
        )
        calculo = calcular_ibs_cbs_padrao(
            valor_operacao=base,
            cst=cst,
            cclass_trib=cclass_trib,
            modelo=modelo,
        )

        campos = (
            ("vBC", calculo.base),
            ("pIBSUF", calculo.aliquota_ibs_uf),
            ("vIBSUF", calculo.valor_ibs_uf),
            ("pIBSMun", calculo.aliquota_ibs_municipio),
            ("vIBSMun", calculo.valor_ibs_municipio),
            ("vIBS", calculo.valor_ibs),
            ("pCBS", calculo.aliquota_cbs),
            ("vCBS", calculo.valor_cbs),
        )
        for campo, esperado in campos:
            informado = _decimal_texto(
                estrutura[campo], f"item {indice} IBS/CBS/{campo}"
            )
            if informado != esperado:
                raise ValueError(
                    f"Divergencia matematica IBS/CBS no item {indice}: "
                    f"{campo} informado {informado} difere de {esperado}"
                )

    reconciliar_xml(inf_nfe, namespace=namespace)
    return True
