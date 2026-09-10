"""Classifica requisitos dos campos da devolução sem autorizar serialização."""

from .rastreabilidade_leiaute_devolucao import construir_rastreabilidade_leiaute_devolucao


CONTRATO_OBRIGATORIEDADE = "supplier_return_field_requirement_matrix_v1"
CONTRATO_VALIDACAO_OBRIGATORIEDADE = "supplier_return_field_requirement_matrix_validation_v1"

XSD = "XSD_PL_010F_LEIAUTE_NFE_4_00"
MOC = "MOC_7_ANEXO_I_P57_58_62_125_126"
NT_REF = "NT_2025_002_V1_51_P71_72"
NT_RTC = "NT_2025_002_V1_51_E_NT_2026_007_V1_00"
GO_ST = "ORIENTACOES_GO_21305_21349"
CONTADOR = "DECISAO_CONTADOR_CASO_CONCRETO"


def _r(categoria, cardinalidade, fontes, *, contador=False, vigencia=False):
    return {
        "categoria": categoria,
        "cardinalidade_xsd": cardinalidade,
        "fontes": list(fontes),
        "exige_decisao_contador": contador,
        "vigencia_operacional_confirmada": False if vigencia else None,
        "aplicacao_operacional": False,
    }


CLASSIFICACOES = {
    ("envelope", "modelo"): _r("OBRIGATORIO_ESTRUTURAL", "1-1", (XSD,)),
    ("envelope", "operacao"): _r("OBRIGATORIO_ESTRUTURAL", "1-1", (XSD, MOC)),
    ("referencias_itens", "itens[].chave_acesso"): _r("OBRIGATORIO_REGRA_CONTEXTO", "0-1/1-1", (XSD, NT_REF), vigencia=True),
    ("referencias_itens", "itens[].nitem_original"): _r("OBRIGATORIO_REGRA_CONTEXTO", "0-1/1-1", (XSD, NT_REF), vigencia=True),
    ("identidade_partes", "identificacao.natureza_operacao"): _r("OBRIGATORIO_ESTRUTURAL", "1-1", (XSD,), contador=True),
    ("identidade_partes", "identificacao.finalidade"): _r("OBRIGATORIO_ESTRUTURAL", "1-1", (XSD, MOC)),
    ("identidade_partes", "identificacao.tipo_operacao"): _r("OBRIGATORIO_ESTRUTURAL", "1-1", (XSD, NT_REF)),
    ("identidade_partes", "emitente"): _r("OBRIGATORIO_ESTRUTURAL", "1-1", (XSD, NT_RTC), contador=True, vigencia=True),
    ("identidade_partes", "destinatario"): _r("OBRIGATORIO_REGRA_CONTEXTO", "0-1", (XSD, NT_REF), contador=True, vigencia=True),
    ("produtos", "itens[].identidade"): _r("MISTO_SUBCAMPOS", "MISTA", (XSD,)),
    ("produtos", "itens[].classificacao"): _r("MISTO_SUBCAMPOS", "MISTA", (XSD, NT_RTC), contador=True, vigencia=True),
    ("produtos", "itens[].quantidades_valores"): _r("OBRIGATORIO_ESTRUTURAL", "MISTA", (XSD,)),
    ("tributos_itens", "itens[].grupos.icms"): _r("CONDICIONADO_ENQUADRAMENTO", "MISTA", (XSD, NT_RTC, CONTADOR), contador=True, vigencia=True),
    ("tributos_itens", "itens[].grupos.pis"): _r("CONDICIONADO_ENQUADRAMENTO", "MISTA", (XSD, CONTADOR), contador=True),
    ("tributos_itens", "itens[].grupos.cofins"): _r("CONDICIONADO_ENQUADRAMENTO", "MISTA", (XSD, CONTADOR), contador=True),
    ("ajustes_comerciais", "itens[].frete"): _r("CONDICIONADO_VALOR", "0-1", (XSD, CONTADOR), contador=True),
    ("ajustes_comerciais", "itens[].seguro"): _r("CONDICIONADO_VALOR", "0-1", (XSD, CONTADOR), contador=True),
    ("ajustes_comerciais", "itens[].outras_despesas"): _r("CONDICIONADO_VALOR", "0-1", (XSD, CONTADOR), contador=True),
    ("ajustes_comerciais", "itens[].desconto"): _r("CONDICIONADO_VALOR", "0-1", (XSD, CONTADOR), contador=True),
    ("transporte", "dados.modalidade"): _r("OBRIGATORIO_ESTRUTURAL", "1-1", (XSD,)),
    ("transporte", "dados.transportador"): _r("CONDICIONADO_MODALIDADE", "0-1", (XSD,)),
    ("transporte", "dados.volumes_pesos"): _r("CONDICIONADO_PRESENCA", "0-N", (XSD,)),
    ("totalizacao", "totais_comerciais"): _r("OBRIGATORIO_ESTRUTURAL", "1-1/MISTA", (XSD, MOC), contador=True),
    ("totalizacao", "totais_tributarios_informados"): _r("CONDICIONADO_ENQUADRAMENTO", "MISTA", (XSD, MOC, CONTADOR), contador=True),
    ("totalizacao", "totais_fiscais_nao_definidos"): _r("PENDENTE_HIPOTESES", "MISTA", (XSD, MOC, NT_RTC, CONTADOR), contador=True, vigencia=True),
    ("pagamento_fiscal", "politica.tpag"): _r("OBRIGATORIO_REGRA_CONTEXTO", "1-1", (XSD, MOC)),
    ("pagamento_fiscal", "politica.vpag"): _r("OBRIGATORIO_REGRA_CONTEXTO", "1-1", (XSD, MOC)),
    ("observacoes_fiscais", "textos_fiscais.infadic"): _r("OPCIONAL_CONTROLADO", "0-1", (XSD, CONTADOR), contador=True),
    ("observacoes_fiscais", "textos_fiscais.itens[].infadprod"): _r("CONDICIONADO_HIPOTESE", "0-1", (XSD, MOC, CONTADOR), contador=True),
    ("ipi_devolvido", "itens[].enquadramento_ipi.valor_candidato"): _r("CONDICIONADO_GRUPO_IPI", "1-1_DENTRO_IPI", (XSD, CONTADOR), contador=True),
    ("ipi_devolvido", "itens[].imposto_devol.pdevol"): _r("CONDICIONADO_HIPOTESE", "0-1/1-1", (XSD, MOC, CONTADOR), contador=True),
    ("ipi_devolvido", "itens[].imposto_devol.vipidevol"): _r("CONDICIONADO_HIPOTESE", "0-1/1-1", (XSD, MOC, CONTADOR), contador=True),
    ("ipi_devolvido", "total.vipidevol"): _r("CONDICIONADO_HIPOTESE", "1-1", (XSD, MOC, CONTADOR), contador=True),
    ("icms_st_fcp", "itens[].destino_fiscal"): _r("PENDENTE_HIPOTESES", "MISTA", (XSD, GO_ST, CONTADOR), contador=True),
    ("icms_st_fcp", "totais.icms_st_fcp"): _r("PENDENTE_HIPOTESES", "MISTA", (XSD, GO_ST, CONTADOR), contador=True),
    ("rtc", "itens[].classificacao_rtc"): _r("PENDENTE_VIGENCIA_E_ENQUADRAMENTO", "MISTA", (XSD, NT_RTC, CONTADOR), contador=True, vigencia=True),
    ("rtc", "itens[].destino_fiscal"): _r("PENDENTE_VIGENCIA_E_ENQUADRAMENTO", "MISTA", (XSD, NT_RTC, CONTADOR), contador=True, vigencia=True),
    ("rtc", "totais.rtc"): _r("PENDENTE_VIGENCIA_E_ENQUADRAMENTO", "0-1/CONDICIONADO", (XSD, NT_RTC, CONTADOR), contador=True, vigencia=True),
}


