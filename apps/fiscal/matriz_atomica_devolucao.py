"""Matriz atômica campo, origem, regra e destino XML; nunca serializa."""

from .inventario_dados_devolucao import CAMPOS_ATOMICOS, CONTRATO_INVENTARIO
from .rastreabilidade_leiaute_devolucao import EVIDENCIA_XSD


CONTRATO_MATRIZ_ATOMICA = "supplier_return_atomic_xml_matrix_v1"
CONTRATO_VALIDACAO_MATRIZ_ATOMICA = "supplier_return_atomic_xml_matrix_validation_v1"
REGRAS = {
    "BLOQUEIO": "EXIGIDO_ANTES_DO_GERADOR",
    "CONDICIONADO": "PRESENTE_QUANDO_CONDICAO_APLICAVEL",
    "POLITICA": "SOMENTE_APOS_DECISAO_APROVADA",
}


ESTADOS_INVENTARIO = {
    "DISPONIVEL_NO_CONTRATO", "PARCIALMENTE_DISPONIVEL",
    "CONDICIONADO_NAO_INFORMADO", "NAO_DEFINIDO_POR_POLITICA",
    "AUSENTE_OU_ORIGEM_NAO_APROVADA",
}


def _destino_xml(grupo, campo):
    fixos = {
        ("identidade_partes", "identificacao.natureza_operacao"): "NFe/infNFe/ide/natOp",
        ("identidade_partes", "identificacao.codigo_municipio_fato_gerador"): "NFe/infNFe/ide/cMunFG",
        ("identidade_partes", "identificacao.destino_operacao"): "NFe/infNFe/ide/idDest",
        ("identidade_partes", "identificacao.consumidor_final"): "NFe/infNFe/ide/indFinal",
        ("identidade_partes", "identificacao.presenca_comprador"): "NFe/infNFe/ide/indPres",
        ("identidade_partes", "destinatario.indicador_ie_candidato"): "NFe/infNFe/dest/indIEDest",
        ("referencias_itens", "itens[].chave_acesso"): "NFe/infNFe/det/DFeReferenciado/chaveAcesso",
        ("referencias_itens", "itens[].nitem_original"): "NFe/infNFe/det/DFeReferenciado/nItem",
        ("tributos_itens", "itens[].grupos.icms.modalidade_base_candidata"): "NFe/infNFe/det/imposto/ICMS/*/modBC",
        ("tributos_itens", "itens[].grupos.icms.reducao_base_candidata"): "NFe/infNFe/det/imposto/ICMS/*/pRedBC",
        ("tributos_itens", "itens[].grupos.pis.variante_candidata"): "NFe/infNFe/det/imposto/PIS/(PISAliq|PISQtde|PISNT|PISOutr)",
        ("tributos_itens", "itens[].grupos.pis.modalidade_calculo_candidata"): "NFe/infNFe/det/imposto/PIS/*/(vBC|pPIS|qBCProd|vAliqProd)",
        ("tributos_itens", "itens[].grupos.cofins.variante_candidata"): "NFe/infNFe/det/imposto/COFINS/(COFINSAliq|COFINSQtde|COFINSNT|COFINSOutr)",
        ("tributos_itens", "itens[].grupos.cofins.modalidade_calculo_candidata"): "NFe/infNFe/det/imposto/COFINS/*/(vBC|pCOFINS|qBCProd|vAliqProd)",
        ("totalizacao", "totais_fiscais_nao_definidos.valor_nota"): "NFe/infNFe/total/ICMSTot/vNF",
        ("pagamento_fiscal", "politica.tpag"): "NFe/infNFe/pag/detPag/tPag",
        ("pagamento_fiscal", "politica.vpag"): "NFe/infNFe/pag/detPag/vPag",
        ("observacoes_fiscais", "textos_fiscais.infadic"): "NFe/infNFe/infAdic/infCpl",
        ("observacoes_fiscais", "textos_fiscais.itens[].infadprod"): "NFe/infNFe/det/infAdProd",
        ("ipi_devolvido", "itens[].enquadramento_ipi.valor_candidato"): "NFe/infNFe/det/imposto/IPI/cEnq",
        ("ipi_devolvido", "itens[].imposto_devol.pdevol"): "NFe/infNFe/det/impostoDevol/pDevol",
        ("ipi_devolvido", "itens[].imposto_devol.vipidevol"): "NFe/infNFe/det/impostoDevol/IPI/vIPIDevol",
        ("ipi_devolvido", "total.vipidevol"): "NFe/infNFe/total/ICMSTot/vIPIDevol",
        ("icms_st_fcp", "itens[].hipotese.codigo"): "NFe/infNFe/det/imposto/ICMS/*/(CST|CSOSN)",
        ("icms_st_fcp", "itens[].destino_fiscal.grupo_icms_st"): "NFe/infNFe/det/imposto/ICMS/*/(vBCST|pICMSST|vICMSST)",
        ("icms_st_fcp", "itens[].destino_fiscal.grupo_fcp"): "NFe/infNFe/det/imposto/ICMS/*/(vBCFCP|pFCP|vFCP|vBCFCPST|pFCPST|vFCPST)",
        ("icms_st_fcp", "totais.icms_st"): "NFe/infNFe/total/ICMSTot/vST",
        ("icms_st_fcp", "totais.fcp"): "NFe/infNFe/total/ICMSTot/(vFCP|vFCPST)",
        ("rtc", "itens[].classificacao_rtc.codigo"): "NFe/infNFe/det/imposto/IBSCBS/[LEIAUTE_RTC_PENDENTE]",
        ("rtc", "itens[].classificacao_rtc.contribuinte_exclusivo_ibs_cbs"): "NFe/infNFe/det/imposto/IBSCBS/[LEIAUTE_RTC_PENDENTE]",
        ("rtc", "itens[].destino_fiscal.grupo_ibs"): "NFe/infNFe/det/imposto/IBSCBS/[GRUPO_IBS_PENDENTE]",
        ("rtc", "itens[].destino_fiscal.grupo_cbs"): "NFe/infNFe/det/imposto/IBSCBS/[GRUPO_CBS_PENDENTE]",
        ("rtc", "itens[].destino_fiscal.grupo_devolucao_tributos"): "NFe/infNFe/det/imposto/IBSCBS/[GRUPO_DEVOLUCAO_RTC_PENDENTE]",
        ("rtc", "totais.ibs"): "NFe/infNFe/total/IBSCBSTot/[TOTAL_IBS_PENDENTE]",
        ("rtc", "totais.cbs"): "NFe/infNFe/total/IBSCBSTot/[TOTAL_CBS_PENDENTE]",
        ("rtc", "totais.rtc"): "NFe/infNFe/total/IBSCBSTot/[LEIAUTE_RTC_PENDENTE]",
    }
    if (grupo, campo) in fixos:
        return fixos[(grupo, campo)]

    if grupo == "identidade_partes":
        prefixo, nome = campo.split(".", 1)
        tags = {
            "cnpj": "CNPJ", "razao_social": "xNome", "inscricao_estadual": "IE",
            "crt": "CRT", "logradouro": "xLgr", "numero": "nro", "bairro": "xBairro",
            "codigo_municipio": "cMun", "municipio": "xMun", "uf": "UF", "cep": "CEP",
        }
        endereco = nome in {"logradouro", "numero", "bairro", "codigo_municipio", "municipio", "uf", "cep"}
        bloco = "emit" if prefixo == "emitente" else "dest"
        subgrupo = "/enderEmit" if bloco == "emit" and endereco else "/enderDest" if endereco else ""
        return f"NFe/infNFe/{bloco}{subgrupo}/{tags[nome]}"

    if grupo == "produtos":
        nome = campo.rsplit(".", 1)[-1]
        tags = {
            "codigo_produto": "cProd", "ean": "cEAN", "ean_tributavel": "cEANTrib",
            "descricao": "xProd", "ncm": "NCM", "cest": "CEST", "cfop": "CFOP",
            "unidade_comercial": "uCom", "quantidade_comercial": "qCom",
            "valor_unitario_comercial": "vUnCom", "valor_produtos": "vProd",
            "unidade_tributavel": "uTrib", "quantidade_tributavel": "qTrib",
            "valor_unitario_tributavel": "vUnTrib", "codigo_cbenef": "cBenef",
            "inclui_total_candidato": "indTot",
        }
        especiais = {
            "tipo_codigo_icms": "NFe/infNFe/det/imposto/ICMS/*/(CST|CSOSN)",
            "origem_icms": "NFe/infNFe/det/imposto/ICMS/*/orig",
            "codigo_icms": "NFe/infNFe/det/imposto/ICMS/*/(CST|CSOSN)",
            "codigo_ipi": "NFe/infNFe/det/imposto/IPI/*/CST",
            "codigo_pis": "NFe/infNFe/det/imposto/PIS/*/CST",
            "codigo_cofins": "NFe/infNFe/det/imposto/COFINS/*/CST",
        }
        if nome in especiais:
            return especiais[nome]
        return f"NFe/infNFe/det/prod/{tags[nome]}"

    if grupo == "tributos_itens":
        tributo, nome = campo.split(".")[-2:]
        tags = {
            "icms": {"base": "vBC", "aliquota": "pICMS", "valor": "vICMS"},
            "pis": {"base": "vBC|qBCProd", "aliquota": "pPIS|vAliqProd", "valor": "vPIS"},
            "cofins": {"base": "vBC|qBCProd", "aliquota": "pCOFINS|vAliqProd", "valor": "vCOFINS"},
        }
        return f"NFe/infNFe/det/imposto/{tributo.upper()}/*/{tags[tributo][nome]}"

    if grupo == "ajustes_comerciais":
        tags = {"frete": "vFrete", "seguro": "vSeg", "outras_despesas": "vOutro", "desconto": "vDesc"}
        return f"NFe/infNFe/det/prod/{tags[campo.rsplit('.', 1)[-1]]}"

    if grupo == "transporte":
        tags = {
            "modalidade": "modFrete", "nome": "transporta/xNome", "documento": "transporta/(CNPJ|CPF)",
            "inscricao_estadual": "transporta/IE", "endereco": "transporta/xEnder",
            "municipio": "transporta/xMun", "uf": "transporta/UF",
            "quantidade_volumes": "vol/qVol", "peso_liquido": "vol/pesoL", "peso_bruto": "vol/pesoB",
        }
        return f"NFe/infNFe/transp/{tags[campo.rsplit('.', 1)[-1]]}"

    if grupo == "totalizacao":
        nome = campo.rsplit(".", 1)[-1]
        if "totais_comerciais" in campo:
            tag = {
                "valor_produtos": "vProd", "valor_base": "vProd", "frete": "vFrete",
                "seguro": "vSeg", "outras_despesas": "vOutro", "desconto": "vDesc",
                "total_informado": "vNF",
            }[nome]
        else:
            tributo = campo.split(".")[-2]
            tag = {
                ("icms", "base"): "vBC", ("icms", "valor"): "vICMS",
                ("pis", "base"): "SEM_CAMPO_TOTAL_ESPECIFICO", ("pis", "valor"): "vPIS",
                ("cofins", "base"): "SEM_CAMPO_TOTAL_ESPECIFICO", ("cofins", "valor"): "vCOFINS",
            }[(tributo, nome)]
        return f"NFe/infNFe/total/ICMSTot/{tag}"
    return ""


