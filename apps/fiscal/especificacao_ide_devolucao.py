"""Especificação não emissiva dos campos mapeados no bloco ``ide``."""

import re

from .matriz_atomica_devolucao import (
    CONTRATO_MATRIZ_ATOMICA,
    ESTADOS_INVENTARIO,
    validar_matriz_atomica_devolucao,
)
from .plano_blocos_xsd_devolucao import CONTRATO_PLANO_BLOCOS, validar_plano_blocos_xsd


CONTRATO_ESPECIFICACAO_IDE = "supplier_return_ide_field_specification_v1"
CONTRATO_VALIDACAO_ESPECIFICACAO_IDE = "supplier_return_ide_field_specification_validation_v1"


DEFINICOES_IDE = (
    {
        "campo": "identificacao.natureza_operacao",
        "destino_xml_futuro": "NFe/infNFe/ide/natOp",
        "fonte_primaria": "PARECER_CONTADOR", "tratamento_ausencia": "BLOQUEIO",
        "regra_aplicacao": "EXIGIDO_ANTES_DO_GERADOR", "ordem_ide": 3,
        "formato_xsd": {"tipo": "ANONIMO", "base": "TString", "minimo_caracteres": 1,
                        "maximo_caracteres": 60, "padrao": None, "enumeracoes": []},
        "bloqueio_contextual": "PARECER_CONTADOR_NAO_APROVADO",
    },
    {
        "campo": "identificacao.destino_operacao",
        "destino_xml_futuro": "NFe/infNFe/ide/idDest",
        "fonte_primaria": "FILIAL_E_XML_ORIGINAL", "tratamento_ausencia": "BLOQUEIO",
        "regra_aplicacao": "EXIGIDO_ANTES_DO_GERADOR", "ordem_ide": 11,
        "formato_xsd": {"tipo": "ANONIMO", "base": "xs:string", "minimo_caracteres": None,
                        "maximo_caracteres": None, "padrao": None, "enumeracoes": ["1", "2", "3"]},
        "bloqueio_contextual": "DESTINO_OPERACAO_NAO_CONFIRMADO",
    },
    {
        "campo": "identificacao.codigo_municipio_fato_gerador",
        "destino_xml_futuro": "NFe/infNFe/ide/cMunFG",
        "fonte_primaria": "CADASTRO_FILIAL", "tratamento_ausencia": "BLOQUEIO",
        "regra_aplicacao": "EXIGIDO_ANTES_DO_GERADOR", "ordem_ide": 12,
        "formato_xsd": {"tipo": "TCodMunIBGE", "base": "xs:string", "minimo_caracteres": None,
                        "maximo_caracteres": None, "padrao": "[0-9]{7}", "enumeracoes": []},
        "bloqueio_contextual": "CADASTRO_FILIAL_NAO_CONFIRMADO",
    },
    {
        "campo": "identificacao.consumidor_final",
        "destino_xml_futuro": "NFe/infNFe/ide/indFinal",
        "fonte_primaria": "DECISAO_FISCAL", "tratamento_ausencia": "BLOQUEIO",
        "regra_aplicacao": "EXIGIDO_ANTES_DO_GERADOR", "ordem_ide": 21,
        "formato_xsd": {"tipo": "ANONIMO", "base": "xs:string", "minimo_caracteres": None,
                        "maximo_caracteres": None, "padrao": None, "enumeracoes": ["0", "1"]},
        "bloqueio_contextual": "DECISAO_CONSUMIDOR_FINAL_PENDENTE",
    },
    {
        "campo": "identificacao.presenca_comprador",
        "destino_xml_futuro": "NFe/infNFe/ide/indPres",
        "fonte_primaria": "DECISAO_FISCAL", "tratamento_ausencia": "BLOQUEIO",
        "regra_aplicacao": "EXIGIDO_ANTES_DO_GERADOR", "ordem_ide": 22,
        "formato_xsd": {"tipo": "ANONIMO", "base": "xs:string", "minimo_caracteres": None,
                        "maximo_caracteres": None, "padrao": None,
                        "enumeracoes": ["0", "1", "2", "3", "4", "5", "9"]},
        "bloqueio_contextual": "DECISAO_PRESENCA_COMPRADOR_PENDENTE",
    },
)


