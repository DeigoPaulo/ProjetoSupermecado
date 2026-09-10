"""Inventário atômico, sem valores sensíveis, dos dados da devolução."""


CONTRATO_INVENTARIO = "supplier_return_atomic_data_inventory_v1"
CONTRATO_VALIDACAO_INVENTARIO = "supplier_return_atomic_data_inventory_validation_v1"
TRATAMENTOS = {"BLOQUEIO", "CONDICIONADO", "POLITICA"}


def _definicoes():
    campos = [
        ("identidade_partes", "identificacao.natureza_operacao", "PARECER_CONTADOR", "BLOQUEIO"),
        ("identidade_partes", "identificacao.codigo_municipio_fato_gerador", "CADASTRO_FILIAL", "BLOQUEIO"),
        ("identidade_partes", "identificacao.destino_operacao", "FILIAL_E_XML_ORIGINAL", "BLOQUEIO"),
        ("identidade_partes", "identificacao.consumidor_final", "DECISAO_FISCAL", "BLOQUEIO"),
        ("identidade_partes", "identificacao.presenca_comprador", "DECISAO_FISCAL", "BLOQUEIO"),
    ]
    campos += [
        ("identidade_partes", f"emitente.{nome}", "CADASTRO_FILIAL_E_CONFIGURACAO", "BLOQUEIO")
        for nome in (
            "cnpj", "razao_social", "inscricao_estadual", "crt", "logradouro", "numero",
            "bairro", "codigo_municipio", "municipio", "uf", "cep",
        )
    ]
    campos += [
        ("identidade_partes", f"destinatario.{nome}", "XML_ORIGINAL", "BLOQUEIO")
        for nome in (
            "cnpj", "razao_social", "inscricao_estadual", "logradouro", "numero",
            "bairro", "codigo_municipio", "municipio", "uf", "cep",
        )
    ]
    campos.append((
        "identidade_partes", "destinatario.indicador_ie_candidato",
        "CADASTRO_FORNECEDOR_ATUAL", "BLOQUEIO",
    ))
    campos += [
        ("referencias_itens", "itens[].chave_acesso", "XML_ORIGINAL_E_DOSSIE", "BLOQUEIO"),
        ("referencias_itens", "itens[].nitem_original", "XML_ORIGINAL_E_RASCUNHO", "BLOQUEIO"),
    ]
    fontes_produtos = {
        "codigo_produto": "XML_ORIGINAL", "ean": "XML_ORIGINAL", "ean_tributavel": "XML_ORIGINAL",
        "descricao": "XML_ORIGINAL", "ncm": "XML_ORIGINAL", "cest": "XML_ORIGINAL",
        "cfop": "PARECER_CONTADOR", "unidade_comercial": "XML_ORIGINAL",
        "quantidade_comercial": "RASCUNHO", "valor_unitario_comercial": "XML_ORIGINAL_E_MEMORIA",
        "valor_produtos": "MEMORIA_APROVADA", "unidade_tributavel": "XML_ORIGINAL",
        "quantidade_tributavel": "XML_ORIGINAL", "valor_unitario_tributavel": "XML_ORIGINAL",
        "tipo_codigo_icms": "PARAMETRIZACAO_CONTADOR", "origem_icms": "PARAMETRIZACAO_CONTADOR",
        "codigo_icms": "PARAMETRIZACAO_CONTADOR", "codigo_ipi": "PARAMETRIZACAO_CONTADOR",
        "codigo_pis": "PARAMETRIZACAO_CONTADOR", "codigo_cofins": "PARAMETRIZACAO_CONTADOR",
        "codigo_cbenef": "PARAMETRIZACAO_CONTADOR", "inclui_total_candidato": "DECISAO_FISCAL",
    }
    opcionais = {"ean", "ean_tributavel", "cest"}
    campos += [
        ("produtos", f"itens[].{nome}", fonte, "CONDICIONADO" if nome in opcionais else "BLOQUEIO")
        for nome, fonte in fontes_produtos.items()
    ]
    campos += [
        ("tributos_itens", f"itens[].grupos.{grupo}.{nome}", "MEMORIA_APROVADA", "BLOQUEIO")
        for grupo in ("icms", "pis", "cofins") for nome in ("base", "aliquota", "valor")
    ]
    campos += [
        ("ajustes_comerciais", f"itens[].{nome}", "RATEIO_APROVADO", "CONDICIONADO")
        for nome in ("frete", "seguro", "outras_despesas", "desconto")
    ]
    campos += [
        ("transporte", "dados.modalidade", "FICHA_TRANSPORTE", "BLOQUEIO"),
        *[
            ("transporte", f"dados.{nome}", "FICHA_TRANSPORTE", "CONDICIONADO")
            for nome in (
                "nome", "documento", "inscricao_estadual", "endereco", "municipio", "uf",
                "quantidade_volumes", "peso_liquido", "peso_bruto",
            )
        ],
    ]
    campos += [
        ("totalizacao", f"totais_comerciais.{nome}", "TOTALIZACAO_DIAGNOSTICA", "BLOQUEIO")
        for nome in (
            "valor_produtos", "valor_base", "frete", "seguro", "outras_despesas",
            "desconto", "total_informado",
        )
    ]
    campos += [
        ("totalizacao", f"totais_tributarios_informados.{grupo}.{nome}", "MEMORIA_APROVADA", "BLOQUEIO")
        for grupo in ("icms", "pis", "cofins") for nome in ("base", "valor")
    ]
    campos += [
        ("totalizacao", "totais_fiscais_nao_definidos.valor_nota", "HIPOTESES_E_TOTALIZACAO", "POLITICA"),
        ("pagamento_fiscal", "politica.tpag", "POLITICA_DOCUMENTAL", "BLOQUEIO"),
        ("pagamento_fiscal", "politica.vpag", "POLITICA_DOCUMENTAL", "BLOQUEIO"),
        ("observacoes_fiscais", "textos_fiscais.infadic", "TEXTO_FISCAL_APROVADO", "POLITICA"),
        ("observacoes_fiscais", "textos_fiscais.itens[].infadprod", "TEXTO_FISCAL_APROVADO", "POLITICA"),
        ("ipi_devolvido", "itens[].imposto_devol.pdevol", "HIPOTESE_CONTADOR", "POLITICA"),
        ("ipi_devolvido", "itens[].imposto_devol.vipidevol", "HIPOTESE_CONTADOR", "POLITICA"),
        ("ipi_devolvido", "total.vipidevol", "HIPOTESE_CONTADOR", "POLITICA"),
        ("icms_st_fcp", "itens[].hipotese.codigo", "HIPOTESE_CONTADOR", "POLITICA"),
        ("icms_st_fcp", "itens[].destino_fiscal.grupo_icms_st", "HIPOTESE_CONTADOR", "POLITICA"),
        ("icms_st_fcp", "itens[].destino_fiscal.grupo_fcp", "HIPOTESE_CONTADOR", "POLITICA"),
        ("icms_st_fcp", "totais.icms_st", "HIPOTESE_CONTADOR", "POLITICA"),
        ("icms_st_fcp", "totais.fcp", "HIPOTESE_CONTADOR", "POLITICA"),
        ("rtc", "itens[].classificacao_rtc.codigo", "VIGENCIA_E_CONTADOR", "POLITICA"),
        ("rtc", "itens[].classificacao_rtc.contribuinte_exclusivo_ibs_cbs", "VIGENCIA_E_CONTADOR", "POLITICA"),
        ("rtc", "itens[].destino_fiscal.grupo_ibs", "VIGENCIA_E_CONTADOR", "POLITICA"),
        ("rtc", "itens[].destino_fiscal.grupo_cbs", "VIGENCIA_E_CONTADOR", "POLITICA"),
        ("rtc", "itens[].destino_fiscal.grupo_devolucao_tributos", "VIGENCIA_E_CONTADOR", "POLITICA"),
        ("rtc", "totais.ibs", "VIGENCIA_E_CONTADOR", "POLITICA"),
        ("rtc", "totais.cbs", "VIGENCIA_E_CONTADOR", "POLITICA"),
        ("rtc", "totais.rtc", "VIGENCIA_E_CONTADOR", "POLITICA"),
    ]
    return tuple(campos)


