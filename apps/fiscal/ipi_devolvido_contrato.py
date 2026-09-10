"""Contrato não emissivo do IPI devolvido, separado do IPI da memória."""
from decimal import Decimal, InvalidOperation

from .tributos_itens_devolucao import CONTRATO_TRIBUTOS_ITENS


CONTRATO_IPI_DEVOLVIDO = "supplier_return_returned_ipi_policy_v1"
CONTRATO_VALIDACAO_IPI_DEVOLVIDO = "supplier_return_returned_ipi_policy_validation_v1"
_CAMPOS_FONTES = {
    "tributos_contrato", "memoria_id", "memoria_sha256", "revisao_memoria_sha256",
}
_CAMPOS_ITEM = {
    "nitem_novo", "nitem_original", "item_rascunho_id", "estado",
    "ipi_memoria", "imposto_devol",
}
_CAMPOS_IPI_MEMORIA = {"estado", "codigo", "base", "aliquota", "valor"}
_CAMPOS_IMPOSTO_DEVOL = {"pdevol", "vipidevol", "infadprod_aprovada"}
_CAMPOS_POLITICA = {
    "copiar_ipi_memoria", "calcular_percentual", "exige_hipotese_aprovada",
    "exige_justificativa_fiscal_aprovada",
}


def _decimal_exato(valor, casas):
    if not isinstance(valor, str) or not valor or "," in valor:
        return False
    try:
        numero = Decimal(valor)
        normalizado = numero.quantize(Decimal(1).scaleb(-casas))
    except (InvalidOperation, ValueError):
        return False
    return numero.is_finite() and numero >= 0 and numero == normalizado


def construir_ipi_devolvido(tributos):
    origem_ok = bool(tributos["validacao"].get("origem_completa"))
    itens_origem = tributos["conteudo"].get("itens", []) if origem_ok else []
    ids = {item.get("memoria_id") for item in itens_origem}
    hashes = {item.get("memoria_sha256") for item in itens_origem}
    revisoes = {item.get("revisao_sha256") for item in itens_origem}
    fonte_comum = len(ids) == len(hashes) == len(revisoes) == 1 and next(iter(ids), 0) not in (None, 0)
    itens = []
    for item in tributos["conteudo"].get("itens", []):
        grupo = item.get("grupos", {}).get("ipi_memoria", {}) if origem_ok else {}
        itens.append({
            "nitem_novo": item.get("nitem_novo"),
            "nitem_original": item.get("nitem_original"),
            "item_rascunho_id": item.get("item_rascunho_id"),
            "estado": "HIPOTESE_NAO_APROVADA",
            "ipi_memoria": {
                "estado": grupo.get("estado", "NAO_EQUIVALE_IPI_DEVOLVIDO"),
                "codigo": grupo.get("codigo", ""),
                "base": grupo.get("base", ""),
                "aliquota": grupo.get("aliquota", ""),
                "valor": grupo.get("valor", ""),
            },
            "imposto_devol": {
                "pdevol": "",
                "vipidevol": "",
                "infadprod_aprovada": False,
            },
        })
    conteudo = {
        "contrato": CONTRATO_IPI_DEVOLVIDO,
        "operacao": "DEVOLUCAO_COMPRA",
        "permite_emissao": False,
        "origem_aprovada": origem_ok and fonte_comum,
        "fontes": {
            "tributos_contrato": tributos["conteudo"].get("contrato", ""),
            "memoria_id": next(iter(ids)) if fonte_comum else 0,
            "memoria_sha256": next(iter(hashes)) if fonte_comum else "",
            "revisao_memoria_sha256": next(iter(revisoes)) if fonte_comum else "",
        },
        "itens": itens,
        "total": {"vipidevol": "", "estado": "NAO_DEFINIDO"},
        "politica": {
            "copiar_ipi_memoria": False,
            "calcular_percentual": False,
            "exige_hipotese_aprovada": True,
            "exige_justificativa_fiscal_aprovada": True,
        },
    }
    return {"conteudo": conteudo, "validacao": validar_ipi_devolvido(conteudo)}


