"""Validação estrutural, pura e não emissiva das referências da devolução."""


CONTRATO_REFERENCIAS_ITEM = "supplier_return_item_references_v1"
CONTRATO_VALIDACAO_REFERENCIAS_ITEM = "supplier_return_item_references_validation_v1"
POLITICA_REFERENCIAS_ITEM = "NT_2025_002_V1_51_VC"


def _chave_acesso_valida(chave):
    if not isinstance(chave, str) or len(chave) != 44 or not chave.isascii() or not chave.isdigit():
        return False
    pesos = (2, 3, 4, 5, 6, 7, 8, 9) * 6
    soma = sum(int(digito) * peso for digito, peso in zip(reversed(chave[:43]), pesos))
    resto = soma % 11
    esperado = 0 if resto in (0, 1) else 11 - resto
    return int(chave[43]) == esperado


def _nitem_valido(valor):
    return type(valor) is int and 1 <= valor <= 999


def validar_referencias_item_devolucao(conteudo):
    """Valida chave+nItem sem consultar banco, gerar XML ou liberar transmissão."""
    erros = []
    bloqueios = []

    def erro(caminho, codigo):
        erros.append({"caminho": caminho, "codigo": codigo})

    if not isinstance(conteudo, dict):
        erro("$", "OBJETO_OBRIGATORIO")
        conteudo = {}
    permitidos = {
        "contrato", "politica", "modelo", "operacao", "possui_nfref_cabecalho",
        "permite_emissao", "itens",
    }
    for _chave in conteudo.keys() - permitidos:
        erro("$", "CAMPO_DESCONHECIDO")
    for campo, esperado in (
        ("contrato", CONTRATO_REFERENCIAS_ITEM),
        ("politica", POLITICA_REFERENCIAS_ITEM),
        ("modelo", "55"),
        ("operacao", "DEVOLUCAO_COMPRA"),
    ):
        if conteudo.get(campo) != esperado:
            erro(campo, "VALOR_NAO_SUPORTADO")
    if conteudo.get("possui_nfref_cabecalho") is not False:
        erro("possui_nfref_cabecalho", "NFREF_CABECALHO_PROIBIDA")
    if conteudo.get("permite_emissao") is not False:
        erro("permite_emissao", "EMISSAO_PROIBIDA")

    itens = conteudo.get("itens")
    if not isinstance(itens, list) or not itens:
        erro("itens", "LISTA_NAO_VAZIA_OBRIGATORIA")
        itens = []
    pares = set()
    itens_novos = set()
    chaves = set()
    campos_item = {"nitem_novo", "chave_acesso", "nitem_original"}
    for indice, item in enumerate(itens):
        caminho = f"itens[{indice}]"
        if not isinstance(item, dict):
            erro(caminho, "ITEM_INVALIDO")
            continue
        if set(item) != campos_item:
            erro(caminho, "CAMPOS_INVALIDOS")
        nitem_novo = item.get("nitem_novo")
        nitem_original = item.get("nitem_original")
        chave = item.get("chave_acesso")
        if not _nitem_valido(nitem_novo):
            erro(caminho + ".nitem_novo", "NITEM_INVALIDO")
        elif nitem_novo in itens_novos:
            erro(caminho + ".nitem_novo", "NITEM_NOVO_DUPLICADO")
        else:
            itens_novos.add(nitem_novo)
        if not _nitem_valido(nitem_original):
            erro(caminho + ".nitem_original", "NITEM_INVALIDO")
        if not _chave_acesso_valida(chave):
            erro(caminho + ".chave_acesso", "CHAVE_ACESSO_INVALIDA")
            continue
        chaves.add(chave)
        if _nitem_valido(nitem_original):
            par = (chave, nitem_original)
            if par in pares:
                erro(caminho, "DFE_ITEM_REFERENCIADO_EM_DUPLICIDADE")
            pares.add(par)

    escopo_suportado = not erros and bool(chaves) and len(chaves) == 1
    if len(chaves) > 1:
        bloqueios.append({"grupo": "origem", "codigo": "MULTIPLAS_ORIGENS_FORA_ESCOPO_INICIAL"})
    bloqueios.extend((
        {"grupo": "vigencia", "codigo": "CRONOGRAMA_UF_NAO_CONFIRMADO"},
        {"grupo": "origem", "codigo": "PARTES_E_XML_ORIGINAL_NAO_CONFERIDOS"},
        {"grupo": "dossie", "codigo": "INTEGRACAO_AUTENTICADA_PENDENTE"},
        {"grupo": "xml", "codigo": "GERACAO_NAO_IMPLEMENTADA"},
        {"grupo": "transmissao", "codigo": "HOMOLOGACAO_PENDENTE"},
    ))
    return {
        "contrato": CONTRATO_VALIDACAO_REFERENCIAS_ITEM,
        "estrutura_valida": not erros,
        "escopo_suportado": escopo_suportado,
        "erros": erros,
        "bloqueios": bloqueios,
        "permite_gerar_xml": False,
        "permite_emissao": False,
    }
