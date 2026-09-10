"""Política fiscal não emissiva de pagamento para devolução de compra."""


CONTRATO_PAGAMENTO = "supplier_return_fiscal_payment_policy_v1"
CONTRATO_VALIDACAO_PAGAMENTO = "supplier_return_fiscal_payment_policy_validation_v1"
_CAMPOS_POLITICA = {"tpag", "vpag", "usa_total_comercial", "estado"}
_CAMPOS_EFEITOS = {
    "gerar_titulo", "movimentar_caixa", "acionar_meio_pagamento", "calcular_troco",
}
_CAMPOS_EVIDENCIA = {"documento", "regras", "confirmacao_complementar_pendente"}


def construir_politica_pagamento_devolucao():
    conteudo = {
        "contrato": CONTRATO_PAGAMENTO,
        "operacao": "DEVOLUCAO_COMPRA",
        "modelo": "55",
        "finalidade": "4",
        "permite_emissao": False,
        "politica": {
            "tpag": "90",
            "vpag": "0.00",
            "usa_total_comercial": False,
            "estado": "SEM_PAGAMENTO_FISCAL",
        },
        "efeitos_operacionais": {
            "gerar_titulo": False,
            "movimentar_caixa": False,
            "acionar_meio_pagamento": False,
            "calcular_troco": False,
        },
        "evidencia_documental": {
            "documento": "MOC_7_0_ANEXO_I",
            "regras": ["YA02_04_871", "YA03_30_904"],
            "confirmacao_complementar_pendente": True,
        },
    }
    return {"conteudo": conteudo, "validacao": validar_politica_pagamento_devolucao(conteudo)}


def validar_politica_pagamento_devolucao(conteudo):
    erros = []

    def erro(caminho, codigo):
        erros.append({"caminho": caminho, "codigo": codigo})

    if not isinstance(conteudo, dict):
        erro("$", "OBJETO_OBRIGATORIO")
        conteudo = {}
    campos = {
        "contrato", "operacao", "modelo", "finalidade", "permite_emissao",
        "politica", "efeitos_operacionais", "evidencia_documental",
    }
    if set(conteudo) != campos:
        erro("$", "CAMPOS_INVALIDOS")
    for campo, esperado in (
        ("contrato", CONTRATO_PAGAMENTO),
        ("operacao", "DEVOLUCAO_COMPRA"),
        ("modelo", "55"),
        ("finalidade", "4"),
    ):
        if conteudo.get(campo) != esperado:
            erro(campo, "VALOR_NAO_SUPORTADO")
    if conteudo.get("permite_emissao") is not False:
        erro("permite_emissao", "EMISSAO_PROIBIDA")

    politica = conteudo.get("politica")
    if not isinstance(politica, dict) or set(politica) != _CAMPOS_POLITICA:
        erro("politica", "CAMPOS_INVALIDOS")
        politica = {}
    if politica.get("tpag") != "90":
        erro("politica.tpag", "SOMENTE_SEM_PAGAMENTO_PERMITIDO")
    if politica.get("vpag") != "0.00":
        erro("politica.vpag", "SEM_PAGAMENTO_EXIGE_VALOR_ZERO")
    if politica.get("usa_total_comercial") is not False:
        erro("politica.usa_total_comercial", "TOTAL_COMERCIAL_NAO_PODE_ALIMENTAR_PAGAMENTO")
    if politica.get("estado") != "SEM_PAGAMENTO_FISCAL":
        erro("politica.estado", "ESTADO_INVALIDO")

    efeitos = conteudo.get("efeitos_operacionais")
    if not isinstance(efeitos, dict) or set(efeitos) != _CAMPOS_EFEITOS:
        erro("efeitos_operacionais", "CAMPOS_INVALIDOS")
        efeitos = {}
    for campo in _CAMPOS_EFEITOS:
        if efeitos.get(campo) is not False:
            erro(f"efeitos_operacionais.{campo}", "EFEITO_OPERACIONAL_PROIBIDO")

    evidencia = conteudo.get("evidencia_documental")
    if not isinstance(evidencia, dict) or set(evidencia) != _CAMPOS_EVIDENCIA:
        erro("evidencia_documental", "CAMPOS_INVALIDOS")
        evidencia = {}
    if evidencia.get("documento") != "MOC_7_0_ANEXO_I":
        erro("evidencia_documental.documento", "FONTE_INVALIDA")
    if evidencia.get("regras") != ["YA02_04_871", "YA03_30_904"]:
        erro("evidencia_documental.regras", "REGRAS_INVALIDAS")
    if evidencia.get("confirmacao_complementar_pendente") is not True:
        erro("evidencia_documental.confirmacao_complementar_pendente", "PENDENCIA_NAO_PODE_SER_REMOVIDA")

    bloqueios = [
        {"grupo": "pagamento", "codigo": "REGRAS_COMPLEMENTARES_PENDENTES"},
        {"grupo": "pagamento", "codigo": "MAPEAMENTO_XML_PENDENTE"},
        {"grupo": "xml", "codigo": "GERACAO_NAO_IMPLEMENTADA"},
        {"grupo": "transmissao", "codigo": "HOMOLOGACAO_PENDENTE"},
    ]
    return {
        "contrato": CONTRATO_VALIDACAO_PAGAMENTO,
        "estrutura_valida": not erros,
        "dados_completos": not erros,
        "escopo_fiscal_suportado": False,
        "erros": erros,
        "bloqueios": bloqueios,
        "permite_gerar_xml": False,
        "permite_emissao": False,
    }
