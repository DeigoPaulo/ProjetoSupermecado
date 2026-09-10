"""Contrato puro e não emissivo dos produtos da devolução."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


CONTRATO_PRODUTOS = "supplier_return_products_v1"
CONTRATO_VALIDACAO_PRODUTOS = "supplier_return_products_validation_v1"

_CAMPOS_ITEM = {
    "nitem_novo", "nitem_original", "item_rascunho_id", "produto_id",
    "xml_origem_sha256", "parametrizacao_id", "parametrizacao_sha256",
    "memoria_id", "memoria_sha256", "memoria_aprovada", "codigo_produto",
    "ean", "ean_tributavel", "descricao", "ncm", "cest", "cfop",
    "unidade_comercial", "quantidade_comercial", "valor_unitario_comercial",
    "valor_produtos", "unidade_tributavel", "quantidade_tributavel",
    "valor_unitario_tributavel", "tipo_codigo_icms", "origem_icms",
    "codigo_icms", "codigo_ipi", "codigo_pis", "codigo_cofins", "codigo_cbenef",
}


def _decimal(valor, *, positivo=False, casas=None):
    if not isinstance(valor, str) or not valor or "," in valor:
        return None
    try:
        numero = Decimal(valor)
    except (InvalidOperation, ValueError):
        return None
    if not numero.is_finite() or numero < 0 or (positivo and numero <= 0):
        return None
    if casas is not None:
        try:
            if numero != numero.quantize(Decimal(1).scaleb(-casas)):
                return None
        except InvalidOperation:
            return None
    return numero


def validar_produtos_devolucao(conteudo):
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
    if conteudo.get("contrato") != CONTRATO_PRODUTOS:
        erro("contrato", "VALOR_NAO_SUPORTADO")
    if conteudo.get("operacao") != "DEVOLUCAO_COMPRA":
        erro("operacao", "VALOR_NAO_SUPORTADO")
    if conteudo.get("permite_emissao") is not False:
        erro("permite_emissao", "EMISSAO_PROIBIDA")
    itens = conteudo.get("itens")
    if not isinstance(itens, list) or not itens:
        erro("itens", "LISTA_NAO_VAZIA_OBRIGATORIA")
        itens = []
    novos = set()
    rascunhos = set()
    for indice, item in enumerate(itens):
        caminho = f"itens[{indice}]"
        if not isinstance(item, dict) or set(item) != _CAMPOS_ITEM:
            erro(caminho, "CAMPOS_INVALIDOS")
            continue
        for campo in ("nitem_novo", "nitem_original", "item_rascunho_id", "produto_id"):
            if type(item.get(campo)) is not int or item[campo] <= 0:
                erro(f"{caminho}.{campo}", "IDENTIFICADOR_INVALIDO")
        for campo in ("nitem_novo", "nitem_original"):
            if type(item.get(campo)) is int and item[campo] > 999:
                erro(f"{caminho}.{campo}", "NITEM_INVALIDO")
        if item.get("nitem_novo") in novos:
            erro(f"{caminho}.nitem_novo", "NITEM_NOVO_DUPLICADO")
        novos.add(item.get("nitem_novo"))
        if item.get("item_rascunho_id") in rascunhos:
            erro(f"{caminho}.item_rascunho_id", "ITEM_RASCUNHO_DUPLICADO")
        rascunhos.add(item.get("item_rascunho_id"))
        for campo in ("xml_origem_sha256", "parametrizacao_sha256", "memoria_sha256"):
            valor = item.get(campo)
            if not isinstance(valor, str) or len(valor) != 64 or not valor.isascii() or any(c not in "0123456789abcdef" for c in valor):
                pendencia(f"{caminho}.{campo}", "HASH_ORIGEM_PENDENTE")
        for campo in ("parametrizacao_id", "memoria_id"):
            if type(item.get(campo)) is not int or item[campo] <= 0:
                pendencia(f"{caminho}.{campo}", "ORIGEM_APROVADA_PENDENTE")
        if item.get("memoria_aprovada") is not True:
            pendencia(f"{caminho}.memoria_aprovada", "MEMORIA_APROVADA_PENDENTE")
        for campo, limite, codigo in (
            ("codigo_produto", 60, "CODIGO_PRODUTO_PENDENTE"),
            ("descricao", 120, "DESCRICAO_PENDENTE"),
            ("unidade_comercial", 6, "UNIDADE_COMERCIAL_PENDENTE"),
            ("unidade_tributavel", 6, "UNIDADE_TRIBUTAVEL_PENDENTE"),
        ):
            if not isinstance(item.get(campo), str) or not item[campo].strip() or len(item[campo]) > limite:
                pendencia(f"{caminho}.{campo}", codigo)
        if not isinstance(item.get("ncm"), str) or not item["ncm"].isdigit() or len(item["ncm"]) != 8:
            pendencia(f"{caminho}.ncm", "NCM_PENDENTE")
        if not isinstance(item.get("cest"), str) or (item["cest"] and (not item["cest"].isdigit() or len(item["cest"]) != 7)):
            pendencia(f"{caminho}.cest", "CEST_INVALIDO")
        if not isinstance(item.get("cfop"), str) or not item["cfop"].isdigit() or len(item["cfop"]) != 4 or item["cfop"][0] not in "567":
            pendencia(f"{caminho}.cfop", "CFOP_SAIDA_PENDENTE")
        quantidade = _decimal(item.get("quantidade_comercial"), positivo=True, casas=4)
        unitario = _decimal(item.get("valor_unitario_comercial"), positivo=True, casas=10)
        total = _decimal(item.get("valor_produtos"), casas=2)
        if quantidade is None:
            pendencia(f"{caminho}.quantidade_comercial", "QUANTIDADE_COMERCIAL_PENDENTE")
        if unitario is None:
            pendencia(f"{caminho}.valor_unitario_comercial", "VALOR_UNITARIO_PENDENTE")
        if total is None:
            pendencia(f"{caminho}.valor_produtos", "VALOR_PRODUTOS_PENDENTE")
        if quantidade is not None and unitario is not None and total is not None:
            calculado = (quantidade * unitario).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if calculado != total:
                pendencia(f"{caminho}.valor_produtos", "VALOR_NAO_CONFERE_COM_QUANTIDADE_E_UNITARIO")
        for campo, codigo in (
            ("quantidade_tributavel", "QUANTIDADE_TRIBUTAVEL_PENDENTE"),
            ("valor_unitario_tributavel", "VALOR_UNITARIO_TRIBUTAVEL_PENDENTE"),
        ):
            casas = 4 if campo == "quantidade_tributavel" else 10
            if _decimal(item.get(campo), positivo=True, casas=casas) is None:
                pendencia(f"{caminho}.{campo}", codigo)
        if item.get("tipo_codigo_icms") not in {"CST", "CSOSN", "NAO_APLICAVEL"}:
            pendencia(f"{caminho}.tipo_codigo_icms", "TIPO_ICMS_PENDENTE")
        if item.get("origem_icms") not in set("012345678"):
            pendencia(f"{caminho}.origem_icms", "ORIGEM_ICMS_PENDENTE")
        for campo in ("codigo_icms", "codigo_ipi", "codigo_pis", "codigo_cofins", "codigo_cbenef"):
            if not isinstance(item.get(campo), str) or not item[campo]:
                pendencia(f"{caminho}.{campo}", "CLASSIFICACAO_PENDENTE")
    bloqueios = [{"grupo": "produtos", "codigo": item["codigo"]} for item in pendencias]
    bloqueios.extend((
        {"grupo": "produtos", "codigo": "PARIDADE_XML_E_XSD_PENDENTE"},
        {"grupo": "xml", "codigo": "GERACAO_NAO_IMPLEMENTADA"},
        {"grupo": "transmissao", "codigo": "HOMOLOGACAO_PENDENTE"},
    ))
    return {
        "contrato": CONTRATO_VALIDACAO_PRODUTOS,
        "estrutura_valida": not erros,
        "dados_completos": not erros and not pendencias,
        "erros": erros,
        "pendencias": pendencias,
        "bloqueios": bloqueios,
        "permite_gerar_xml": False,
        "permite_emissao": False,
    }
