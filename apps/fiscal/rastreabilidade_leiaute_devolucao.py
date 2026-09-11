"""Matriz estática de rastreabilidade da devolução; não serializa nem transmite."""

from .portao_prontidao_devolucao import SUBCONTRATOS


CONTRATO_RASTREABILIDADE = "supplier_return_layout_traceability_v1"
CONTRATO_VALIDACAO_RASTREABILIDADE = "supplier_return_layout_traceability_validation_v1"

COBERTURAS_FOCUS = {"MAPEADO", "PARCIAL", "NAO_MAPEADO", "CONDICIONADO_HIPOTESE"}
COBERTURA_DIRETA = "SEM_TRANSFORMACAO_DE_CONTEUDO"
EVIDENCIA_XSD = {
    "pacote": "PL_010f_v1.04",
    "arquivo_principal": "leiauteNFe_v4.00.xsd",
    "sha256_arquivo_principal": "2bace939973916d54184ff3e2740041a932de5d79772f3363504504160f22542",
    "arquivo_evidencia": "docs/evidencias/nfe_2026_09_10/schemas_010f.zip",
    "sha256_arquivo_evidencia": "b8589490a58a09a993a80e6ac4d7ed10f20892061ecfc56719337098d4b95998",
    "entrada_arquivo_principal": "PL_010f_v1.04/leiauteNFe_v4.00.xsd",
    "evidencia_arquivada": True,
    "hash_reproduzivel": True,
    "instalado_em_fiscal_schemas": False,
    "contrato_auditoria_offline": "fiscal_schema_package_audit_v1",
    "auditoria_offline_disponivel": True,
    "contrato_compatibilidade_matriz": "supplier_return_atomic_xsd_compatibility_v1",
    "compatibilidade_matriz_disponivel": True,
    "pacote_aprovado": False,
}
FONTES_CODIGO = {
    "gerador_atual": "apps/fiscal/services.py:gerar_xml_nfe_pedido_online",
    "adaptador_focus": "apps/fiscal/focus_sefaz_adapter.py:FocusNFeSefazAdapter._payload_xml",
    "adaptador_sefaz_direta": "apps/fiscal/sefaz_direta/adapter.py:SefazDiretaAdapter.transmitir",
}