def construir_obrigatoriedade_campos_devolucao():
    rastreabilidade = construir_rastreabilidade_leiaute_devolucao()["conteudo"]
    itens = []
    for grupo in rastreabilidade["grupos"]:
        for campo in grupo["campos"]:
            chave = (grupo["grupo"], campo["origem_contrato"])
            itens.append({
                "grupo": chave[0],
                "origem_contrato": chave[1],
                "destino_xsd": campo["destino_xsd"],
                **CLASSIFICACOES[chave],
            })
    conteudo = {
        "contrato": CONTRATO_OBRIGATORIEDADE,
        "operacao": "DEVOLUCAO_COMPRA",
        "escopo": {
            "modelo": "55",
            "finalidade": "4",
            "tipo_operacao": "1",
            "uma_nfe_origem": True,
            "analise_normativa_integral": False,
            "vigencia_go_confirmada": False,
            "caso_real_contador_aprovado": False,
        },
        "itens": itens,
        "politica": {
            "inferir_obrigatoriedade_por_xsd_isolado": False,
            "permitir_serializacao": False,
            "permitir_focus": False,
            "permitir_sefaz_direta": False,
            "permitir_emissao": False,
        },
    }
    return {"conteudo": conteudo, "validacao": validar_obrigatoriedade_campos_devolucao(conteudo)}


