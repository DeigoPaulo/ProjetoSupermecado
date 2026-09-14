"""Especificação não emissiva dos campos mapeados no bloco ``emit``."""

import re

from .matriz_atomica_devolucao import (
    CONTRATO_MATRIZ_ATOMICA,
    ESTADOS_INVENTARIO,
    validar_matriz_atomica_devolucao,
)
from .plano_blocos_xsd_devolucao import CONTRATO_PLANO_BLOCOS, validar_plano_blocos_xsd


CONTRATO_ESPECIFICACAO_EMIT = "supplier_return_emit_field_specification_v1"
CONTRATO_VALIDACAO_ESPECIFICACAO_EMIT = "supplier_return_emit_field_specification_validation_v1"
UFS_EMITENTE = [
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT",
    "PA", "PB", "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO",
]


def _formato(tipo, base, *, minimo=None, maximo=None, padrao=None, enumeracoes=()):
    return {"tipo": tipo, "base": base, "minimo_caracteres": minimo,
            "maximo_caracteres": maximo, "padrao": padrao, "enumeracoes": list(enumeracoes)}


def _definicao(campo, destino, ordem_emit, formato, bloqueios, *, ordem_endereco=None,
               minimo=1, maximo=1, contexto="ELEMENTO"):
    return {
        "campo": f"emitente.{campo}", "destino_xml_futuro": destino,
        "fonte_primaria": "CADASTRO_FILIAL_E_CONFIGURACAO", "tratamento_ausencia": "BLOQUEIO",
        "regra_aplicacao": "EXIGIDO_ANTES_DO_GERADOR", "ordem_emit": ordem_emit,
        "ordem_ender_emit": ordem_endereco,
        "cardinalidade_xsd": {"minimo": minimo, "maximo": maximo, "contexto": contexto},
        "formato_xsd": formato, "bloqueios_especificos": list(bloqueios),
    }


DEFINICOES_EMIT = (
    _definicao("cnpj", "NFe/infNFe/emit/CNPJ", 1,
               _formato("TCnpj", "xs:string", maximo=14, padrao="[0-9A-Z]{12}[0-9]{2}"),
               ("IDENTIFICACAO_CNPJ_CPF_NAO_APROVADA", "CNPJ_ALFANUMERICO_NAO_SUPORTADO"),
               contexto="ESCOLHA_CNPJ_OU_CPF"),
    _definicao("razao_social", "NFe/infNFe/emit/xNome", 2,
               _formato("ANONIMO", "TString", minimo=2, maximo=60),
               ("VALIDACAO_MINIMA_XSD_NAO_IMPLEMENTADA",)),
    _definicao("logradouro", "NFe/infNFe/emit/enderEmit/xLgr", 4,
               _formato("ANONIMO", "TString", minimo=2, maximo=60),
               ("VALIDACAO_MINIMA_XSD_NAO_IMPLEMENTADA",), ordem_endereco=1,
               contexto="SUBGRUPO_ENDEREMIT"),
    _definicao("numero", "NFe/infNFe/emit/enderEmit/nro", 4,
               _formato("ANONIMO", "TString", minimo=1, maximo=60), (), ordem_endereco=2,
               contexto="SUBGRUPO_ENDEREMIT"),
    _definicao("bairro", "NFe/infNFe/emit/enderEmit/xBairro", 4,
               _formato("ANONIMO", "TString", minimo=2, maximo=60),
               ("VALIDACAO_MINIMA_XSD_NAO_IMPLEMENTADA",), ordem_endereco=4,
               contexto="SUBGRUPO_ENDEREMIT"),
    _definicao("codigo_municipio", "NFe/infNFe/emit/enderEmit/cMun", 4,
               _formato("TCodMunIBGE", "xs:string", padrao="[0-9]{7}"), (), ordem_endereco=5,
               contexto="SUBGRUPO_ENDEREMIT"),
    _definicao("municipio", "NFe/infNFe/emit/enderEmit/xMun", 4,
               _formato("ANONIMO", "TString", minimo=2, maximo=60),
               ("VALIDACAO_MINIMA_XSD_NAO_IMPLEMENTADA",), ordem_endereco=6,
               contexto="SUBGRUPO_ENDEREMIT"),
    _definicao("uf", "NFe/infNFe/emit/enderEmit/UF", 4,
               _formato("TUfEmi", "xs:string", enumeracoes=UFS_EMITENTE),
               ("VALIDACAO_DOMINIO_UF_XSD_NAO_IMPLEMENTADA",), ordem_endereco=7,
               contexto="SUBGRUPO_ENDEREMIT"),
    _definicao("cep", "NFe/infNFe/emit/enderEmit/CEP", 4,
               _formato("ANONIMO", "xs:string", padrao="[0-9]{8}"), (), ordem_endereco=8,
               contexto="SUBGRUPO_ENDEREMIT"),
    _definicao("inscricao_estadual", "NFe/infNFe/emit/IE", 5,
               _formato("TIe", "xs:string", maximo=14, padrao="[0-9]{2,14}|ISENTO"),
               ("VALIDACAO_IE_XSD_NAO_IMPLEMENTADA",), minimo=0),
    _definicao("crt", "NFe/infNFe/emit/CRT", 8,
               _formato("ANONIMO", "xs:string", enumeracoes=("1", "2", "3", "4")),
               ("REGIME_TRIBUTARIO_NAO_CONFIRMADO",)),
)


