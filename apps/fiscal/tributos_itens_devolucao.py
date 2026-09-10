"""Contrato puro dos valores tributários informados, sem cálculo ou emissão."""
from decimal import Decimal, InvalidOperation


CONTRATO_TRIBUTOS_ITENS = "supplier_return_item_tax_values_v1"
CONTRATO_VALIDACAO_TRIBUTOS_ITENS = "supplier_return_item_tax_values_validation_v1"

ESTADOS_GRUPOS = {
    "icms": "INFORMADO_PENDENTE_MATRIZ",
    "pis": "INFORMADO_PENDENTE_MATRIZ",
    "cofins": "INFORMADO_PENDENTE_MATRIZ",
    "icms_st": "HIPOTESE_NAO_CONFIRMADA",
    "fcp": "HIPOTESE_NAO_CONFIRMADA",
    "ipi_memoria": "NAO_EQUIVALE_IPI_DEVOLVIDO",
    "ibs": "VIGENCIA_E_LEIAUTE_PENDENTES",
    "cbs": "VIGENCIA_E_LEIAUTE_PENDENTES",
}
_CAMPOS_ITEM = {
    "nitem_novo", "nitem_original", "item_rascunho_id", "memoria_id",
    "memoria_sha256", "revisao_sha256", "origem_aprovada", "grupos",
}
_CAMPOS_GRUPO = {"estado", "codigo", "base", "aliquota", "valor"}


def _decimal_exato(valor, casas):
    if not isinstance(valor, str) or not valor or "," in valor:
        return False
    try:
        numero = Decimal(valor)
        normalizado = numero.quantize(Decimal(1).scaleb(-casas))
    except (InvalidOperation, ValueError):
        return False
    return numero.is_finite() and numero >= 0 and numero == normalizado


def validar_tributos_itens_devolucao(conteudo):
    erros = []
    pendencias = []

    def erro(caminho, codigo):
        erros.append({"caminho": caminho, "codigo": codigo})

    def pendencia(caminho, codigo):
        pendencias.append({"caminho": caminho, "codigo": codigo})

    if not isinstance(conteudo, dict):
        erro("$", "OBJETO_OBRIGATORIO")
        conteudo = {}
    if set(conteudo) != {"contrato", "operacao", "permite_emissao", "itens"}:
        erro("$", "CAMPOS_INVALIDOS")
    if conteudo.get("contrato") != CONTRATO_TRIBUTOS_ITENS:
        erro("contrato", "VALOR_NAO_SUPORTADO")
    if conteudo.get("operacao") != "DEVOLUCAO_COMPRA":
        erro("operacao", "VALOR_NAO_SUPORTADO")
    if conteudo.get("permite_emissao") is not False:
        erro("permite_emissao", "EMISSAO_PROIBIDA")
    itens = conteudo.get("itens")
    if not isinstance(itens, list) or not itens:
        erro("itens", "LISTA_NAO_VAZIA_OBRIGATORIA")
        itens = []
    vistos = set()
    for indice, item in enumerate(itens):
        caminho = f"itens[{indice}]"
        if not isinstance(item, dict) or set(item) != _CAMPOS_ITEM:
            erro(caminho, "CAMPOS_INVALIDOS")
            continue
        for campo in ("nitem_novo", "nitem_original", "item_rascunho_id"):
            if type(item.get(campo)) is not int or not 1 <= item[campo] <= (999 if campo.startswith("nitem") else 2**63 - 1):
                erro(f"{caminho}.{campo}", "IDENTIFICADOR_INVALIDO")
        if item.get("item_rascunho_id") in vistos:
            erro(f"{caminho}.item_rascunho_id", "ITEM_DUPLICADO")
        vistos.add(item.get("item_rascunho_id"))
        if item.get("origem_aprovada") is not True:
            pendencia(f"{caminho}.origem_aprovada", "MEMORIA_REVISADA_APROVADA_PENDENTE")
        if type(item.get("memoria_id")) is not int or item.get("memoria_id", 0) <= 0:
            pendencia(f"{caminho}.memoria_id", "MEMORIA_PENDENTE")
        for campo in ("memoria_sha256", "revisao_sha256"):
            valor = item.get(campo)
            if not isinstance(valor, str) or len(valor) != 64 or any(c not in "0123456789abcdef" for c in valor):
                pendencia(f"{caminho}.{campo}", "HASH_ORIGEM_PENDENTE")
        grupos = item.get("grupos")
        if not isinstance(grupos, dict) or set(grupos) != set(ESTADOS_GRUPOS):
            erro(f"{caminho}.grupos", "GRUPOS_INVALIDOS")
            continue
        for nome, estado in ESTADOS_GRUPOS.items():
            grupo = grupos.get(nome)
            grupo_caminho = f"{caminho}.grupos.{nome}"
            if not isinstance(grupo, dict) or set(grupo) != _CAMPOS_GRUPO:
                erro(grupo_caminho, "CAMPOS_INVALIDOS")
                continue
            if grupo.get("estado") != estado:
                erro(f"{grupo_caminho}.estado", "ESTADO_INVALIDO")
            if not isinstance(grupo.get("codigo"), str):
                erro(f"{grupo_caminho}.codigo", "CODIGO_INVALIDO")
            if item.get("origem_aprovada") is True:
                for campo, casas in (("base", 2), ("aliquota", 4), ("valor", 2)):
                    if not _decimal_exato(grupo.get(campo), casas):
                        pendencia(f"{grupo_caminho}.{campo}", "VALOR_TRIBUTARIO_PENDENTE")
    bloqueios = [{"grupo": "bases_valores", "codigo": item["codigo"]} for item in pendencias]
    bloqueios.extend((
        {"grupo": "classificacao", "codigo": "MATRIZ_TRIBUTARIA_NAO_HOMOLOGADA"},
        {"grupo": "icms_st_fcp", "codigo": "HIPOTESE_NAO_CONFIRMADA"},
        {"grupo": "ipi_devolvido", "codigo": "GRUPO_ESPECIFICO_NAO_IMPLEMENTADO"},
        {"grupo": "ibs_cbs", "codigo": "VIGENCIA_E_LEIAUTE_PENDENTES"},
        {"grupo": "xml", "codigo": "GERACAO_NAO_IMPLEMENTADA"},
        {"grupo": "transmissao", "codigo": "HOMOLOGACAO_PENDENTE"},
    ))
    return {
        "contrato": CONTRATO_VALIDACAO_TRIBUTOS_ITENS,
        "estrutura_valida": not erros,
        "origem_completa": not erros and not pendencias,
        "escopo_fiscal_suportado": False,
        "erros": erros,
        "pendencias": pendencias,
        "bloqueios": bloqueios,
        "permite_gerar_xml": False,
        "permite_emissao": False,
    }