def validar_obrigatoriedade_campos_devolucao(conteudo):
    erros = []

    def erro(caminho, codigo):
        erros.append({"caminho": caminho, "codigo": codigo})

    if not isinstance(conteudo, dict):
        erro("$", "OBJETO_OBRIGATORIO")
        conteudo = {}
    if set(conteudo) != {"contrato", "operacao", "escopo", "itens", "politica"}:
        erro("$", "CAMPOS_INVALIDOS")
    if conteudo.get("contrato") != CONTRATO_OBRIGATORIEDADE:
        erro("contrato", "CONTRATO_INVALIDO")
    if conteudo.get("operacao") != "DEVOLUCAO_COMPRA":
        erro("operacao", "OPERACAO_NAO_SUPORTADA")
    escopo_esperado = {
        "modelo": "55", "finalidade": "4", "tipo_operacao": "1",
        "uma_nfe_origem": True, "analise_normativa_integral": False,
        "vigencia_go_confirmada": False, "caso_real_contador_aprovado": False,
    }
    if conteudo.get("escopo") != escopo_esperado:
        erro("escopo", "ESCOPO_OU_APROVACAO_ANTECIPADA")

    itens = conteudo.get("itens")
    if not isinstance(itens, list) or len(itens) != len(CLASSIFICACOES):
        erro("itens", "CLASSIFICACAO_INCOMPLETA")
        itens = []
    rastreabilidade = construir_rastreabilidade_leiaute_devolucao()["conteudo"]
    campos_esperados = [
        (grupo["grupo"], campo["origem_contrato"], campo["destino_xsd"])
        for grupo in rastreabilidade["grupos"] for campo in grupo["campos"]
    ]
    for indice, esperado in enumerate(campos_esperados):
        caminho = f"itens.{indice}"
        item = itens[indice] if indice < len(itens) else {}
        if not isinstance(item, dict) or set(item) != {
            "grupo", "origem_contrato", "destino_xsd", "categoria",
            "cardinalidade_xsd", "fontes", "exige_decisao_contador",
            "vigencia_operacional_confirmada", "aplicacao_operacional",
        }:
            erro(caminho, "ITEM_INVALIDO")
            continue
        if (item["grupo"], item["origem_contrato"], item["destino_xsd"]) != esperado:
            erro(caminho, "RASTREABILIDADE_DIVERGENTE")
            continue
        classificacao = CLASSIFICACOES[(esperado[0], esperado[1])]
        for chave, valor in classificacao.items():
            if item[chave] != valor:
                erro(f"{caminho}.{chave}", "CLASSIFICACAO_DIVERGENTE")
        if item["aplicacao_operacional"] is not False:
            erro(f"{caminho}.aplicacao_operacional", "APLICACAO_ANTECIPADA_PROIBIDA")

    politica_esperada = {
        "inferir_obrigatoriedade_por_xsd_isolado": False,
        "permitir_serializacao": False,
        "permitir_focus": False,
        "permitir_sefaz_direta": False,
        "permitir_emissao": False,
    }
    if conteudo.get("politica") != politica_esperada:
        erro("politica", "POLITICA_DE_BLOQUEIO_INVALIDA")
    pendentes = sum(
        item.get("categoria", "").startswith("PENDENTE_")
        or item.get("vigencia_operacional_confirmada") is False
        for item in itens if isinstance(item, dict)
    )
    return {
        "contrato": CONTRATO_VALIDACAO_OBRIGATORIEDADE,
        "estrutura_valida": not erros,
        "quantidade_campos": len(itens),
        "quantidade_pendentes": pendentes,
        "analise_normativa_integral": False,
        "erros": erros,
        "permite_gerar_xml": False,
        "permite_focus": False,
        "permite_sefaz_direta": False,
        "permite_emissao": False,
    }