MAPEAMENTOS = (
    ("envelope", (
        ("modelo", "NFe/infNFe/ide/mod", "PARCIAL"),
        ("operacao", "NFe/infNFe/ide/finNFe", "MAPEADO"),
    )),
    ("referencias_itens", (
        ("itens[].chave_acesso", "NFe/infNFe/det/DFeReferenciado/chaveAcesso", "NAO_MAPEADO"),
        ("itens[].nitem_original", "NFe/infNFe/det/DFeReferenciado/nItem", "NAO_MAPEADO"),
    )),
    ("identidade_partes", (
        ("identificacao.natureza_operacao", "NFe/infNFe/ide/natOp", "MAPEADO"),
        ("identificacao.finalidade", "NFe/infNFe/ide/finNFe", "MAPEADO"),
        ("identificacao.tipo_operacao", "NFe/infNFe/ide/tpNF", "MAPEADO"),
        ("emitente", "NFe/infNFe/emit", "PARCIAL"),
        ("destinatario", "NFe/infNFe/dest", "PARCIAL"),
    )),
    ("produtos", (
        ("itens[].identidade", "NFe/infNFe/det/prod/cProd|cEAN|xProd", "MAPEADO"),
        ("itens[].classificacao", "NFe/infNFe/det/prod/NCM|CEST|cBenef|CFOP", "MAPEADO"),
        ("itens[].quantidades_valores", "NFe/infNFe/det/prod/uCom|qCom|vUnCom|vProd|uTrib|qTrib|vUnTrib", "MAPEADO"),
    )),
    ("tributos_itens", (
        ("itens[].grupos.icms", "NFe/infNFe/det/imposto/ICMS/*", "PARCIAL"),
        ("itens[].grupos.pis", "NFe/infNFe/det/imposto/PIS/*", "PARCIAL"),
        ("itens[].grupos.pis.variante_candidata", "NFe/infNFe/det/imposto/PIS/PISAliq|PISQtde|PISNT|PISOutr", "PARCIAL"),
        ("itens[].grupos.pis.modalidade_calculo_candidata", "NFe/infNFe/det/imposto/PIS/*/vBC|pPIS|qBCProd|vAliqProd", "PARCIAL"),
        ("itens[].grupos.cofins", "NFe/infNFe/det/imposto/COFINS/*", "PARCIAL"),
        ("itens[].grupos.cofins.variante_candidata", "NFe/infNFe/det/imposto/COFINS/COFINSAliq|COFINSQtde|COFINSNT|COFINSOutr", "PARCIAL"),
        ("itens[].grupos.cofins.modalidade_calculo_candidata", "NFe/infNFe/det/imposto/COFINS/*/vBC|pCOFINS|qBCProd|vAliqProd", "PARCIAL"),
    )),
    ("ajustes_comerciais", (
        ("itens[].frete", "NFe/infNFe/det/prod/vFrete", "NAO_MAPEADO"),
        ("itens[].seguro", "NFe/infNFe/det/prod/vSeg", "NAO_MAPEADO"),
        ("itens[].outras_despesas", "NFe/infNFe/det/prod/vOutro", "NAO_MAPEADO"),
        ("itens[].desconto", "NFe/infNFe/det/prod/vDesc", "MAPEADO"),
    )),
    ("transporte", (
        ("dados.modalidade", "NFe/infNFe/transp/modFrete", "MAPEADO"),
        ("dados.transportador", "NFe/infNFe/transp/transporta", "NAO_MAPEADO"),
        ("dados.volumes_pesos", "NFe/infNFe/transp/vol", "NAO_MAPEADO"),
    )),
    ("totalizacao", (
        ("totais_comerciais", "NFe/infNFe/total/ICMSTot", "NAO_MAPEADO"),
        ("totais_tributarios_informados", "NFe/infNFe/total/ICMSTot", "NAO_MAPEADO"),
        ("totais_fiscais_nao_definidos", "NFe/infNFe/total/*", "CONDICIONADO_HIPOTESE"),
    )),
    ("pagamento_fiscal", (
        ("politica.tpag", "NFe/infNFe/pag/detPag/tPag", "MAPEADO"),
        ("politica.vpag", "NFe/infNFe/pag/detPag/vPag", "MAPEADO"),
    )),
    ("observacoes_fiscais", (
        ("textos_fiscais.infadic", "NFe/infNFe/infAdic/infCpl", "MAPEADO"),
        ("textos_fiscais.itens[].infadprod", "NFe/infNFe/det/infAdProd", "NAO_MAPEADO"),
    )),
    ("ipi_devolvido", (
        ("itens[].enquadramento_ipi.valor_candidato", "NFe/infNFe/det/imposto/IPI/cEnq", "PARCIAL"),
        ("itens[].imposto_devol.pdevol", "NFe/infNFe/det/impostoDevol/pDevol", "NAO_MAPEADO"),
        ("itens[].imposto_devol.vipidevol", "NFe/infNFe/det/impostoDevol/IPI/vIPIDevol", "NAO_MAPEADO"),
        ("total.vipidevol", "NFe/infNFe/total/ICMSTot/vIPIDevol", "NAO_MAPEADO"),
    )),
    ("icms_st_fcp", (
        ("itens[].destino_fiscal", "NFe/infNFe/det/imposto/ICMS/*", "CONDICIONADO_HIPOTESE"),
        ("totais.icms_st_fcp", "NFe/infNFe/total/ICMSTot/*", "CONDICIONADO_HIPOTESE"),
    )),
    ("rtc", (
        ("itens[].classificacao_rtc", "NFe/infNFe/det/imposto/IBSCBS/*", "CONDICIONADO_HIPOTESE"),
        ("itens[].destino_fiscal", "NFe/infNFe/det/imposto/IBSCBS/*", "CONDICIONADO_HIPOTESE"),
        ("totais.rtc", "NFe/infNFe/total/IBSCBSTot", "CONDICIONADO_HIPOTESE"),
    )),
)


def construir_rastreabilidade_leiaute_devolucao():
    contratos = {grupo: contrato for grupo, contrato, _, _ in SUBCONTRATOS}
    grupos = []
    for grupo, campos in MAPEAMENTOS:
        grupos.append({
            "grupo": grupo,
            "contrato": contratos[grupo],
            "campos": [
                {
                    "origem_contrato": origem,
                    "destino_xsd": destino,
                    "focus": focus,
                    "sefaz_direta": COBERTURA_DIRETA,
                    "serializacao_local_implementada": False,
                }
                for origem, destino, focus in campos
            ],
        })
    conteudo = {
        "contrato": CONTRATO_RASTREABILIDADE,
        "operacao": "DEVOLUCAO_COMPRA",
        "evidencia_xsd": dict(EVIDENCIA_XSD),
        "fontes_codigo": dict(FONTES_CODIGO),
        "grupos": grupos,
        "conclusoes": {
            "gerador_devolucao_implementado": False,
            "focus_paridade_conteudo": False,
            "sefaz_direta_paridade_conteudo": False,
            "schema_pacote_aprovado": False,
        },
        "politica": {
            "permitir_serializacao": False,
            "permitir_focus": False,
            "permitir_sefaz_direta": False,
            "permitir_emissao": False,
        },
    }
    return {"conteudo": conteudo, "validacao": validar_rastreabilidade_leiaute_devolucao(conteudo)}


