"""Plano por bloco dos caminhos XSD confirmados; não constrói XML."""

from .compatibilidade_matriz_xsd import CONTRATO_COMPATIBILIDADE_XSD
from .matriz_atomica_devolucao import CONTRATO_MATRIZ_ATOMICA
from .plano_gerador_devolucao import ORDEM_ESTRUTURAL_XSD


CONTRATO_PLANO_BLOCOS = "supplier_return_xsd_block_build_plan_v1"
CONTRATO_VALIDACAO_PLANO_BLOCOS = "supplier_return_xsd_block_build_plan_validation_v1"


def _ordem_blocos():
    return {
        nome: {"posicao": posicao, "min_ocorrencias": minimo, "max_ocorrencias": maximo}
        for posicao, (nome, minimo, maximo, _fontes, _escopo) in enumerate(ORDEM_ESTRUTURAL_XSD, 1)
    }


def _bloqueios_item(item_matriz):
    bloqueios = ["SERIALIZACAO_NAO_IMPLEMENTADA"]
    if item_matriz["estado_inventario"] != "DISPONIVEL_NO_CONTRATO":
        bloqueios.append("ORIGEM_NAO_PRONTA")
    if item_matriz["regra_aplicacao"] == "PRESENTE_QUANDO_CONDICAO_APLICAVEL":
        bloqueios.append("CONDICAO_FISCAL_NAO_APROVADA")
    if item_matriz["regra_aplicacao"] == "SOMENTE_APOS_DECISAO_APROVADA":
        bloqueios.append("DECISAO_FISCAL_NAO_APROVADA")
    return bloqueios


def construir_plano_blocos_xsd(*, matriz, compatibilidade):
    matriz_conteudo = matriz.get("conteudo", {}) if isinstance(matriz, dict) else {}
    comp_conteudo = compatibilidade.get("conteudo", {}) if isinstance(compatibilidade, dict) else {}
    if matriz_conteudo.get("contrato") != CONTRATO_MATRIZ_ATOMICA:
        raise ValueError("Matriz atômica inválida para o plano por blocos.")
    if comp_conteudo.get("contrato") != CONTRATO_COMPATIBILIDADE_XSD:
        raise ValueError("Relatório de compatibilidade XSD inválido para o plano por blocos.")
    if comp_conteudo.get("resumo", {}).get("DIVERGENTE_DO_XSD_AUDITADO") != 0:
        raise ValueError("O plano por blocos exige compatibilidade sem divergências XSD.")

    matriz_por_chave = {
        (item["grupo"], item["campo"]): item for item in matriz_conteudo.get("itens", [])
    }
    ordem = _ordem_blocos()
    blocos = {}
    for item in comp_conteudo.get("itens", []):
        if item.get("estado") != "CONFIRMADO_NO_XSD_AUDITADO":
            continue
        chave = (item["grupo"], item["campo"])
        item_matriz = matriz_por_chave.get(chave)
        if not item_matriz or item_matriz["destino_xml_futuro"] != item["destino_xml_futuro"]:
            raise ValueError("Relatório de compatibilidade não corresponde à matriz atômica.")
        partes = item["destino_xml_futuro"].split("/")
        bloco = partes[2]
        if bloco not in ordem:
            raise ValueError("Destino confirmado fora da ordem estrutural de infNFe.")
        destino = blocos.setdefault(bloco, {**ordem[bloco], "bloco": bloco, "campos": []})
        destino["campos"].append({
            "grupo": item["grupo"],
            "campo": item["campo"],
            "destino_xml_futuro": item["destino_xml_futuro"],
            "regra_aplicacao": item_matriz["regra_aplicacao"],
            "estado_inventario": item_matriz["estado_inventario"],
            "alternativas_exigidas": item["alternativas_exigidas"],
            "bloqueios": _bloqueios_item(item_matriz),
            "pronto_para_serializar": False,
        })
    blocos_ordenados = sorted(blocos.values(), key=lambda item: item["posicao"])
    for bloco in blocos_ordenados:
        bloco["quantidade_campos"] = len(bloco["campos"])
        bloco["pronto_para_construir"] = False

    conteudo = {
        "contrato": CONTRATO_PLANO_BLOCOS,
        "operacao": "DEVOLUCAO_COMPRA",
        "matriz_contrato": matriz_conteudo.get("contrato"),
        "compatibilidade_contrato": comp_conteudo.get("contrato"),
        "pacote_sha256": comp_conteudo.get("pacote_sha256"),
        "blocos": blocos_ordenados,
        "quantidade_campos_confirmados": sum(bloco["quantidade_campos"] for bloco in blocos_ordenados),
        "bloqueios_globais": [
            "APLICABILIDADE_NORMATIVA_PENDENTE",
            "XSD_NAO_INSTALADO",
            "XSD_NAO_APROVADO",
            "SERIALIZADOR_NAO_IMPLEMENTADO",
        ],
        "politica": {
            "contem_valores": False,
            "construir_arvore_xml": False,
            "promover_schema": False,
            "gerar_xml": False,
            "assinar": False,
            "transmitir": False,
        },
    }
    return {"conteudo": conteudo, "validacao": validar_plano_blocos_xsd(conteudo)}