def construir_matriz_atomica_devolucao(inventario):
    conteudo_inventario = inventario.get("conteudo", {}) if isinstance(inventario, dict) else {}
    itens_inventario = conteudo_inventario.get("itens", [])
    itens_por_chave = {
        (item.get("grupo"), item.get("campo")): item
        for item in itens_inventario if isinstance(item, dict)
    }
    itens = []
    for grupo, campo, fonte, tratamento in CAMPOS_ATOMICOS:
        inventariado = itens_por_chave.get((grupo, campo), {})
        itens.append({
            "grupo": grupo,
            "campo": campo,
            "fonte_primaria": fonte,
            "tratamento_ausencia": tratamento,
            "regra_aplicacao": REGRAS[tratamento],
            "destino_xml_futuro": _destino_xml(grupo, campo),
            "estado_inventario": inventariado.get("estado", "INVENTARIO_AUSENTE"),
            "serializacao_implementada": False,
        })
    conteudo = {
        "contrato": CONTRATO_MATRIZ_ATOMICA,
        "operacao": "DEVOLUCAO_COMPRA",
        "contrato_inventario": conteudo_inventario.get("contrato", ""),
        "evidencia_xsd": dict(EVIDENCIA_XSD),
        "itens": itens,
        "politica": {
            "inferir_decisao_fiscal": False,
            "permitir_serializacao": False,
            "permitir_focus": False,
            "permitir_sefaz_direta": False,
            "permitir_emissao": False,
        },
    }
    return {"conteudo": conteudo, "validacao": validar_matriz_atomica_devolucao(conteudo)}


