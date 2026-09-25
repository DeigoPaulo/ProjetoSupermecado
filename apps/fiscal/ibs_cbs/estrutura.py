def tag(namespace, nome):
    return f"{{{namespace}}}{nome}"


def nome_local(elemento):
    return elemento.tag.rsplit("}", 1)[-1]


def obter_unico(
    pai,
    *,
    namespace,
    nome,
    contexto,
    obrigatorio=True,
):
    elementos = pai.findall(tag(namespace, nome)) if pai is not None else []
    if len(elementos) > 1:
        raise ValueError(f"XML IBS/CBS ambiguo: {contexto} duplicado")
    if not elementos:
        if obrigatorio:
            raise ValueError(f"XML IBS/CBS incompleto: {contexto} ausente")
        return None
    return elementos[0]


def texto_unico(
    pai,
    *,
    namespace,
    nome,
    contexto,
    obrigatorio=True,
):
    elemento = obter_unico(
        pai,
        namespace=namespace,
        nome=nome,
        contexto=contexto,
        obrigatorio=obrigatorio,
    )
    if elemento is None:
        return None
    texto = elemento.text
    if texto is None or not texto.strip():
        if obrigatorio:
            raise ValueError(f"XML IBS/CBS incompleto: {contexto} ausente")
        return None
    return texto


def ler_item_ibs_cbs(imposto, *, namespace, indice, obrigatorio=True):
    prefixo = f"item {indice}"
    ibs_cbs = obter_unico(
        imposto,
        namespace=namespace,
        nome="IBSCBS",
        contexto=f"{prefixo} IBSCBS",
        obrigatorio=obrigatorio,
    )
    if ibs_cbs is None:
        return None
    cst = texto_unico(
        ibs_cbs,
        namespace=namespace,
        nome="CST",
        contexto=f"{prefixo} IBSCBS/CST",
    )
    cclass_trib = texto_unico(
        ibs_cbs,
        namespace=namespace,
        nome="cClassTrib",
        contexto=f"{prefixo} IBSCBS/cClassTrib",
    )
    grupo = obter_unico(
        ibs_cbs,
        namespace=namespace,
        nome="gIBSCBS",
        contexto=f"{prefixo} IBSCBS/gIBSCBS",
    )
    g_ibs_uf = obter_unico(
        grupo,
        namespace=namespace,
        nome="gIBSUF",
        contexto=f"{prefixo} gIBSCBS/gIBSUF",
    )
    g_ibs_mun = obter_unico(
        grupo,
        namespace=namespace,
        nome="gIBSMun",
        contexto=f"{prefixo} gIBSCBS/gIBSMun",
    )
    g_cbs = obter_unico(
        grupo,
        namespace=namespace,
        nome="gCBS",
        contexto=f"{prefixo} gIBSCBS/gCBS",
    )
    campos = (
        (grupo, "vBC"),
        (g_ibs_uf, "pIBSUF"),
        (g_ibs_uf, "vIBSUF"),
        (g_ibs_mun, "pIBSMun"),
        (g_ibs_mun, "vIBSMun"),
        (grupo, "vIBS"),
        (g_cbs, "pCBS"),
        (g_cbs, "vCBS"),
    )
    textos = {
        nome: texto_unico(
            pai,
            namespace=namespace,
            nome=nome,
            contexto=f"{prefixo} IBS/CBS/{nome}",
        )
        for pai, nome in campos
    }
    return {
        "IBSCBS": ibs_cbs,
        "CST": cst,
        "cClassTrib": cclass_trib,
        "gIBSCBS": grupo,
        "gIBSUF": g_ibs_uf,
        "gIBSMun": g_ibs_mun,
        "gCBS": g_cbs,
        **textos,
    }


def ler_total_ibs_cbs(inf_nfe, *, namespace):
    total = obter_unico(
        inf_nfe,
        namespace=namespace,
        nome="total",
        contexto="grupo total",
    )
    ibs_cbs = obter_unico(
        total,
        namespace=namespace,
        nome="IBSCBSTot",
        contexto="total/IBSCBSTot",
    )
    g_ibs = obter_unico(
        ibs_cbs,
        namespace=namespace,
        nome="gIBS",
        contexto="IBSCBSTot/gIBS",
    )
    g_ibs_uf = obter_unico(
        g_ibs,
        namespace=namespace,
        nome="gIBSUF",
        contexto="IBSCBSTot/gIBS/gIBSUF",
    )
    g_ibs_mun = obter_unico(
        g_ibs,
        namespace=namespace,
        nome="gIBSMun",
        contexto="IBSCBSTot/gIBS/gIBSMun",
    )
    g_cbs = obter_unico(
        ibs_cbs,
        namespace=namespace,
        nome="gCBS",
        contexto="IBSCBSTot/gCBS",
    )
    campos = (
        (ibs_cbs, "vBCIBSCBS"),
        (g_ibs_uf, "vIBSUF"),
        (g_ibs_mun, "vIBSMun"),
        (g_ibs, "vIBS"),
        (g_cbs, "vCBS"),
    )
    textos = {
        nome: texto_unico(
            pai,
            namespace=namespace,
            nome=nome,
            contexto=f"total IBS/CBS/{nome}",
        )
        for pai, nome in campos
    }
    return {"IBSCBSTot": ibs_cbs, **textos}