def _bloqueios(definicao, item_plano):
    return list(dict.fromkeys([definicao["bloqueio_contextual"], *item_plano["bloqueios"]]))


def construir_especificacao_ide_devolucao(*, matriz, plano_blocos):
    """Confronta matriz e plano e descreve ``ide`` sem transportar valores."""
    matriz_conteudo = matriz.get("conteudo", {}) if isinstance(matriz, dict) else {}
    plano_conteudo = plano_blocos.get("conteudo", {}) if isinstance(plano_blocos, dict) else {}
    if not validar_matriz_atomica_devolucao(matriz_conteudo)["estrutura_valida"]:
        raise ValueError("A matriz atômica deve estar íntegra antes da especificação de ide.")
    if not validar_plano_blocos_xsd(plano_conteudo)["estrutura_valida"]:
        raise ValueError("O plano por blocos deve estar íntegro antes da especificação de ide.")
    if plano_conteudo.get("matriz_contrato") != matriz_conteudo.get("contrato"):
        raise ValueError("O plano por blocos não corresponde à matriz informada.")

    blocos_ide = [item for item in plano_conteudo["blocos"] if item["bloco"] == "ide"]
    if len(blocos_ide) != 1:
        raise ValueError("O plano deve conter exatamente um bloco ide.")
    bloco_ide = blocos_ide[0]
    matriz_por_campo = {item["campo"]: item for item in matriz_conteudo["itens"]
                        if item["grupo"] == "identidade_partes"}
    plano_por_campo = {item["campo"]: item for item in bloco_ide["campos"]
                       if item["grupo"] == "identidade_partes"}
    campos = []
    for definicao in DEFINICOES_IDE:
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
            "ordem_ide": definicao["ordem_ide"],
            "cardinalidade_xsd": {"minimo": 1, "maximo": 1},
            "formato_xsd": dict(definicao["formato_xsd"]),
            "bloqueios_contextuais": _bloqueios(definicao, item_plano),
            "valor_incluido": False, "elemento_xml_criado": False,
            "pronto_para_serializar": False,
        })

    conteudo = {
        "contrato": CONTRATO_ESPECIFICACAO_IDE, "operacao": "DEVOLUCAO_COMPRA",
        "matriz_contrato": CONTRATO_MATRIZ_ATOMICA,
        "plano_blocos_contrato": CONTRATO_PLANO_BLOCOS,
        "pacote_sha256": plano_conteudo["pacote_sha256"], "bloco": "ide", "posicao_bloco": 1,
        "cardinalidade_bloco": {"minimo": 1, "maximo": 1},
        "campos": campos, "quantidade_campos": len(campos),
        "bloqueios_globais": ["APLICABILIDADE_NORMATIVA_PENDENTE", "XSD_NAO_INSTALADO",
                              "XSD_NAO_APROVADO", "SERIALIZADOR_NAO_IMPLEMENTADO"],
        "politica": {"contem_valores": False, "inferir_decisao_fiscal": False,
                     "construir_elementos_xml": False, "gerar_xml": False,
                     "assinar": False, "transmitir": False},
    }
    return {"conteudo": conteudo, "validacao": validar_especificacao_ide_devolucao(conteudo)}