CAMPOS_ATOMICOS = _definicoes()

LACUNAS_MODELAGEM = (
    ("tributos_itens.itens[].icms.modalidade_base", "NFe/infNFe/det/imposto/ICMS/*/modBC", "MODALIDADE_BASE_ICMS_NAO_MODELADA", "CONTADOR_E_CONTRATO"),
    ("tributos_itens.itens[].icms.reducao_base", "NFe/infNFe/det/imposto/ICMS/*/pRedBC", "REDUCAO_BASE_ICMS_NAO_MODELADA", "CONTADOR_E_CONTRATO"),
    ("ipi_devolvido.enquadramento", "NFe/infNFe/det/imposto/IPI/cEnq", "ENQUADRAMENTO_IPI_NAO_MODELADO_NA_DEVOLUCAO", "CONTADOR_E_CONTRATO"),
    ("tributos_itens.variantes_pis_cofins", "NFe/infNFe/det/imposto/PIS|COFINS/*", "VARIANTES_PIS_COFINS_NAO_MODELADAS", "CONTADOR_E_CONTRATO"),
    ("serializador_devolucao", "NFe", "GERADOR_ESPECIFICO_NAO_IMPLEMENTADO", "CODIGO"),
    ("focus.grupos_devolucao", "JSON Focus", "PARIDADE_FOCUS_INCOMPLETA", "ADAPTADOR"),
)


