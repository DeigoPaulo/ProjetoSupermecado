"""Contrato não emissivo para hipótese de ICMS-ST/FCP na devolução."""
from decimal import Decimal, InvalidOperation

from .tributos_itens_devolucao import CONTRATO_TRIBUTOS_ITENS


CONTRATO_ICMS_ST_FCP = "supplier_return_icms_st_fcp_hypothesis_v1"
CONTRATO_VALIDACAO_ICMS_ST_FCP = "supplier_return_icms_st_fcp_hypothesis_validation_v1"
_CAMPOS_FONTES = {
    "tributos_contrato", "memoria_id", "memoria_sha256", "revisao_memoria_sha256",
}
_CAMPOS_ITEM = {
    "nitem_novo", "nitem_original", "item_rascunho_id", "referencia_memoria",
    "hipotese", "destino_fiscal",
}
_CAMPOS_REFERENCIA = {"icms_st", "fcp"}
_CAMPOS_GRUPO = {"estado", "codigo", "base", "aliquota", "valor"}
_CAMPOS_HIPOTESE = {"codigo", "estado", "aprovacao_especifica"}
_CAMPOS_DESTINO = {"grupo_icms_st", "grupo_fcp", "informacao_complementar_aprovada"}
_CAMPOS_POLITICA = {
    "copiar_valores_memoria", "inferir_por_codigo_icms", "inferir_por_regime",
    "generalizar_orientacao_go", "exige_hipotese_aprovada",
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


def construir_icms_st_fcp(tributos):
    origem_ok = bool(tributos["validacao"].get("origem_completa"))
    itens_origem = tributos["conteudo"].get("itens", []) if origem_ok else []
    ids = {item.get("memoria_id") for item in itens_origem}
    hashes = {item.get("memoria_sha256") for item in itens_origem}
    revisoes = {item.get("revisao_sha256") for item in itens_origem}
    fonte_comum = len(ids) == len(hashes) == len(revisoes) == 1 and next(iter(ids), 0) not in (None, 0)
    itens = []
    for item in tributos["conteudo"].get("itens", []):
        grupos = item.get("grupos", {}) if origem_ok else {}
        referencia = {}
        for nome in ("icms_st", "fcp"):
            grupo = grupos.get(nome, {})
            referencia[nome] = {
                "estado": grupo.get("estado", "HIPOTESE_NAO_CONFIRMADA"),
                "codigo": grupo.get("codigo", ""),
                "base": grupo.get("base", ""),
                "aliquota": grupo.get("aliquota", ""),
                "valor": grupo.get("valor", ""),
            }
        itens.append({
            "nitem_novo": item.get("nitem_novo"),
            "nitem_original": item.get("nitem_original"),
            "item_rascunho_id": item.get("item_rascunho_id"),
            "referencia_memoria": referencia,
            "hipotese": {"codigo": "", "estado": "NAO_DEFINIDA", "aprovacao_especifica": False},
            "destino_fiscal": {
                "grupo_icms_st": "", "grupo_fcp": "",
                "informacao_complementar_aprovada": False,
            },
        })
    conteudo = {
        "contrato": CONTRATO_ICMS_ST_FCP,
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
        "totais": {"icms_st": "", "fcp": "", "estado": "NAO_DEFINIDO"},
        "evidencias_go": {
            "orientacoes": ["GO_21305", "GO_21349"],
            "aplicacao_ao_caso_confirmada": False,
        },
        "politica": {
            "copiar_valores_memoria": False,
            "inferir_por_codigo_icms": False,
            "inferir_por_regime": False,
            "generalizar_orientacao_go": False,
            "exige_hipotese_aprovada": True,
        },
    }
    return {"conteudo": conteudo, "validacao": validar_icms_st_fcp(conteudo)}


def validar_icms_st_fcp(conteudo):
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
        "itens", "totais", "evidencias_go", "politica",
    }
    if set(conteudo) != campos:
        erro("$", "CAMPOS_INVALIDOS")
    if conteudo.get("contrato") != CONTRATO_ICMS_ST_FCP:
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
        referencia = item.get("referencia_memoria")
        if not isinstance(referencia, dict) or set(referencia) != _CAMPOS_REFERENCIA:
            erro(f"{caminho}.referencia_memoria", "GRUPOS_INVALIDOS")
        else:
            for nome in ("icms_st", "fcp"):
                grupo = referencia.get(nome)
                grupo_caminho = f"{caminho}.referencia_memoria.{nome}"
                if not isinstance(grupo, dict) or set(grupo) != _CAMPOS_GRUPO:
                    erro(grupo_caminho, "CAMPOS_INVALIDOS")
                    continue
                if grupo.get("estado") != "HIPOTESE_NAO_CONFIRMADA":
                    erro(f"{grupo_caminho}.estado", "ESTADO_INVALIDO")
                if not isinstance(grupo.get("codigo"), str):
                    erro(f"{grupo_caminho}.codigo", "CODIGO_INVALIDO")
                for campo, casas in (("base", 2), ("aliquota", 4), ("valor", 2)):
                    if not _decimal_exato(grupo.get(campo), casas):
                        pendencia(f"{grupo_caminho}.{campo}", "VALOR_ORIGEM_PENDENTE")
        hipotese = item.get("hipotese")
        if not isinstance(hipotese, dict) or set(hipotese) != _CAMPOS_HIPOTESE:
            erro(f"{caminho}.hipotese", "CAMPOS_INVALIDOS")
        else:
            if hipotese.get("codigo") != "" or hipotese.get("estado") != "NAO_DEFINIDA":
                erro(f"{caminho}.hipotese", "HIPOTESE_NAO_APROVADA")
            if hipotese.get("aprovacao_especifica") is not False:
                erro(f"{caminho}.hipotese.aprovacao_especifica", "APROVACAO_INEXISTENTE")
        destino = item.get("destino_fiscal")
        if not isinstance(destino, dict) or set(destino) != _CAMPOS_DESTINO:
            erro(f"{caminho}.destino_fiscal", "CAMPOS_INVALIDOS")
        else:
            for campo in ("grupo_icms_st", "grupo_fcp"):
                if destino.get(campo) != "":
                    erro(f"{caminho}.destino_fiscal.{campo}", "GRUPO_FISCAL_NAO_APROVADO")
            if destino.get("informacao_complementar_aprovada") is not False:
                erro(f"{caminho}.destino_fiscal.informacao_complementar_aprovada", "TEXTO_FISCAL_NAO_APROVADO")

    totais = conteudo.get("totais")
    if not isinstance(totais, dict) or set(totais) != {"icms_st", "fcp", "estado"}:
        erro("totais", "CAMPOS_INVALIDOS")
        totais = {}
    for campo in ("icms_st", "fcp"):
        if totais.get(campo) != "":
            erro(f"totais.{campo}", "TOTAL_NAO_APROVADO")
    if totais.get("estado") != "NAO_DEFINIDO":
        erro("totais.estado", "TOTAL_NAO_PODE_SER_ATIVADO")

    evidencias = conteudo.get("evidencias_go")
    if not isinstance(evidencias, dict) or set(evidencias) != {"orientacoes", "aplicacao_ao_caso_confirmada"}:
        erro("evidencias_go", "CAMPOS_INVALIDOS")
        evidencias = {}
    if evidencias.get("orientacoes") != ["GO_21305", "GO_21349"]:
        erro("evidencias_go.orientacoes", "EVIDENCIAS_INVALIDAS")
    if evidencias.get("aplicacao_ao_caso_confirmada") is not False:
        erro("evidencias_go.aplicacao_ao_caso_confirmada", "APLICACAO_NAO_CONFIRMADA")

    politica = conteudo.get("politica")
    if not isinstance(politica, dict) or set(politica) != _CAMPOS_POLITICA:
        erro("politica", "CAMPOS_INVALIDOS")
        politica = {}
    for campo in (
        "copiar_valores_memoria", "inferir_por_codigo_icms", "inferir_por_regime",
        "generalizar_orientacao_go",
    ):
        if politica.get(campo) is not False:
            erro(f"politica.{campo}", "INFERENCIA_AUTOMATICA_PROIBIDA")
    if politica.get("exige_hipotese_aprovada") is not True:
        erro("politica.exige_hipotese_aprovada", "APROVACAO_ESPECIFICA_OBRIGATORIA")

    bloqueios = [{"grupo": "icms_st_fcp", "codigo": item["codigo"]} for item in pendencias]
    bloqueios.extend((
        {"grupo": "icms_st_fcp", "codigo": "HIPOTESE_CONTABIL_NAO_APROVADA"},
        {"grupo": "icms_st_fcp", "codigo": "TRATAMENTO_E_TOTAIS_PENDENTES"},
        {"grupo": "icms_st_fcp", "codigo": "MAPEAMENTO_XML_PENDENTE"},
        {"grupo": "xml", "codigo": "GERACAO_NAO_IMPLEMENTADA"},
        {"grupo": "transmissao", "codigo": "HOMOLOGACAO_PENDENTE"},
    ))
    return {
        "contrato": CONTRATO_VALIDACAO_ICMS_ST_FCP,
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