def validar_especificacao_ide_devolucao(conteudo):
    erros = []

    def erro(caminho, codigo):
        erros.append({"caminho": caminho, "codigo": codigo})

    if not isinstance(conteudo, dict):
        conteudo = {}
        erro("$", "OBJETO_OBRIGATORIO")
    if set(conteudo) != {"contrato", "operacao", "matriz_contrato", "plano_blocos_contrato",
                         "pacote_sha256", "bloco", "posicao_bloco", "cardinalidade_bloco",
                         "campos", "quantidade_campos", "bloqueios_globais", "politica"}:
        erro("$", "CAMPOS_INVALIDOS")
    if conteudo.get("contrato") != CONTRATO_ESPECIFICACAO_IDE:
        erro("contrato", "CONTRATO_INVALIDO")
    if conteudo.get("operacao") != "DEVOLUCAO_COMPRA":
        erro("operacao", "OPERACAO_INVALIDA")
    if conteudo.get("matriz_contrato") != CONTRATO_MATRIZ_ATOMICA:
        erro("matriz_contrato", "MATRIZ_INVALIDA")
    if conteudo.get("plano_blocos_contrato") != CONTRATO_PLANO_BLOCOS:
        erro("plano_blocos_contrato", "PLANO_INVALIDO")
    if not re.fullmatch(r"[0-9a-f]{64}", conteudo.get("pacote_sha256", "")):
        erro("pacote_sha256", "HASH_INVALIDO")
    if (conteudo.get("bloco") != "ide" or conteudo.get("posicao_bloco") != 1
            or conteudo.get("cardinalidade_bloco") != {"minimo": 1, "maximo": 1}):
        erro("bloco", "BLOCO_DIVERGENTE")

    campos = conteudo.get("campos")
    if not isinstance(campos, list) or len(campos) != len(DEFINICOES_IDE):
        erro("campos", "CAMPOS_INCOMPLETOS")
        campos = []
    for indice, definicao in enumerate(DEFINICOES_IDE):
        item = campos[indice] if indice < len(campos) else {}
        caminho = f"campos.{indice}"
        if not isinstance(item, dict) or set(item) != {
            "grupo", "campo", "destino_xml_futuro", "fonte_primaria", "tratamento_ausencia",
            "regra_aplicacao", "estado_inventario", "ordem_ide", "cardinalidade_xsd",
            "formato_xsd", "bloqueios_contextuais", "valor_incluido", "elemento_xml_criado",
            "pronto_para_serializar",
        }:
            erro(caminho, "CAMPO_INVALIDO")
            continue
        if any(item[chave] != definicao[chave] for chave in (
            "campo", "destino_xml_futuro", "fonte_primaria", "tratamento_ausencia",
            "regra_aplicacao", "ordem_ide", "formato_xsd",
        )):
            erro(caminho, "DEFINICAO_XSD_DIVERGENTE")
        if item["grupo"] != "identidade_partes" or item["estado_inventario"] not in ESTADOS_INVENTARIO:
            erro(caminho, "ORIGEM_DIVERGENTE")
        if item["cardinalidade_xsd"] != {"minimo": 1, "maximo": 1}:
            erro(caminho, "CARDINALIDADE_DIVERGENTE")
        bloqueios = item["bloqueios_contextuais"]
        if (not isinstance(bloqueios, list) or definicao["bloqueio_contextual"] not in bloqueios
                or "SERIALIZACAO_NAO_IMPLEMENTADA" not in bloqueios):
            erro(caminho, "BLOQUEIO_CONTEXTUAL_AUSENTE")
        if any(item[chave] is not False for chave in (
            "valor_incluido", "elemento_xml_criado", "pronto_para_serializar",
        )):
            erro(caminho, "CAMPO_LIBERADO_INDEVIDAMENTE")
    if conteudo.get("quantidade_campos") != len(campos) or len(campos) != 5:
        erro("quantidade_campos", "TOTAL_DIVERGENTE")
    if set(conteudo.get("bloqueios_globais", [])) != {"APLICABILIDADE_NORMATIVA_PENDENTE",
            "XSD_NAO_INSTALADO", "XSD_NAO_APROVADO", "SERIALIZADOR_NAO_IMPLEMENTADO"}:
        erro("bloqueios_globais", "BLOQUEIOS_GLOBAIS_INVALIDOS")
    if conteudo.get("politica") != {"contem_valores": False, "inferir_decisao_fiscal": False,
            "construir_elementos_xml": False, "gerar_xml": False, "assinar": False,
            "transmitir": False}:
        erro("politica", "POLITICA_INVALIDA")
    return {
        "contrato": CONTRATO_VALIDACAO_ESPECIFICACAO_IDE,
        "estrutura_valida": not erros, "quantidade_campos": len(campos), "erros": erros,
        "permite_gerar_xml": False, "permite_focus": False,
        "permite_sefaz_direta": False, "permite_emissao": False,
    }
