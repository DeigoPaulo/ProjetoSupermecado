"""Contrato não emissivo de vigência e leiaute IBS/CBS/RTC na devolução."""
from decimal import Decimal, InvalidOperation

from .tributos_itens_devolucao import CONTRATO_TRIBUTOS_ITENS


CONTRATO_RTC = "supplier_return_rtc_vigency_policy_v1"
CONTRATO_VALIDACAO_RTC = "supplier_return_rtc_vigency_policy_validation_v1"
NT_SHA256 = "559fcd7d1b495549099498ff5c1ba4165f65d4b5ad5b34dbe802869d4619d917"
_CAMPOS_FONTES = {
    "tributos_contrato", "memoria_id", "memoria_sha256", "revisao_memoria_sha256",
}
_CAMPOS_ITEM = {
    "nitem_novo", "nitem_original", "item_rascunho_id", "referencia_memoria",
    "classificacao_rtc", "destino_fiscal",
}
_CAMPOS_REFERENCIA = {"ibs", "cbs"}
_CAMPOS_GRUPO = {"estado", "codigo", "base", "aliquota", "valor"}
_CAMPOS_CLASSIFICACAO = {"codigo", "contribuinte_exclusivo_ibs_cbs", "estado"}
_CAMPOS_DESTINO = {"grupo_ibs", "grupo_cbs", "grupo_devolucao_tributos"}
_CAMPOS_POLITICA = {
    "ativar_por_data", "copiar_valores_memoria", "inferir_enquadramento",
    "usar_schema_sem_homologacao", "exige_vigencia_confirmada",
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


def construir_rtc_devolucao(tributos):
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
        for nome in ("ibs", "cbs"):
            grupo = grupos.get(nome, {})
            referencia[nome] = {
                "estado": grupo.get("estado", "VIGENCIA_E_LEIAUTE_PENDENTES"),
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
            "classificacao_rtc": {
                "codigo": "", "contribuinte_exclusivo_ibs_cbs": None,
                "estado": "NAO_CONFIRMADA",
            },
            "destino_fiscal": {
                "grupo_ibs": "", "grupo_cbs": "", "grupo_devolucao_tributos": "",
            },
        })
    conteudo = {
        "contrato": CONTRATO_RTC,
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
        "totais": {"ibs": "", "cbs": "", "rtc": "", "estado": "NAO_DEFINIDO"},
        "evidencia_normativa": {
            "documento": "NT_2026_007_V1_00",
            "sha256": NT_SHA256,
            "paginas_analisadas": [3, 7],
            "homologacao_documental": "2026-09-01",
            "producao_documental": "2026-11-03",
            "leitura_integral_concluida": False,
            "implantacao_go_confirmada": False,
            "leiaute_aplicavel_confirmado": False,
        },
        "politica": {
            "ativar_por_data": False,
            "copiar_valores_memoria": False,
            "inferir_enquadramento": False,
            "usar_schema_sem_homologacao": False,
            "exige_vigencia_confirmada": True,
        },
    }
    return {"conteudo": conteudo, "validacao": validar_rtc_devolucao(conteudo)}