def _conteudo(resultado, grupo):
    item = resultado.get(grupo, {}) if isinstance(resultado, dict) else {}
    return item.get("conteudo", {}) if isinstance(item, dict) and isinstance(item.get("conteudo"), dict) else {}


def _valores(raiz, caminho):
    atuais = [raiz]
    for parte in caminho.split("."):
        lista = parte.endswith("[]")
        chave = parte[:-2] if lista else parte
        proximos = []
        for atual in atuais:
            valor = atual.get(chave) if isinstance(atual, dict) else None
            if lista:
                proximos.extend(valor if isinstance(valor, list) else [])
            else:
                proximos.append(valor)
        atuais = proximos
    return atuais


def _preenchido(valor):
    return valor is not None and valor != ""


def construir_inventario_dados_devolucao(resultado_extracao):
    itens = []
    for grupo, campo, fonte, tratamento in CAMPOS_ATOMICOS:
        valores = _valores(_conteudo(resultado_extracao, grupo), campo)
        preenchidos = sum(_preenchido(valor) for valor in valores)
        if valores and preenchidos == len(valores):
            estado = "DISPONIVEL_NO_CONTRATO"
        elif preenchidos:
            estado = "PARCIALMENTE_DISPONIVEL"
        elif tratamento == "CONDICIONADO":
            estado = "CONDICIONADO_NAO_INFORMADO"
        elif tratamento == "POLITICA":
            estado = "NAO_DEFINIDO_POR_POLITICA"
        else:
            estado = "AUSENTE_OU_ORIGEM_NAO_APROVADA"
        itens.append({
            "grupo": grupo,
            "campo": campo,
            "fonte_primaria": fonte,
            "tratamento_ausencia": tratamento,
            "estado": estado,
            "ocorrencias": len(valores),
            "preenchidas": preenchidos,
            "expoe_valor": False,
            "permite_serializacao": False,
        })
    conteudo = {
        "contrato": CONTRATO_INVENTARIO,
        "operacao": "DEVOLUCAO_COMPRA",
        "itens": itens,
        "lacunas_modelagem": [
            {"campo": campo, "destino": destino, "codigo": codigo, "responsavel": responsavel}
            for campo, destino, codigo, responsavel in LACUNAS_MODELAGEM
        ],
        "politica": {
            "expor_valores": False,
            "usar_xml_historico_como_cadastro_atual": False,
            "preencher_por_default": False,
            "permitir_serializacao": False,
            "permitir_emissao": False,
        },
    }
    return {"conteudo": conteudo, "validacao": validar_inventario_dados_devolucao(conteudo)}