def _bloqueios(definicao, item_plano):
    return list(dict.fromkeys([
        "CADASTRO_FILIAL_E_CONFIGURACAO_NAO_CONFIRMADO",
        *definicao["bloqueios_especificos"], *item_plano["bloqueios"],
    ]))


def construir_especificacao_emit_devolucao(*, matriz, plano_blocos):
    """Confronta matriz e plano e descreve ``emit`` sem transportar valores."""
    matriz_conteudo = matriz.get("conteudo", {}) if isinstance(matriz, dict) else {}
    plano_conteudo = plano_blocos.get("conteudo", {}) if isinstance(plano_blocos, dict) else {}
    if not validar_matriz_atomica_devolucao(matriz_conteudo)["estrutura_valida"]:
        raise ValueError("A matriz atômica deve estar íntegra antes da especificação de emit.")
    if not validar_plano_blocos_xsd(plano_conteudo)["estrutura_valida"]:
        raise ValueError("O plano por blocos deve estar íntegro antes da especificação de emit.")
    if plano_conteudo.get("matriz_contrato") != matriz_conteudo.get("contrato"):
        raise ValueError("O plano por blocos não corresponde à matriz informada.")

    blocos = [item for item in plano_conteudo["blocos"] if item["bloco"] == "emit"]
    if len(blocos) != 1:
        raise ValueError("O plano deve conter exatamente um bloco emit.")
    matriz_por_campo = {item["campo"]: item for item in matriz_conteudo["itens"]
                        if item["grupo"] == "identidade_partes"}
    plano_por_campo = {item["campo"]: item for item in blocos[0]["campos"]
                       if item["grupo"] == "identidade_partes"}
    campos = []
    for definicao in DEFINICOES_EMIT:
        campo = definicao["campo"]
        item_matriz = matriz_por_campo.get(campo)
        item_plano = plano_por_campo.get(campo)
        esperado = {chave: definicao[chave] for chave in (
            "campo", "destino_xml_futuro", "fonte_primaria", "tratamento_ausencia", "regra_aplicacao",
        )}
        if not item_matriz or any(item_matriz.get(chave) != valor for chave, valor in esperado.items()):
            raise ValueError(f"O campo {campo} diverge da matriz atômica.")
        if not item_plano or any(item_plano.get(chave) != item_matriz.get(chave) for chave in (
            "campo", "destino_xml_futuro", "regra_aplicacao", "estado_inventario",
        )):
            raise ValueError(f"O campo {campo} diverge do plano por blocos.")
        campos.append({
            "grupo": "identidade_partes", "campo": campo,
            "destino_xml_futuro": definicao["destino_xml_futuro"],
            "fonte_primaria": definicao["fonte_primaria"],
            "tratamento_ausencia": definicao["tratamento_ausencia"],
            "regra_aplicacao": definicao["regra_aplicacao"],
            "estado_inventario": item_matriz["estado_inventario"],
            "ordem_emit": definicao["ordem_emit"],
            "ordem_ender_emit": definicao["ordem_ender_emit"],
            "cardinalidade_xsd": dict(definicao["cardinalidade_xsd"]),
            "formato_xsd": dict(definicao["formato_xsd"]),
            "bloqueios_contextuais": _bloqueios(definicao, item_plano),
            "valor_incluido": False, "elemento_xml_criado": False,
            "pronto_para_serializar": False,
        })

    conteudo = {
        "contrato": CONTRATO_ESPECIFICACAO_EMIT, "operacao": "DEVOLUCAO_COMPRA",
        "matriz_contrato": CONTRATO_MATRIZ_ATOMICA,
        "plano_blocos_contrato": CONTRATO_PLANO_BLOCOS,
        "pacote_sha256": plano_conteudo["pacote_sha256"], "bloco": "emit", "posicao_bloco": 2,
        "cardinalidade_bloco": {"minimo": 1, "maximo": 1},
        "campos": campos, "quantidade_campos": len(campos),
        "lacunas_compatibilidade": [
            "CNPJ_ALFANUMERICO_NAO_SUPORTADO", "VALIDACAO_MINIMA_XSD_NAO_IMPLEMENTADA",
            "VALIDACAO_IE_XSD_NAO_IMPLEMENTADA", "VALIDACAO_DOMINIO_UF_XSD_NAO_IMPLEMENTADA",
        ],
        "bloqueios_globais": ["APLICABILIDADE_NORMATIVA_PENDENTE", "XSD_NAO_INSTALADO",
                              "XSD_NAO_APROVADO", "SERIALIZADOR_NAO_IMPLEMENTADO"],
        "politica": {"contem_valores": False, "alterar_cadastro": False,
                     "inferir_decisao_fiscal": False, "construir_elementos_xml": False,
                     "gerar_xml": False, "assinar": False, "transmitir": False},
    }
    return {"conteudo": conteudo, "validacao": validar_especificacao_emit_devolucao(conteudo)}


