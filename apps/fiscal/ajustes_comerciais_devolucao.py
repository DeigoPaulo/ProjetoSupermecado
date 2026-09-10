"""Contrato puro dos ajustes comerciais informados, sem reaplicação ou emissão."""
from decimal import Decimal, InvalidOperation


CONTRATO_AJUSTES_COMERCIAIS = "supplier_return_commercial_adjustments_v1"
CONTRATO_VALIDACAO_AJUSTES_COMERCIAIS = "supplier_return_commercial_adjustments_validation_v1"
_CAMPOS_ITEM = {
    "nitem_novo", "nitem_original", "item_rascunho_id", "item_memoria_id",
    "valor_base", "frete", "seguro", "outras_despesas", "desconto", "total_informado",
}
_CAMPOS_TOTAIS = {"valor_base", "frete", "seguro", "outras_despesas", "desconto", "total_informado"}


def _decimal(valor):
    if not isinstance(valor, str) or not valor or "," in valor:
        return None
    try:
        numero = Decimal(valor)
        normalizado = numero.quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None
    return numero if numero.is_finite() and numero >= 0 and numero == normalizado else None


def validar_ajustes_comerciais_devolucao(conteudo):
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
        "contrato", "operacao", "permite_emissao", "origem_aprovada",
        "rateio_id", "rateio_sha256", "reflexos_id", "reflexos_sha256",
        "memoria_id", "memoria_sha256", "revisao_memoria_sha256", "itens", "totais",
    }
    if set(conteudo) != campos:
        erro("$", "CAMPOS_INVALIDOS")
    if conteudo.get("contrato") != CONTRATO_AJUSTES_COMERCIAIS:
        erro("contrato", "VALOR_NAO_SUPORTADO")
    if conteudo.get("operacao") != "DEVOLUCAO_COMPRA":
        erro("operacao", "VALOR_NAO_SUPORTADO")
    if conteudo.get("permite_emissao") is not False:
        erro("permite_emissao", "EMISSAO_PROIBIDA")
    if conteudo.get("origem_aprovada") is not True:
        pendencia("origem_aprovada", "CADEIA_FINAL_APROVADA_PENDENTE")
    for campo in ("rateio_id", "reflexos_id", "memoria_id"):
        if type(conteudo.get(campo)) is not int or conteudo.get(campo, 0) <= 0:
            pendencia(campo, "IDENTIFICADOR_ORIGEM_PENDENTE")
    for campo in ("rateio_sha256", "reflexos_sha256", "memoria_sha256", "revisao_memoria_sha256"):
        valor = conteudo.get(campo)
        if not isinstance(valor, str) or len(valor) != 64 or any(c not in "0123456789abcdef" for c in valor):
            pendencia(campo, "HASH_ORIGEM_PENDENTE")

    itens = conteudo.get("itens")
    if not isinstance(itens, list) or not itens:
        erro("itens", "LISTA_NAO_VAZIA_OBRIGATORIA")
        itens = []
    vistos = set()
    somas = {campo: Decimal("0.00") for campo in _CAMPOS_TOTAIS}
    valores_validos = True
    for indice, item in enumerate(itens):
        caminho = f"itens[{indice}]"
        if not isinstance(item, dict) or set(item) != _CAMPOS_ITEM:
            erro(caminho, "CAMPOS_INVALIDOS")
            valores_validos = False
            continue
        for campo in ("nitem_novo", "nitem_original"):
            if type(item.get(campo)) is not int or not 1 <= item[campo] <= 999:
                erro(f"{caminho}.{campo}", "NITEM_INVALIDO")
        for campo in ("item_rascunho_id", "item_memoria_id"):
            if type(item.get(campo)) is not int or item.get(campo, 0) <= 0:
                pendencia(f"{caminho}.{campo}", "ITEM_ORIGEM_PENDENTE")
        if item.get("item_rascunho_id") in vistos:
            erro(f"{caminho}.item_rascunho_id", "ITEM_DUPLICADO")
        vistos.add(item.get("item_rascunho_id"))
        numeros = {}
        for campo in _CAMPOS_TOTAIS:
            numeros[campo] = _decimal(item.get(campo))
            if numeros[campo] is None:
                pendencia(f"{caminho}.{campo}", "VALOR_COMERCIAL_PENDENTE")
                valores_validos = False
            else:
                somas[campo] += numeros[campo]
        if all(numero is not None for numero in numeros.values()):
            esperado = numeros["valor_base"] + numeros["frete"] + numeros["seguro"] + numeros["outras_despesas"] - numeros["desconto"]
            if esperado < 0 or esperado != numeros["total_informado"]:
                pendencia(f"{caminho}.total_informado", "TOTAL_ITEM_NAO_CONFERE")

    totais = conteudo.get("totais")
    if not isinstance(totais, dict) or set(totais) != _CAMPOS_TOTAIS:
        erro("totais", "CAMPOS_INVALIDOS")
        totais = {}
    for campo in _CAMPOS_TOTAIS:
        total = _decimal(totais.get(campo))
        if total is None:
            pendencia(f"totais.{campo}", "TOTAL_PENDENTE")
        elif valores_validos and total != somas[campo]:
            pendencia(f"totais.{campo}", "TOTAL_NAO_CONFERE_COM_ITENS")

    bloqueios = [{"grupo": "ajustes_comerciais", "codigo": item["codigo"]} for item in pendencias]
    bloqueios.extend((
        {"grupo": "ajustes_comerciais", "codigo": "NAO_REAPLICAR_A_BASES_TRIBUTARIAS"},
        {"grupo": "ajustes_comerciais", "codigo": "MAPEAMENTO_XML_PENDENTE"},
        {"grupo": "xml", "codigo": "GERACAO_NAO_IMPLEMENTADA"},
        {"grupo": "transmissao", "codigo": "HOMOLOGACAO_PENDENTE"},
    ))
    return {
        "contrato": CONTRATO_VALIDACAO_AJUSTES_COMERCIAIS,
        "estrutura_valida": not erros,
        "origem_completa": not erros and not pendencias,
        "erros": erros,
        "pendencias": pendencias,
        "bloqueios": bloqueios,
        "permite_gerar_xml": False,
        "permite_emissao": False,
    }
