"""Contrato puro dos valores tributários informados, sem cálculo ou emissão."""
from decimal import Decimal, InvalidOperation
import re


CONTRATO_TRIBUTOS_ITENS = "supplier_return_item_tax_values_v1"
CONTRATO_VALIDACAO_TRIBUTOS_ITENS = "supplier_return_item_tax_values_validation_v1"

ESTADOS_GRUPOS = {
    "icms": "INFORMADO_PENDENTE_MATRIZ",
    "pis": "INFORMADO_PENDENTE_MATRIZ",
    "cofins": "INFORMADO_PENDENTE_MATRIZ",
    "icms_st": "HIPOTESE_NAO_CONFIRMADA",
    "fcp": "HIPOTESE_NAO_CONFIRMADA",
    "ipi_memoria": "NAO_EQUIVALE_IPI_DEVOLVIDO",
    "ibs": "VIGENCIA_E_LEIAUTE_PENDENTES",
    "cbs": "VIGENCIA_E_LEIAUTE_PENDENTES",
}
_CAMPOS_ITEM = {
    "nitem_novo", "nitem_original", "item_rascunho_id", "memoria_id",
    "memoria_sha256", "revisao_sha256", "origem_aprovada", "grupos",
}
_CAMPOS_GRUPO = {"estado", "codigo", "base", "aliquota", "valor"}
_CAMPOS_GRUPO_ICMS = _CAMPOS_GRUPO | {
    "modalidade_base_candidata", "modalidade_base_fonte", "modalidade_base_confirmada",
    "reducao_base_candidata", "reducao_base_fonte", "reducao_base_confirmada",
}
_CAMPOS_GRUPO_CONTRIBUICAO = _CAMPOS_GRUPO | {
    "variante_candidata", "modalidade_calculo_candidata", "variante_fonte",
    "estado_variante", "grupo_opcional_xsd", "depende_decisao_contador",
    "destino_xml_futuro", "variante_confirmada",
}
VARIANTES_CONTRIBUICOES = {
    "pis": {
        "PISAliq": ({"01", "02"}, {"PERCENTUAL"}),
        "PISQtde": ({"03"}, {"QUANTIDADE"}),
        "PISNT": ({"04", "05", "06", "07", "08", "09"}, {"SEM_CALCULO"}),
        "PISOutr": ({
            "49", "50", "51", "52", "53", "54", "55", "56",
            "60", "61", "62", "63", "64", "65", "66", "67",
            "70", "71", "72", "73", "74", "75", "98", "99",
        }, {"PERCENTUAL", "QUANTIDADE"}),
    },
    "cofins": {
        "COFINSAliq": ({"01", "02"}, {"PERCENTUAL"}),
        "COFINSQtde": ({"03"}, {"QUANTIDADE"}),
        "COFINSNT": ({"04", "05", "06", "07", "08", "09"}, {"SEM_CALCULO"}),
        "COFINSOutr": ({
            "49", "50", "51", "52", "53", "54", "55", "56",
            "60", "61", "62", "63", "64", "65", "66", "67",
            "70", "71", "72", "73", "74", "75", "98", "99",
        }, {"PERCENTUAL", "QUANTIDADE"}),
    },
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


def _percentual_reducao_candidato(valor):
    if not isinstance(valor, str) or not re.fullmatch(r"(?:0|[1-9][0-9]{0,2})(?:\.[0-9]{2,4})?", valor):
        return False
    try:
        numero = Decimal(valor)
    except (InvalidOperation, ValueError):
        return False
    return numero.is_finite() and Decimal("0") <= numero <= Decimal("100")


def validar_tributos_itens_devolucao(conteudo):
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
    if conteudo.get("contrato") != CONTRATO_TRIBUTOS_ITENS:
        erro("contrato", "VALOR_NAO_SUPORTADO")
    if conteudo.get("operacao") != "DEVOLUCAO_COMPRA":
        erro("operacao", "VALOR_NAO_SUPORTADO")
    if conteudo.get("permite_emissao") is not False:
        erro("permite_emissao", "EMISSAO_PROIBIDA")
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
        for campo in ("nitem_novo", "nitem_original", "item_rascunho_id"):
            if type(item.get(campo)) is not int or not 1 <= item[campo] <= (999 if campo.startswith("nitem") else 2**63 - 1):
                erro(f"{caminho}.{campo}", "IDENTIFICADOR_INVALIDO")
        if item.get("item_rascunho_id") in vistos:
            erro(f"{caminho}.item_rascunho_id", "ITEM_DUPLICADO")
        vistos.add(item.get("item_rascunho_id"))
        if item.get("origem_aprovada") is not True:
            pendencia(f"{caminho}.origem_aprovada", "MEMORIA_REVISADA_APROVADA_PENDENTE")
        if type(item.get("memoria_id")) is not int or item.get("memoria_id", 0) <= 0:
            pendencia(f"{caminho}.memoria_id", "MEMORIA_PENDENTE")
        for campo in ("memoria_sha256", "revisao_sha256"):
            valor = item.get(campo)
            if not isinstance(valor, str) or len(valor) != 64 or any(c not in "0123456789abcdef" for c in valor):
                pendencia(f"{caminho}.{campo}", "HASH_ORIGEM_PENDENTE")
        grupos = item.get("grupos")
        if not isinstance(grupos, dict) or set(grupos) != set(ESTADOS_GRUPOS):
            erro(f"{caminho}.grupos", "GRUPOS_INVALIDOS")
            continue
        for nome, estado in ESTADOS_GRUPOS.items():
            grupo = grupos.get(nome)
            grupo_caminho = f"{caminho}.grupos.{nome}"
            if nome == "icms":
                campos_grupo = _CAMPOS_GRUPO_ICMS
            elif nome in VARIANTES_CONTRIBUICOES:
                campos_grupo = _CAMPOS_GRUPO_CONTRIBUICAO
            else:
                campos_grupo = _CAMPOS_GRUPO
            if not isinstance(grupo, dict) or set(grupo) != campos_grupo:
                erro(grupo_caminho, "CAMPOS_INVALIDOS")
                continue
            if grupo.get("estado") != estado:
                erro(f"{grupo_caminho}.estado", "ESTADO_INVALIDO")
            if not isinstance(grupo.get("codigo"), str):
                erro(f"{grupo_caminho}.codigo", "CODIGO_INVALIDO")
            if item.get("origem_aprovada") is True:
                for campo, casas in (("base", 2), ("aliquota", 4), ("valor", 2)):
                    if not _decimal_exato(grupo.get(campo), casas):
                        pendencia(f"{grupo_caminho}.{campo}", "VALOR_TRIBUTARIO_PENDENTE")
            if nome == "icms":
                modalidade = grupo.get("modalidade_base_candidata")
                if modalidade not in {"", "0", "1", "2", "3"}:
                    erro(f"{grupo_caminho}.modalidade_base_candidata", "MODBC_CANDIDATA_INVALIDA")
                elif not modalidade:
                    pendencia(f"{grupo_caminho}.modalidade_base_candidata", "MODBC_CANDIDATA_PENDENTE")
                else:
                    pendencia(f"{grupo_caminho}.modalidade_base_candidata", "MODBC_NAO_CONFIRMADA")
                if grupo.get("modalidade_base_fonte") != "DECISAO_CONTADOR_PENDENTE":
                    erro(f"{grupo_caminho}.modalidade_base_fonte", "MODBC_FONTE_INVALIDA")
                if grupo.get("modalidade_base_confirmada") is not False:
                    erro(f"{grupo_caminho}.modalidade_base_confirmada", "MODBC_CONFIRMACAO_DIRETA_PROIBIDA")
                reducao = grupo.get("reducao_base_candidata")
                if reducao == "":
                    pendencia(f"{grupo_caminho}.reducao_base_candidata", "PREDBC_CANDIDATA_PENDENTE")
                elif not _percentual_reducao_candidato(reducao):
                    erro(f"{grupo_caminho}.reducao_base_candidata", "PREDBC_CANDIDATA_INVALIDA")
                else:
                    pendencia(f"{grupo_caminho}.reducao_base_candidata", "PREDBC_NAO_CONFIRMADA")
                if grupo.get("reducao_base_fonte") != "DECISAO_CONTADOR_PENDENTE":
                    erro(f"{grupo_caminho}.reducao_base_fonte", "PREDBC_FONTE_INVALIDA")
                if grupo.get("reducao_base_confirmada") is not False:
                    erro(f"{grupo_caminho}.reducao_base_confirmada", "PREDBC_CONFIRMACAO_DIRETA_PROIBIDA")
            elif nome in VARIANTES_CONTRIBUICOES:
                prefixo = nome.upper()
                variante = grupo.get("variante_candidata")
                modalidade = grupo.get("modalidade_calculo_candidata")
                opcoes = VARIANTES_CONTRIBUICOES[nome]
                if variante == "":
                    pendencia(f"{grupo_caminho}.variante_candidata", f"VARIANTE_{prefixo}_PENDENTE")
                    if modalidade != "":
                        erro(f"{grupo_caminho}.modalidade_calculo_candidata", f"MODALIDADE_{prefixo}_SEM_VARIANTE")
                    estado_esperado = "NAO_DEFINIDA"
                elif variante not in opcoes:
                    erro(f"{grupo_caminho}.variante_candidata", f"VARIANTE_{prefixo}_INVALIDA")
                    estado_esperado = "CANDIDATA_NAO_CONFIRMADA"
                else:
                    csts, modalidades = opcoes[variante]
                    if grupo.get("codigo") not in csts:
                        erro(f"{grupo_caminho}.codigo", f"CST_{prefixo}_INCOMPATIVEL_COM_VARIANTE")
                    if modalidade not in modalidades:
                        erro(f"{grupo_caminho}.modalidade_calculo_candidata", f"MODALIDADE_{prefixo}_INCOMPATIVEL")
                    pendencia(f"{grupo_caminho}.variante_candidata", f"VARIANTE_{prefixo}_NAO_CONFIRMADA")
                    estado_esperado = "CANDIDATA_NAO_CONFIRMADA"
                if grupo.get("estado_variante") != estado_esperado:
                    erro(f"{grupo_caminho}.estado_variante", f"ESTADO_VARIANTE_{prefixo}_INVALIDO")
                if grupo.get("variante_fonte") != "DECISAO_CONTADOR_PENDENTE":
                    erro(f"{grupo_caminho}.variante_fonte", f"FONTE_VARIANTE_{prefixo}_INVALIDA")
                if grupo.get("grupo_opcional_xsd") is not True:
                    erro(f"{grupo_caminho}.grupo_opcional_xsd", f"CARDINALIDADE_{prefixo}_INVALIDA")
                if grupo.get("depende_decisao_contador") is not True:
                    erro(f"{grupo_caminho}.depende_decisao_contador", f"DECISAO_CONTADOR_{prefixo}_OBRIGATORIA")
                destino = f"NFe/infNFe/det/imposto/{'PIS' if nome == 'pis' else 'COFINS'}/*"
                if grupo.get("destino_xml_futuro") != destino:
                    erro(f"{grupo_caminho}.destino_xml_futuro", f"DESTINO_{prefixo}_INVALIDO")
                if grupo.get("variante_confirmada") is not False:
                    erro(f"{grupo_caminho}.variante_confirmada", f"CONFIRMACAO_VARIANTE_{prefixo}_ANTECIPADA")
    bloqueios = [{"grupo": "bases_valores", "codigo": item["codigo"]} for item in pendencias]
    bloqueios.extend((
        {"grupo": "classificacao", "codigo": "MATRIZ_TRIBUTARIA_NAO_HOMOLOGADA"},
        {"grupo": "icms_st_fcp", "codigo": "HIPOTESE_NAO_CONFIRMADA"},
        {"grupo": "ipi_devolvido", "codigo": "GRUPO_ESPECIFICO_NAO_IMPLEMENTADO"},
        {"grupo": "ibs_cbs", "codigo": "VIGENCIA_E_LEIAUTE_PENDENTES"},
        {"grupo": "xml", "codigo": "GERACAO_NAO_IMPLEMENTADA"},
        {"grupo": "transmissao", "codigo": "HOMOLOGACAO_PENDENTE"},
    ))
    pendencias_decisoes_icms = {
        "MODBC_CANDIDATA_PENDENTE", "MODBC_NAO_CONFIRMADA",
        "PREDBC_CANDIDATA_PENDENTE", "PREDBC_NAO_CONFIRMADA",
    }
    pendencias_decisoes = pendencias_decisoes_icms | {
        "VARIANTE_PIS_PENDENTE", "VARIANTE_PIS_NAO_CONFIRMADA",
        "VARIANTE_COFINS_PENDENTE", "VARIANTE_COFINS_NAO_CONFIRMADA",
    }
    return {
        "contrato": CONTRATO_VALIDACAO_TRIBUTOS_ITENS,
        "estrutura_valida": not erros,
        "origem_completa": not erros and not any(
            item["codigo"] not in pendencias_decisoes for item in pendencias
        ),
        "dados_completos": not erros and not pendencias,
        "escopo_fiscal_suportado": False,
        "erros": erros,
        "pendencias": pendencias,
        "bloqueios": bloqueios,
        "permite_aplicar_modalidade_base_icms": False,
        "permite_aplicar_reducao_base_icms": False,
        "permite_aplicar_variantes_pis_cofins": False,
        "permite_gerar_xml": False,
        "permite_emissao": False,
    }