def validar_ipi_devolvido(conteudo):
    erros = []
    pendencias = []

    def erro(caminho, codigo):
        erros.append({"caminho": caminho, "codigo": codigo})

    def pendencia(caminho, codigo):
        pendencias.append({"caminho": caminho, "codigo": codigo})

    if not isinstance(conteudo, dict):
        erro("$", "OBJETO_OBRIGATORIO")
        conteudo = {}
    campos = {"contrato", "operacao", "permite_emissao", "origem_aprovada", "fontes", "itens", "total", "politica"}
    if set(conteudo) != campos:
        erro("$", "CAMPOS_INVALIDOS")
    if conteudo.get("contrato") != CONTRATO_IPI_DEVOLVIDO:
        erro("contrato", "VALOR_NAO_SUPORTADO")
    if conteudo.get("operacao") != "DEVOLUCAO_COMPRA":
        erro("operacao", "VALOR_NAO_SUPORTADO")
    if conteudo.get("permite_emissao") is not False:
        erro("permite_emissao", "EMISSAO_PROIBIDA")
    if conteudo.get("origem_aprovada") is not True:
        pendencia("origem_aprovada", "MEMORIA_APROVADA_PENDENTE")

    fontes = conteudo.get("fontes")
    if not isinstance(fontes, dict) or set(fontes) != _CAMPOS_FONTES:
        erro("fontes", "CAMPOS_INVALIDOS")
        fontes = {}
    if fontes.get("tributos_contrato") != CONTRATO_TRIBUTOS_ITENS:
        erro("fontes.tributos_contrato", "CONTRATO_ORIGEM_INVALIDO")
    if type(fontes.get("memoria_id")) is not int or fontes.get("memoria_id", 0) <= 0:
        pendencia("fontes.memoria_id", "MEMORIA_PENDENTE")
    for campo in ("memoria_sha256", "revisao_memoria_sha256"):
        valor = fontes.get(campo)
        if not isinstance(valor, str) or len(valor) != 64 or any(c not in "0123456789abcdef" for c in valor):
            pendencia(f"fontes.{campo}", "HASH_ORIGEM_PENDENTE")

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
        for campo in ("nitem_novo", "nitem_original"):
            if type(item.get(campo)) is not int or not 1 <= item[campo] <= 999:
                erro(f"{caminho}.{campo}", "NITEM_INVALIDO")
        item_id = item.get("item_rascunho_id")
        if type(item_id) is not int or item_id <= 0:
            erro(f"{caminho}.item_rascunho_id", "IDENTIFICADOR_INVALIDO")
        elif item_id in vistos:
            erro(f"{caminho}.item_rascunho_id", "ITEM_DUPLICADO")
        vistos.add(item_id)
        if item.get("estado") != "HIPOTESE_NAO_APROVADA":
            erro(f"{caminho}.estado", "HIPOTESE_NAO_PODE_SER_ATIVADA")
        ipi_memoria = item.get("ipi_memoria")
        if not isinstance(ipi_memoria, dict) or set(ipi_memoria) != _CAMPOS_IPI_MEMORIA:
            erro(f"{caminho}.ipi_memoria", "CAMPOS_INVALIDOS")
        else:
            if ipi_memoria.get("estado") != "NAO_EQUIVALE_IPI_DEVOLVIDO":
                erro(f"{caminho}.ipi_memoria.estado", "ESTADO_INVALIDO")
            if not isinstance(ipi_memoria.get("codigo"), str):
                erro(f"{caminho}.ipi_memoria.codigo", "CODIGO_INVALIDO")
            for campo, casas in (("base", 2), ("aliquota", 4), ("valor", 2)):
                if not _decimal_exato(ipi_memoria.get(campo), casas):
                    pendencia(f"{caminho}.ipi_memoria.{campo}", "VALOR_ORIGEM_PENDENTE")
        imposto_devol = item.get("imposto_devol")
        if not isinstance(imposto_devol, dict) or set(imposto_devol) != _CAMPOS_IMPOSTO_DEVOL:
            erro(f"{caminho}.imposto_devol", "CAMPOS_INVALIDOS")
        else:
            for campo in ("pdevol", "vipidevol"):
                if imposto_devol.get(campo) != "":
                    erro(f"{caminho}.imposto_devol.{campo}", "VALOR_IPI_DEVOLVIDO_NAO_APROVADO")
            if imposto_devol.get("infadprod_aprovada") is not False:
                erro(f"{caminho}.imposto_devol.infadprod_aprovada", "JUSTIFICATIVA_FISCAL_NAO_APROVADA")

    total = conteudo.get("total")
    if not isinstance(total, dict) or set(total) != {"vipidevol", "estado"}:
        erro("total", "CAMPOS_INVALIDOS")
        total = {}
    if total.get("vipidevol") != "":
        erro("total.vipidevol", "TOTAL_IPI_DEVOLVIDO_NAO_APROVADO")
    if total.get("estado") != "NAO_DEFINIDO":
        erro("total.estado", "TOTAL_NAO_PODE_SER_ATIVADO")

    politica = conteudo.get("politica")
    if not isinstance(politica, dict) or set(politica) != _CAMPOS_POLITICA:
        erro("politica", "CAMPOS_INVALIDOS")
        politica = {}
    for campo in ("copiar_ipi_memoria", "calcular_percentual"):
        if politica.get(campo) is not False:
            erro(f"politica.{campo}", "AUTOMACAO_PROIBIDA")
    for campo in ("exige_hipotese_aprovada", "exige_justificativa_fiscal_aprovada"):
        if politica.get(campo) is not True:
            erro(f"politica.{campo}", "APROVACAO_ESPECIFICA_OBRIGATORIA")

    bloqueios = [{"grupo": "ipi_devolvido", "codigo": item["codigo"]} for item in pendencias]
    bloqueios.extend((
        {"grupo": "ipi_devolvido", "codigo": "HIPOTESE_CONTABIL_NAO_APROVADA"},
        {"grupo": "ipi_devolvido", "codigo": "VALORES_E_JUSTIFICATIVA_PENDENTES"},
        {"grupo": "ipi_devolvido", "codigo": "MAPEAMENTO_XML_PENDENTE"},
        {"grupo": "xml", "codigo": "GERACAO_NAO_IMPLEMENTADA"},
        {"grupo": "transmissao", "codigo": "HOMOLOGACAO_PENDENTE"},
    ))
    return {
        "contrato": CONTRATO_VALIDACAO_IPI_DEVOLVIDO,
        "estrutura_valida": not erros,
        "origem_completa": not erros and not pendencias,
        "hipotese_definida": False,
        "escopo_fiscal_suportado": False,
        "erros": erros,
        "pendencias": pendencias,
        "bloqueios": bloqueios,
        "permite_gerar_xml": False,
        "permite_emissao": False,
    }