def validar_plano_blocos_xsd(conteudo):
    erros = []
    def erro(caminho, codigo):
        erros.append({"caminho": caminho, "codigo": codigo})
    if not isinstance(conteudo, dict):
        conteudo = {}
        erro("$", "OBJETO_OBRIGATORIO")
    campos = {
        "contrato", "operacao", "matriz_contrato", "compatibilidade_contrato",
        "pacote_sha256", "blocos", "quantidade_campos_confirmados",
        "bloqueios_globais", "politica",
    }
    if set(conteudo) != campos:
        erro("$", "CAMPOS_INVALIDOS")
    if conteudo.get("contrato") != CONTRATO_PLANO_BLOCOS:
        erro("contrato", "CONTRATO_INVALIDO")
    if conteudo.get("operacao") != "DEVOLUCAO_COMPRA":
        erro("operacao", "OPERACAO_INVALIDA")
    if conteudo.get("matriz_contrato") != CONTRATO_MATRIZ_ATOMICA:
        erro("matriz_contrato", "MATRIZ_INVALIDA")
    if conteudo.get("compatibilidade_contrato") != CONTRATO_COMPATIBILIDADE_XSD:
        erro("compatibilidade_contrato", "COMPATIBILIDADE_INVALIDA")
    blocos = conteudo.get("blocos")
    ordem = _ordem_blocos()
    if not isinstance(blocos, list) or not blocos:
        erro("blocos", "BLOCOS_OBRIGATORIOS")
        blocos = []
    posicoes = []
    total = 0
    for indice, bloco in enumerate(blocos):
        caminho = f"blocos.{indice}"
        if not isinstance(bloco, dict) or set(bloco) != {
            "posicao", "min_ocorrencias", "max_ocorrencias", "bloco", "campos",
            "quantidade_campos", "pronto_para_construir",
        }:
            erro(caminho, "BLOCO_INVALIDO")
            continue
        esperado = ordem.get(bloco["bloco"])
        if not esperado or any(bloco[chave] != esperado[chave] for chave in esperado):
            erro(caminho, "ORDEM_CARDINALIDADE_DIVERGENTE")
        posicoes.append(bloco["posicao"])
        campos_bloco = bloco["campos"]
        if not isinstance(campos_bloco, list):
            erro(caminho, "CONTAGEM_DIVERGENTE")
            campos_bloco = []
        elif bloco["quantidade_campos"] != len(campos_bloco):
            erro(caminho, "CONTAGEM_DIVERGENTE")
        total += len(campos_bloco)
        for campo_indice, campo in enumerate(campos_bloco):
            if not isinstance(campo, dict) or set(campo) != {
                "grupo", "campo", "destino_xml_futuro", "regra_aplicacao",
                "estado_inventario", "alternativas_exigidas", "bloqueios",
                "pronto_para_serializar",
            }:
                erro(f"{caminho}.campos.{campo_indice}", "CAMPO_INVALIDO")
            elif not campo["bloqueios"] or campo["pronto_para_serializar"] is not False:
                erro(f"{caminho}.campos.{campo_indice}", "CAMPO_LIBERADO_INDEVIDAMENTE")
        if bloco["pronto_para_construir"] is not False:
            erro(caminho, "BLOCO_LIBERADO_INDEVIDAMENTE")
    if posicoes != sorted(posicoes) or len(posicoes) != len(set(posicoes)):
        erro("blocos", "ORDEM_DIVERGENTE")
    if conteudo.get("quantidade_campos_confirmados") != total or total != 105:
        erro("quantidade_campos_confirmados", "TOTAL_DIVERGENTE")
    bloqueios = {
        "APLICABILIDADE_NORMATIVA_PENDENTE", "XSD_NAO_INSTALADO",
        "XSD_NAO_APROVADO", "SERIALIZADOR_NAO_IMPLEMENTADO",
    }
    if set(conteudo.get("bloqueios_globais", [])) != bloqueios:
        erro("bloqueios_globais", "BLOQUEIOS_GLOBAIS_INVALIDOS")
    politica = {
        "contem_valores": False, "construir_arvore_xml": False,
        "promover_schema": False, "gerar_xml": False,
        "assinar": False, "transmitir": False,
    }
    if conteudo.get("politica") != politica:
        erro("politica", "POLITICA_INVALIDA")
    return {
        "contrato": CONTRATO_VALIDACAO_PLANO_BLOCOS,
        "estrutura_valida": not erros,
        "quantidade_blocos": len(blocos),
        "quantidade_campos": total,
        "erros": erros,
        "permite_gerar_xml": False,
        "permite_focus": False,
        "permite_sefaz_direta": False,
        "permite_emissao": False,
    }