def validar_especificacao_emit_devolucao(conteudo):
    erros = []

    def erro(caminho, codigo):
        erros.append({"caminho": caminho, "codigo": codigo})

    if not isinstance(conteudo, dict):
        conteudo = {}
        erro("$", "OBJETO_OBRIGATORIO")
    if set(conteudo) != {
        "contrato", "operacao", "matriz_contrato", "plano_blocos_contrato", "pacote_sha256",
        "bloco", "posicao_bloco", "cardinalidade_bloco", "campos", "quantidade_campos",
        "lacunas_compatibilidade", "bloqueios_globais", "politica",
    }:
        erro("$", "CAMPOS_INVALIDOS")
    if conteudo.get("contrato") != CONTRATO_ESPECIFICACAO_EMIT:
        erro("contrato", "CONTRATO_INVALIDO")
    if conteudo.get("operacao") != "DEVOLUCAO_COMPRA":
        erro("operacao", "OPERACAO_INVALIDA")
    if conteudo.get("matriz_contrato") != CONTRATO_MATRIZ_ATOMICA:
        erro("matriz_contrato", "MATRIZ_INVALIDA")
    if conteudo.get("plano_blocos_contrato") != CONTRATO_PLANO_BLOCOS:
        erro("plano_blocos_contrato", "PLANO_INVALIDO")
    if not isinstance(conteudo.get("pacote_sha256"), str) or not re.fullmatch(
            r"[0-9a-f]{64}", conteudo["pacote_sha256"]):
        erro("pacote_sha256", "HASH_INVALIDO")
    if (conteudo.get("bloco") != "emit" or conteudo.get("posicao_bloco") != 2
            or conteudo.get("cardinalidade_bloco") != {"minimo": 1, "maximo": 1}):
        erro("bloco", "BLOCO_DIVERGENTE")

    campos = conteudo.get("campos")
    if not isinstance(campos, list) or len(campos) != len(DEFINICOES_EMIT):
        erro("campos", "CAMPOS_INCOMPLETOS")
        campos = []
    for indice, definicao in enumerate(DEFINICOES_EMIT):
        item = campos[indice] if indice < len(campos) else {}
        caminho = f"campos.{indice}"
        if not isinstance(item, dict) or set(item) != {
            "grupo", "campo", "destino_xml_futuro", "fonte_primaria", "tratamento_ausencia",
            "regra_aplicacao", "estado_inventario", "ordem_emit", "ordem_ender_emit",
            "cardinalidade_xsd", "formato_xsd", "bloqueios_contextuais", "valor_incluido",
            "elemento_xml_criado", "pronto_para_serializar",
        }:
            erro(caminho, "CAMPO_INVALIDO")
            continue
        if any(item[chave] != definicao[chave] for chave in (
            "campo", "destino_xml_futuro", "fonte_primaria", "tratamento_ausencia",
            "regra_aplicacao", "ordem_emit", "ordem_ender_emit", "cardinalidade_xsd", "formato_xsd",
        )):
            erro(caminho, "DEFINICAO_XSD_DIVERGENTE")
        if item["grupo"] != "identidade_partes" or item["estado_inventario"] not in ESTADOS_INVENTARIO:
            erro(caminho, "ORIGEM_DIVERGENTE")
        bloqueios = item["bloqueios_contextuais"]
        exigidos = {"CADASTRO_FILIAL_E_CONFIGURACAO_NAO_CONFIRMADO",
                    "SERIALIZACAO_NAO_IMPLEMENTADA", *definicao["bloqueios_especificos"]}
        if not isinstance(bloqueios, list) or not exigidos.issubset(set(bloqueios)):
            erro(caminho, "BLOQUEIO_CONTEXTUAL_AUSENTE")
        if any(item[chave] is not False for chave in (
            "valor_incluido", "elemento_xml_criado", "pronto_para_serializar",
        )):
            erro(caminho, "CAMPO_LIBERADO_INDEVIDAMENTE")
    if conteudo.get("quantidade_campos") != len(campos) or len(campos) != 11:
        erro("quantidade_campos", "TOTAL_DIVERGENTE")
    lacunas = conteudo.get("lacunas_compatibilidade")
    if not isinstance(lacunas, list) or set(lacunas) != {
        "CNPJ_ALFANUMERICO_NAO_SUPORTADO", "VALIDACAO_MINIMA_XSD_NAO_IMPLEMENTADA",
        "VALIDACAO_IE_XSD_NAO_IMPLEMENTADA", "VALIDACAO_DOMINIO_UF_XSD_NAO_IMPLEMENTADA",
    }:
        erro("lacunas_compatibilidade", "LACUNAS_INVALIDAS")
    bloqueios_globais = conteudo.get("bloqueios_globais")
    if not isinstance(bloqueios_globais, list) or set(bloqueios_globais) != {
        "APLICABILIDADE_NORMATIVA_PENDENTE", "XSD_NAO_INSTALADO",
        "XSD_NAO_APROVADO", "SERIALIZADOR_NAO_IMPLEMENTADO",
    }:
        erro("bloqueios_globais", "BLOQUEIOS_GLOBAIS_INVALIDOS")
    if conteudo.get("politica") != {
        "contem_valores": False, "alterar_cadastro": False, "inferir_decisao_fiscal": False,
        "construir_elementos_xml": False, "gerar_xml": False, "assinar": False,
        "transmitir": False,
    }:
        erro("politica", "POLITICA_INVALIDA")
    return {
        "contrato": CONTRATO_VALIDACAO_ESPECIFICACAO_EMIT,
        "estrutura_valida": not erros, "quantidade_campos": len(campos), "erros": erros,
        "permite_alterar_cadastro": False, "permite_gerar_xml": False,
        "permite_focus": False, "permite_sefaz_direta": False, "permite_emissao": False,
    }
