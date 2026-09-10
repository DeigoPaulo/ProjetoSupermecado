"""Totalização somente diagnóstica da devolução, sem formar totais do XML."""
from decimal import Decimal, InvalidOperation

from .ajustes_comerciais_devolucao import CONTRATO_AJUSTES_COMERCIAIS
from .produtos_devolucao import CONTRATO_PRODUTOS
from .tributos_itens_devolucao import CONTRATO_TRIBUTOS_ITENS, ESTADOS_GRUPOS


CONTRATO_TOTALIZACAO = "supplier_return_diagnostic_totals_v1"
CONTRATO_VALIDACAO_TOTALIZACAO = "supplier_return_diagnostic_totals_validation_v1"
_CAMPOS_COMERCIAIS = (
    "valor_produtos", "valor_base", "frete", "seguro",
    "outras_despesas", "desconto", "total_informado",
)
_CAMPOS_FONTE = {
    "produtos_contrato", "tributos_contrato", "ajustes_contrato",
    "memoria_id", "memoria_sha256", "revisao_memoria_sha256",
}
_CAMPOS_NAO_DEFINIDOS = ("valor_nota", "ipi_devolvido", "total_rtc")


def _decimal(valor):
    if not isinstance(valor, str) or not valor or "," in valor:
        return None
    try:
        numero = Decimal(valor)
        normalizado = numero.quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None
    return numero if numero.is_finite() and numero >= 0 and numero == normalizado else None


def _somar(valores):
    numeros = [_decimal(valor) for valor in valores]
    if not numeros or any(numero is None for numero in numeros):
        return ""
    return format(sum(numeros, Decimal("0.00")), ".2f")


def _origem_comum(produtos, tributos, ajustes):
    produtos_itens = produtos["conteudo"].get("itens", [])
    tributos_itens = tributos["conteudo"].get("itens", [])
    ids = {item.get("memoria_id") for item in produtos_itens + tributos_itens}
    ids.add(ajustes["conteudo"].get("memoria_id"))
    hashes = {item.get("memoria_sha256") for item in produtos_itens + tributos_itens}
    hashes.add(ajustes["conteudo"].get("memoria_sha256"))
    revisoes = {item.get("revisao_sha256") for item in tributos_itens}
    revisoes.add(ajustes["conteudo"].get("revisao_memoria_sha256"))
    mesma = len(ids) == len(hashes) == len(revisoes) == 1 and next(iter(ids), 0) not in (None, 0)
    return {
        "mesma": mesma,
        "memoria_id": next(iter(ids)) if mesma else 0,
        "memoria_sha256": next(iter(hashes)) if mesma else "",
        "revisao_memoria_sha256": next(iter(revisoes)) if mesma else "",
    }


def construir_totalizacao_diagnostica(produtos, tributos, ajustes):
    produtos_ok = bool(produtos["validacao"].get("dados_completos"))
    tributos_ok = bool(tributos["validacao"].get("origem_completa"))
    ajustes_ok = bool(ajustes["validacao"].get("origem_completa"))
    origem = _origem_comum(produtos, tributos, ajustes) if produtos_ok and tributos_ok and ajustes_ok else {
        "mesma": False, "memoria_id": 0, "memoria_sha256": "", "revisao_memoria_sha256": "",
    }
    itens_produtos = produtos["conteudo"].get("itens", []) if produtos_ok else []
    itens_tributos = tributos["conteudo"].get("itens", []) if tributos_ok else []
    totais_ajustes = ajustes["conteudo"].get("totais", {}) if ajustes_ok else {}
    comerciais = {
        "valor_produtos": _somar([item.get("valor_produtos") for item in itens_produtos]),
        **{
            campo: totais_ajustes.get(campo, "")
            for campo in _CAMPOS_COMERCIAIS if campo != "valor_produtos"
        },
    }
    totais_tributarios = {}
    for grupo, estado in ESTADOS_GRUPOS.items():
        grupos = [item.get("grupos", {}).get(grupo, {}) for item in itens_tributos]
        totais_tributarios[grupo] = {
            "estado": estado,
            "base": _somar([item.get("base") for item in grupos]),
            "valor": _somar([item.get("valor") for item in grupos]),
        }
    conteudo = {
        "contrato": CONTRATO_TOTALIZACAO,
        "operacao": "DEVOLUCAO_COMPRA",
        "permite_emissao": False,
        "origens": {
            "produtos": produtos_ok,
            "tributos": tributos_ok,
            "ajustes_comerciais": ajustes_ok,
            "mesma_memoria": origem["mesma"],
        },
        "fontes": {
            "produtos_contrato": produtos["conteudo"].get("contrato", ""),
            "tributos_contrato": tributos["conteudo"].get("contrato", ""),
            "ajustes_contrato": ajustes["conteudo"].get("contrato", ""),
            "memoria_id": origem["memoria_id"],
            "memoria_sha256": origem["memoria_sha256"],
            "revisao_memoria_sha256": origem["revisao_memoria_sha256"],
        },
        "totais_comerciais": comerciais,
        "totais_tributarios_informados": totais_tributarios,
        "totais_fiscais_nao_definidos": {campo: "" for campo in _CAMPOS_NAO_DEFINIDOS},
    }
    return {"conteudo": conteudo, "validacao": validar_totalizacao_diagnostica(conteudo)}