def validar_matriz_atomica_devolucao(conteudo):
    erros = []

    def erro(caminho, codigo):
        erros.append({"caminho": caminho, "codigo": codigo})

    if not isinstance(conteudo, dict):
        conteudo = {}
        erro("$", "OBJETO_OBRIGATORIO")
    if set(conteudo) != {"contrato", "operacao", "contrato_inventario", "evidencia_xsd", "itens", "politica"}:
        erro("$", "CAMPOS_INVALIDOS")
    if conteudo.get("contrato") != CONTRATO_MATRIZ_ATOMICA:
        erro("contrato", "CONTRATO_INVALIDO")
    if conteudo.get("operacao") != "DEVOLUCAO_COMPRA":
        erro("operacao", "OPERACAO_NAO_SUPORTADA")
    if conteudo.get("contrato_inventario") != CONTRATO_INVENTARIO:
        erro("contrato_inventario", "INVENTARIO_INVALIDO")
    if conteudo.get("evidencia_xsd") != EVIDENCIA_XSD:
        erro("evidencia_xsd", "EVIDENCIA_INVALIDA")
    itens = conteudo.get("itens")
    if not isinstance(itens, list) or len(itens) != len(CAMPOS_ATOMICOS):
        erro("itens", "MATRIZ_INCOMPLETA")
        itens = []
    vistos = set()
    for indice, esperado in enumerate(CAMPOS_ATOMICOS):
        item = itens[indice] if indice < len(itens) else {}
        caminho = f"itens.{indice}"
        campos = {
            "grupo", "campo", "fonte_primaria", "tratamento_ausencia",
            "regra_aplicacao", "destino_xml_futuro", "estado_inventario",
            "serializacao_implementada",
        }
        if not isinstance(item, dict) or set(item) != campos:
            erro(caminho, "ITEM_INVALIDO")
            continue
        grupo, campo, fonte, tratamento = esperado
        if (item["grupo"], item["campo"], item["fonte_primaria"], item["tratamento_ausencia"]) != esperado:
            erro(caminho, "DEFINICAO_DIVERGENTE")
        if item["regra_aplicacao"] != REGRAS[tratamento]:
            erro(caminho, "REGRA_DIVERGENTE")
        if item["destino_xml_futuro"] != _destino_xml(grupo, campo) or not item["destino_xml_futuro"].startswith("NFe/infNFe/"):
            erro(caminho, "DESTINO_XML_DIVERGENTE")
        identidade = (item["grupo"], item["campo"])
        if identidade in vistos:
            erro(caminho, "CAMPO_DUPLICADO")
        vistos.add(identidade)
        if item["estado_inventario"] not in ESTADOS_INVENTARIO:
            erro(caminho, "ESTADO_INVENTARIO_INVALIDO")
        if item["serializacao_implementada"] is not False:
            erro(caminho, "SERIALIZACAO_ANTECIPADA_PROIBIDA")
    politica = {
        "inferir_decisao_fiscal": False, "permitir_serializacao": False,
        "permitir_focus": False, "permitir_sefaz_direta": False, "permitir_emissao": False,
    }
    if conteudo.get("politica") != politica:
        erro("politica", "POLITICA_DE_BLOQUEIO_INVALIDA")
    return {
        "contrato": CONTRATO_VALIDACAO_MATRIZ_ATOMICA,
        "estrutura_valida": not erros,
        "quantidade_campos": len(itens),
        "quantidade_destinos_documentados": sum(
            isinstance(item, dict) and bool(item.get("destino_xml_futuro")) for item in itens
        ),
        "erros": erros,
        "permite_gerar_xml": False,
        "permite_focus": False,
        "permite_sefaz_direta": False,
        "permite_emissao": False,
    }