def validar_rastreabilidade_leiaute_devolucao(conteudo):
    erros = []

    def erro(caminho, codigo):
        erros.append({"caminho": caminho, "codigo": codigo})

    if not isinstance(conteudo, dict):
        erro("$", "OBJETO_OBRIGATORIO")
        conteudo = {}
    if set(conteudo) != {"contrato", "operacao", "evidencia_xsd", "fontes_codigo", "grupos", "conclusoes", "politica"}:
        erro("$", "CAMPOS_INVALIDOS")
    if conteudo.get("contrato") != CONTRATO_RASTREABILIDADE:
        erro("contrato", "CONTRATO_INVALIDO")
    if conteudo.get("operacao") != "DEVOLUCAO_COMPRA":
        erro("operacao", "OPERACAO_NAO_SUPORTADA")

    evidencia = conteudo.get("evidencia_xsd")
    if evidencia != EVIDENCIA_XSD:
        erro("evidencia_xsd", "EVIDENCIA_INVALIDA")

    esperados = [(grupo, contrato) for grupo, contrato, _, _ in SUBCONTRATOS]
    grupos = conteudo.get("grupos")
    if not isinstance(grupos, list) or len(grupos) != len(esperados):
        erro("grupos", "GRUPOS_INCOMPLETOS")
        grupos = []
    origens_vistas = set()
    for indice, esperado in enumerate(esperados):
        caminho = f"grupos.{indice}"
        grupo = grupos[indice] if indice < len(grupos) else {}
        if not isinstance(grupo, dict) or set(grupo) != {"grupo", "contrato", "campos"}:
            erro(caminho, "GRUPO_INVALIDO")
            continue
        if (grupo["grupo"], grupo["contrato"]) != esperado:
            erro(caminho, "SUBCONTRATO_DIVERGENTE")
        campos = grupo["campos"]
        if not isinstance(campos, list) or not campos:
            erro(f"{caminho}.campos", "CAMPOS_OBRIGATORIOS")
            continue
        campos_esperados = MAPEAMENTOS[indice][1]
        if len(campos) != len(campos_esperados):
            erro(f"{caminho}.campos", "MAPEAMENTOS_INCOMPLETOS")
        for posicao, campo in enumerate(campos):
            campo_caminho = f"{caminho}.campos.{posicao}"
            if not isinstance(campo, dict) or set(campo) != {
                "origem_contrato", "destino_xsd", "focus", "sefaz_direta", "serializacao_local_implementada"
            }:
                erro(campo_caminho, "MAPEAMENTO_INVALIDO")
                continue
            identidade = (grupo["grupo"], campo["origem_contrato"])
            if identidade in origens_vistas:
                erro(campo_caminho, "ORIGEM_DUPLICADA")
            origens_vistas.add(identidade)
            if not campo["origem_contrato"] or not campo["destino_xsd"]:
                erro(campo_caminho, "CAMINHO_OBRIGATORIO")
            if posicao >= len(campos_esperados) or (
                campo["origem_contrato"], campo["destino_xsd"], campo["focus"]
            ) != campos_esperados[posicao]:
                erro(campo_caminho, "MAPEAMENTO_DIVERGENTE")
            if campo["focus"] not in COBERTURAS_FOCUS:
                erro(f"{campo_caminho}.focus", "COBERTURA_FOCUS_INVALIDA")
            if campo["sefaz_direta"] != COBERTURA_DIRETA:
                erro(f"{campo_caminho}.sefaz_direta", "TRANSPORTE_DIRETO_DIVERGENTE")
            if campo["serializacao_local_implementada"] is not False:
                erro(f"{campo_caminho}.serializacao_local_implementada", "SERIALIZACAO_ANTECIPADA_PROIBIDA")

    fontes = conteudo.get("fontes_codigo")
    if fontes != FONTES_CODIGO:
        erro("fontes_codigo", "FONTES_INVALIDAS")
    conclusoes_esperadas = {
        "gerador_devolucao_implementado": False,
        "focus_paridade_conteudo": False,
        "sefaz_direta_paridade_conteudo": False,
        "schema_pacote_aprovado": False,
    }
    if conteudo.get("conclusoes") != conclusoes_esperadas:
        erro("conclusoes", "CONCLUSAO_ANTECIPADA_PROIBIDA")
    politica_esperada = {
        "permitir_serializacao": False,
        "permitir_focus": False,
        "permitir_sefaz_direta": False,
        "permitir_emissao": False,
    }
    if conteudo.get("politica") != politica_esperada:
        erro("politica", "POLITICA_DE_BLOQUEIO_INVALIDA")
    return {
        "contrato": CONTRATO_VALIDACAO_RASTREABILIDADE,
        "estrutura_valida": not erros,
        "quantidade_grupos": len(grupos),
        "quantidade_campos": sum(len(item.get("campos", [])) for item in grupos if isinstance(item, dict)),
        "erros": erros,
        "permite_gerar_xml": False,
        "permite_focus": False,
        "permite_sefaz_direta": False,
        "permite_emissao": False,
    }