def validar_rtc_devolucao(conteudo):
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
        "itens", "totais", "evidencia_normativa", "politica",
    }
    if set(conteudo) != campos:
        erro("$", "CAMPOS_INVALIDOS")
    if conteudo.get("contrato") != CONTRATO_RTC:
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
            for nome in ("ibs", "cbs"):
                grupo = referencia.get(nome)
                grupo_caminho = f"{caminho}.referencia_memoria.{nome}"
                if not isinstance(grupo, dict) or set(grupo) != _CAMPOS_GRUPO:
                    erro(grupo_caminho, "CAMPOS_INVALIDOS")
                    continue
                if grupo.get("estado") != "VIGENCIA_E_LEIAUTE_PENDENTES":
                    erro(f"{grupo_caminho}.estado", "ESTADO_INVALIDO")
                if not isinstance(grupo.get("codigo"), str):
                    erro(f"{grupo_caminho}.codigo", "CODIGO_INVALIDO")
                for campo, casas in (("base", 2), ("aliquota", 4), ("valor", 2)):
                    if not _decimal_exato(grupo.get(campo), casas):
                        pendencia(f"{grupo_caminho}.{campo}", "VALOR_ORIGEM_PENDENTE")
        classificacao = item.get("classificacao_rtc")
        if not isinstance(classificacao, dict) or set(classificacao) != _CAMPOS_CLASSIFICACAO:
            erro(f"{caminho}.classificacao_rtc", "CAMPOS_INVALIDOS")
        elif classificacao != {"codigo": "", "contribuinte_exclusivo_ibs_cbs": None, "estado": "NAO_CONFIRMADA"}:
            erro(f"{caminho}.classificacao_rtc", "CLASSIFICACAO_NAO_CONFIRMADA")
        destino = item.get("destino_fiscal")
        if not isinstance(destino, dict) or set(destino) != _CAMPOS_DESTINO:
            erro(f"{caminho}.destino_fiscal", "CAMPOS_INVALIDOS")
        elif any(destino.get(campo) != "" for campo in _CAMPOS_DESTINO):
            erro(f"{caminho}.destino_fiscal", "GRUPO_RTC_NAO_APROVADO")

    totais = conteudo.get("totais")
    if not isinstance(totais, dict) or set(totais) != {"ibs", "cbs", "rtc", "estado"}:
        erro("totais", "CAMPOS_INVALIDOS")
        totais = {}
    for campo in ("ibs", "cbs", "rtc"):
        if totais.get(campo) != "":
            erro(f"totais.{campo}", "TOTAL_RTC_NAO_APROVADO")
    if totais.get("estado") != "NAO_DEFINIDO":
        erro("totais.estado", "TOTAL_NAO_PODE_SER_ATIVADO")

    evidencia = conteudo.get("evidencia_normativa")
    campos_evidencia = {
        "documento", "sha256", "paginas_analisadas", "homologacao_documental",
        "producao_documental", "leitura_integral_concluida", "implantacao_go_confirmada",
        "leiaute_aplicavel_confirmado",
    }
    if not isinstance(evidencia, dict) or set(evidencia) != campos_evidencia:
        erro("evidencia_normativa", "CAMPOS_INVALIDOS")
        evidencia = {}
    esperados = {
        "documento": "NT_2026_007_V1_00", "sha256": NT_SHA256,
        "paginas_analisadas": [3, 7], "homologacao_documental": "2026-09-01",
        "producao_documental": "2026-11-03",
    }
    for campo, esperado in esperados.items():
        if evidencia.get(campo) != esperado:
            erro(f"evidencia_normativa.{campo}", "EVIDENCIA_INVALIDA")
    for campo in ("leitura_integral_concluida", "implantacao_go_confirmada", "leiaute_aplicavel_confirmado"):
        if evidencia.get(campo) is not False:
            erro(f"evidencia_normativa.{campo}", "CONFIRMACAO_INEXISTENTE")

    politica = conteudo.get("politica")
    if not isinstance(politica, dict) or set(politica) != _CAMPOS_POLITICA:
        erro("politica", "CAMPOS_INVALIDOS")
        politica = {}
    for campo in ("ativar_por_data", "copiar_valores_memoria", "inferir_enquadramento", "usar_schema_sem_homologacao"):
        if politica.get(campo) is not False:
            erro(f"politica.{campo}", "ATIVACAO_AUTOMATICA_PROIBIDA")
    if politica.get("exige_vigencia_confirmada") is not True:
        erro("politica.exige_vigencia_confirmada", "CONFIRMACAO_DE_VIGENCIA_OBRIGATORIA")

    bloqueios = [{"grupo": "ibs_cbs", "codigo": item["codigo"]} for item in pendencias]
    bloqueios.extend((
        {"grupo": "ibs_cbs", "codigo": "VIGENCIA_E_IMPLANTACAO_GO_NAO_CONFIRMADAS"},
        {"grupo": "ibs_cbs", "codigo": "CLASSIFICACAO_E_LEIAUTE_PENDENTES"},
        {"grupo": "ibs_cbs", "codigo": "TOTAIS_RTC_NAO_DEFINIDOS"},
        {"grupo": "xml", "codigo": "GERACAO_NAO_IMPLEMENTADA"},
        {"grupo": "transmissao", "codigo": "HOMOLOGACAO_PENDENTE"},
    ))
    return {
        "contrato": CONTRATO_VALIDACAO_RTC,
        "estrutura_valida": not erros,
        "origem_completa": not erros and not pendencias,
        "vigencia_confirmada": False,
        "escopo_fiscal_suportado": False,
        "erros": erros,
        "pendencias": pendencias,
        "bloqueios": bloqueios,
        "permite_gerar_xml": False,
        "permite_emissao": False,
    }
