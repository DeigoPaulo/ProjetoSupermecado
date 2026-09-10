"""Contrato de separação entre textos internos e observações fiscais da devolução."""


CONTRATO_OBSERVACOES = "supplier_return_fiscal_notes_policy_v1"
CONTRATO_VALIDACAO_OBSERVACOES = "supplier_return_fiscal_notes_policy_validation_v1"
_CAMPOS_FONTES = {
    "parecer_id", "parecer_sha256", "parametrizacao_id", "parametrizacao_sha256",
    "memoria_id", "memoria_sha256", "revisao_memoria_sha256",
}
_CAMPOS_INVENTARIO = {
    "motivo_operacional_presente", "fundamentacao_parecer_presente",
    "observacoes_parametros", "observacoes_memoria", "observacao_transporte_presente",
}
_CAMPOS_POLITICA = {
    "classificacao_interna_obrigatoria", "exportacao_automatica",
    "exige_texto_fiscal_aprovado",
}


def validar_observacoes_fiscais_devolucao(conteudo):
    erros = []
    pendencias = []

    def erro(caminho, codigo):
        erros.append({"caminho": caminho, "codigo": codigo})

    def pendencia(caminho, codigo):
        pendencias.append({"caminho": caminho, "codigo": codigo})

    if not isinstance(conteudo, dict):
        erro("$", "OBJETO_OBRIGATORIO")
        conteudo = {}
    campos = {
        "contrato", "operacao", "permite_emissao", "origem_aprovada", "fontes",
        "inventario_interno", "textos_fiscais", "politica",
    }
    if set(conteudo) != campos:
        erro("$", "CAMPOS_INVALIDOS")
    if conteudo.get("contrato") != CONTRATO_OBSERVACOES:
        erro("contrato", "VALOR_NAO_SUPORTADO")
    if conteudo.get("operacao") != "DEVOLUCAO_COMPRA":
        erro("operacao", "VALOR_NAO_SUPORTADO")
    if conteudo.get("permite_emissao") is not False:
        erro("permite_emissao", "EMISSAO_PROIBIDA")
    if conteudo.get("origem_aprovada") is not True:
        pendencia("origem_aprovada", "CADEIA_FINAL_APROVADA_PENDENTE")

    fontes = conteudo.get("fontes")
    if not isinstance(fontes, dict) or set(fontes) != _CAMPOS_FONTES:
        erro("fontes", "CAMPOS_INVALIDOS")
        fontes = {}
    for campo in ("parecer_id", "parametrizacao_id", "memoria_id"):
        if type(fontes.get(campo)) is not int or fontes.get(campo, 0) <= 0:
            pendencia(f"fontes.{campo}", "IDENTIFICADOR_ORIGEM_PENDENTE")
    for campo in (
        "parecer_sha256", "parametrizacao_sha256", "memoria_sha256",
        "revisao_memoria_sha256",
    ):
        valor = fontes.get(campo)
        if not isinstance(valor, str) or len(valor) != 64 or any(c not in "0123456789abcdef" for c in valor):
            pendencia(f"fontes.{campo}", "HASH_ORIGEM_PENDENTE")

    inventario = conteudo.get("inventario_interno")
    if not isinstance(inventario, dict) or set(inventario) != _CAMPOS_INVENTARIO:
        erro("inventario_interno", "CAMPOS_INVALIDOS")
        inventario = {}
    for campo in (
        "motivo_operacional_presente", "fundamentacao_parecer_presente",
        "observacao_transporte_presente",
    ):
        if type(inventario.get(campo)) is not bool:
            erro(f"inventario_interno.{campo}", "BOOLEANO_OBRIGATORIO")
    for campo in ("observacoes_parametros", "observacoes_memoria"):
        if type(inventario.get(campo)) is not int or inventario.get(campo, -1) < 0:
            erro(f"inventario_interno.{campo}", "CONTAGEM_INVALIDA")

    textos = conteudo.get("textos_fiscais")
    if not isinstance(textos, dict) or set(textos) != {"infadic", "itens"}:
        erro("textos_fiscais", "CAMPOS_INVALIDOS")
        textos = {}
    if textos.get("infadic") != "":
        erro("textos_fiscais.infadic", "TEXTO_FISCAL_NAO_APROVADO")
    itens = textos.get("itens")
    if not isinstance(itens, list) or not itens:
        erro("textos_fiscais.itens", "LISTA_NAO_VAZIA_OBRIGATORIA")
        itens = []
    vistos = set()
    for indice, item in enumerate(itens):
        caminho = f"textos_fiscais.itens[{indice}]"
        if not isinstance(item, dict) or set(item) != {
            "nitem_novo", "nitem_original", "item_rascunho_id", "infadprod",
        }:
            erro(caminho, "CAMPOS_INVALIDOS")
            continue
        for campo in ("nitem_novo", "nitem_original"):
            if type(item.get(campo)) is not int or not 1 <= item[campo] <= 999:
                erro(f"{caminho}.{campo}", "NITEM_INVALIDO")
        item_id = item.get("item_rascunho_id")
        if type(item_id) is not int or item_id <= 0:
            erro(f"{caminho}.item_rascunho_id", "IDENTIFICADOR_INVALIDO")
        elif item_id in vistos:
            erro(f"{caminho}.item_rascunho_id", "ITEM_DUPLICADO")
        vistos.add(item_id)
        if item.get("infadprod") != "":
            erro(f"{caminho}.infadprod", "TEXTO_FISCAL_NAO_APROVADO")

    politica = conteudo.get("politica")
    if not isinstance(politica, dict) or set(politica) != _CAMPOS_POLITICA:
        erro("politica", "CAMPOS_INVALIDOS")
        politica = {}
    if politica.get("classificacao_interna_obrigatoria") is not True:
        erro("politica.classificacao_interna_obrigatoria", "SEPARACAO_OBRIGATORIA")
    if politica.get("exportacao_automatica") is not False:
        erro("politica.exportacao_automatica", "EXPORTACAO_AUTOMATICA_PROIBIDA")
    if politica.get("exige_texto_fiscal_aprovado") is not True:
        erro("politica.exige_texto_fiscal_aprovado", "APROVACAO_ESPECIFICA_OBRIGATORIA")

    bloqueios = [{"grupo": "observacoes", "codigo": item["codigo"]} for item in pendencias]
    bloqueios.extend((
        {"grupo": "observacoes", "codigo": "TEXTO_FISCAL_APROVADO_PENDENTE"},
        {"grupo": "observacoes", "codigo": "MAPEAMENTO_XML_PENDENTE"},
        {"grupo": "xml", "codigo": "GERACAO_NAO_IMPLEMENTADA"},
        {"grupo": "transmissao", "codigo": "HOMOLOGACAO_PENDENTE"},
    ))
    return {
        "contrato": CONTRATO_VALIDACAO_OBSERVACOES,
        "estrutura_valida": not erros,
        "origem_completa": not erros and not pendencias,
        "textos_fiscais_definidos": False,
        "escopo_fiscal_suportado": False,
        "erros": erros,
        "pendencias": pendencias,
        "bloqueios": bloqueios,
        "permite_gerar_xml": False,
        "permite_emissao": False,
    }