def validar_totalizacao_diagnostica(conteudo):
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
        "contrato", "operacao", "permite_emissao", "origens", "fontes",
        "totais_comerciais", "totais_tributarios_informados", "totais_fiscais_nao_definidos",
    }
    if set(conteudo) != campos:
        erro("$", "CAMPOS_INVALIDOS")
    if conteudo.get("contrato") != CONTRATO_TOTALIZACAO:
        erro("contrato", "VALOR_NAO_SUPORTADO")
    if conteudo.get("operacao") != "DEVOLUCAO_COMPRA":
        erro("operacao", "VALOR_NAO_SUPORTADO")
    if conteudo.get("permite_emissao") is not False:
        erro("permite_emissao", "EMISSAO_PROIBIDA")

    origens = conteudo.get("origens")
    campos_origens = {"produtos", "tributos", "ajustes_comerciais", "mesma_memoria"}
    if not isinstance(origens, dict) or set(origens) != campos_origens:
        erro("origens", "CAMPOS_INVALIDOS")
        origens = {}
    for campo in campos_origens:
        if origens.get(campo) is not True:
            pendencia(f"origens.{campo}", "ORIGEM_TOTALIZACAO_PENDENTE")

    fontes = conteudo.get("fontes")
    if not isinstance(fontes, dict) or set(fontes) != _CAMPOS_FONTE:
        erro("fontes", "CAMPOS_INVALIDOS")
        fontes = {}
    contratos = {
        "produtos_contrato": CONTRATO_PRODUTOS,
        "tributos_contrato": CONTRATO_TRIBUTOS_ITENS,
        "ajustes_contrato": CONTRATO_AJUSTES_COMERCIAIS,
    }
    for campo, esperado in contratos.items():
        if fontes.get(campo) != esperado:
            erro(f"fontes.{campo}", "CONTRATO_ORIGEM_INVALIDO")
    if type(fontes.get("memoria_id")) is not int or fontes.get("memoria_id", 0) <= 0:
        pendencia("fontes.memoria_id", "MEMORIA_COMUM_PENDENTE")
    for campo in ("memoria_sha256", "revisao_memoria_sha256"):
        valor = fontes.get(campo)
        if not isinstance(valor, str) or len(valor) != 64 or any(c not in "0123456789abcdef" for c in valor):
            pendencia(f"fontes.{campo}", "HASH_ORIGEM_PENDENTE")

    comerciais = conteudo.get("totais_comerciais")
    if not isinstance(comerciais, dict) or set(comerciais) != set(_CAMPOS_COMERCIAIS):
        erro("totais_comerciais", "CAMPOS_INVALIDOS")
        comerciais = {}
    numeros = {}
    for campo in _CAMPOS_COMERCIAIS:
        numeros[campo] = _decimal(comerciais.get(campo))
        if numeros[campo] is None:
            pendencia(f"totais_comerciais.{campo}", "TOTAL_COMERCIAL_PENDENTE")
    if all(numero is not None for numero in numeros.values()):
        esperado = numeros["valor_base"] + numeros["frete"] + numeros["seguro"] + numeros["outras_despesas"] - numeros["desconto"]
        if esperado != numeros["total_informado"]:
            pendencia("totais_comerciais.total_informado", "TOTAL_COMERCIAL_NAO_CONFERE")
        if numeros["valor_produtos"] != numeros["valor_base"]:
            pendencia("totais_comerciais.valor_base", "BASE_COMERCIAL_DIVERGE_PRODUTOS")

    tributarios = conteudo.get("totais_tributarios_informados")
    if not isinstance(tributarios, dict) or set(tributarios) != set(ESTADOS_GRUPOS):
        erro("totais_tributarios_informados", "GRUPOS_INVALIDOS")
        tributarios = {}
    for grupo, estado in ESTADOS_GRUPOS.items():
        dados = tributarios.get(grupo)
        caminho = f"totais_tributarios_informados.{grupo}"
        if not isinstance(dados, dict) or set(dados) != {"estado", "base", "valor"}:
            erro(caminho, "CAMPOS_INVALIDOS")
            continue
        if dados.get("estado") != estado:
            erro(f"{caminho}.estado", "ESTADO_INVALIDO")
        for campo in ("base", "valor"):
            if _decimal(dados.get(campo)) is None:
                pendencia(f"{caminho}.{campo}", "TOTAL_TRIBUTARIO_PENDENTE")

    nao_definidos = conteudo.get("totais_fiscais_nao_definidos")
    if not isinstance(nao_definidos, dict) or set(nao_definidos) != set(_CAMPOS_NAO_DEFINIDOS):
        erro("totais_fiscais_nao_definidos", "CAMPOS_INVALIDOS")
        nao_definidos = {}
    for campo in _CAMPOS_NAO_DEFINIDOS:
        if nao_definidos.get(campo) != "":
            erro(f"totais_fiscais_nao_definidos.{campo}", "TOTAL_FISCAL_NAO_PODE_SER_PREENCHIDO")

    bloqueios = [{"grupo": "totalizacao", "codigo": item["codigo"]} for item in pendencias]
    bloqueios.extend((
        {"grupo": "totalizacao", "codigo": "VNF_NAO_DEFINIDO"},
        {"grupo": "ipi_devolvido", "codigo": "TOTAL_NAO_MODELADO"},
        {"grupo": "ibs_cbs", "codigo": "TOTAL_RTC_NAO_MODELADO"},
        {"grupo": "totalizacao", "codigo": "MAPEAMENTO_XML_PENDENTE"},
        {"grupo": "xml", "codigo": "GERACAO_NAO_IMPLEMENTADA"},
        {"grupo": "transmissao", "codigo": "HOMOLOGACAO_PENDENTE"},
    ))
    return {
        "contrato": CONTRATO_VALIDACAO_TOTALIZACAO,
        "estrutura_valida": not erros,
        "origem_completa": not erros and not pendencias,
        "escopo_fiscal_suportado": False,
        "erros": erros,
        "pendencias": pendencias,
        "bloqueios": bloqueios,
        "permite_gerar_xml": False,
        "permite_emissao": False,
    }