def validar_inventario_dados_devolucao(conteudo):
    erros = []

    def erro(caminho, codigo):
        erros.append({"caminho": caminho, "codigo": codigo})

    if not isinstance(conteudo, dict):
        erro("$", "OBJETO_OBRIGATORIO")
        conteudo = {}
    if set(conteudo) != {"contrato", "operacao", "itens", "lacunas_modelagem", "politica"}:
        erro("$", "CAMPOS_INVALIDOS")
    if conteudo.get("contrato") != CONTRATO_INVENTARIO:
        erro("contrato", "CONTRATO_INVALIDO")
    if conteudo.get("operacao") != "DEVOLUCAO_COMPRA":
        erro("operacao", "OPERACAO_NAO_SUPORTADA")
    itens = conteudo.get("itens")
    if not isinstance(itens, list) or len(itens) != len(CAMPOS_ATOMICOS):
        erro("itens", "INVENTARIO_INCOMPLETO")
        itens = []
    estados = {
        "DISPONIVEL_NO_CONTRATO", "PARCIALMENTE_DISPONIVEL",
        "CONDICIONADO_NAO_INFORMADO", "NAO_DEFINIDO_POR_POLITICA",
        "AUSENTE_OU_ORIGEM_NAO_APROVADA",
    }
    for indice, esperado in enumerate(CAMPOS_ATOMICOS):
        caminho = f"itens.{indice}"
        item = itens[indice] if indice < len(itens) else {}
        if not isinstance(item, dict) or set(item) != {
            "grupo", "campo", "fonte_primaria", "tratamento_ausencia", "estado",
            "ocorrencias", "preenchidas", "expoe_valor", "permite_serializacao",
        }:
            erro(caminho, "ITEM_INVALIDO")
            continue
        if (item["grupo"], item["campo"], item["fonte_primaria"], item["tratamento_ausencia"]) != esperado:
            erro(caminho, "DEFINICAO_DIVERGENTE")
        if item["tratamento_ausencia"] not in TRATAMENTOS or item["estado"] not in estados:
            erro(caminho, "ESTADO_INVALIDO")
        if type(item["ocorrencias"]) is not int or type(item["preenchidas"]) is not int or not 0 <= item["preenchidas"] <= item["ocorrencias"]:
            erro(caminho, "CONTAGEM_INVALIDA")
        if item["expoe_valor"] is not False:
            erro(caminho, "EXPOSICAO_DE_VALOR_PROIBIDA")
        if item["permite_serializacao"] is not False:
            erro(caminho, "SERIALIZACAO_ANTECIPADA_PROIBIDA")
    lacunas = conteudo.get("lacunas_modelagem")
    esperadas = [
        {"campo": campo, "destino": destino, "codigo": codigo, "responsavel": responsavel}
        for campo, destino, codigo, responsavel in LACUNAS_MODELAGEM
    ]
    if lacunas != esperadas:
        erro("lacunas_modelagem", "LACUNAS_DIVERGENTES")
    politica = {
        "expor_valores": False,
        "usar_xml_historico_como_cadastro_atual": False,
        "preencher_por_default": False,
        "permitir_serializacao": False,
        "permitir_emissao": False,
    }
    if conteudo.get("politica") != politica:
        erro("politica", "POLITICA_DE_BLOQUEIO_INVALIDA")
    contagens = {estado: sum(item.get("estado") == estado for item in itens) for estado in estados}
    return {
        "contrato": CONTRATO_VALIDACAO_INVENTARIO,
        "estrutura_valida": not erros,
        "quantidade_campos_atomicos": len(itens),
        "quantidade_lacunas_modelagem": len(lacunas) if isinstance(lacunas, list) else 0,
        "contagens": contagens,
        "erros": erros,
        "permite_gerar_xml": False,
        "permite_focus": False,
        "permite_sefaz_direta": False,
        "permite_emissao": False,
    }
