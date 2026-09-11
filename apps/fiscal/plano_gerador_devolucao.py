"""Limite de entrada do futuro gerador offline; não produz XML."""

from .matriz_atomica_devolucao import (
    CONTRATO_MATRIZ_ATOMICA,
    validar_matriz_atomica_devolucao,
)
from .portao_prontidao_devolucao import PORTOES_EXTERNOS
from .rastreabilidade_leiaute_devolucao import EVIDENCIA_XSD


CONTRATO_PLANO_GERADOR = "supplier_return_offline_generator_input_plan_v1"
CONTRATO_VALIDACAO_PLANO_GERADOR = "supplier_return_offline_generator_input_plan_validation_v1"
ESTADO_ORDEM_XSD = "CONFIRMADA_NA_EVIDENCIA_ARQUIVADA_NAO_PROMOVIDA"

# Filhos diretos de NFe/infNFe na sequência do leiauteNFe_v4.00.xsd arquivado.
# A confirmação estrutural da evidência não equivale a aprovação para uso operacional.
ORDEM_ESTRUTURAL_XSD = (
    ("ide", "1", "1", "identidade_partes", "MAPEADO_NO_CONTRATO"),
    ("emit", "1", "1", "identidade_partes", "MAPEADO_NO_CONTRATO"),
    ("avulsa", "0", "1", "", "FORA_DO_ESCOPO_ATUAL"),
    ("dest", "0", "1", "identidade_partes", "MAPEADO_NO_CONTRATO"),
    ("retirada", "0", "1", "", "FORA_DO_ESCOPO_ATUAL"),
    ("entrega", "0", "1", "", "FORA_DO_ESCOPO_ATUAL"),
    ("autXML", "0", "10", "", "FORA_DO_ESCOPO_ATUAL"),
    (
        "det", "1", "990",
        "referencias_itens|produtos|tributos_itens|ajustes_comerciais|"
        "observacoes_fiscais|ipi_devolvido|icms_st_fcp|rtc",
        "MAPEADO_NO_CONTRATO",
    ),
    ("total", "1", "1", "totalizacao|ipi_devolvido|icms_st_fcp|rtc", "MAPEADO_NO_CONTRATO"),
    ("transp", "1", "1", "transporte", "MAPEADO_NO_CONTRATO"),
    ("cobr", "0", "1", "", "FORA_DO_ESCOPO_ATUAL"),
    ("pag", "1", "1", "pagamento_fiscal", "MAPEADO_NO_CONTRATO"),
    ("infIntermed", "0", "1", "", "FORA_DO_ESCOPO_ATUAL"),
    ("infAdic", "0", "1", "observacoes_fiscais", "MAPEADO_NO_CONTRATO"),
    ("exporta", "0", "1", "", "FORA_DO_ESCOPO_ATUAL"),
    ("compra", "0", "1", "", "FORA_DO_ESCOPO_ATUAL"),
    ("cana", "0", "1", "", "FORA_DO_ESCOPO_ATUAL"),
    ("infRespTec", "0", "1", "", "FORA_DO_ESCOPO_ATUAL"),
    ("infSolicNFF", "0", "1", "", "FORA_DO_ESCOPO_ATUAL"),
    ("agropecuario", "0", "1", "", "FORA_DO_ESCOPO_ATUAL"),
    ("infPAA", "0", "1", "", "FORA_DO_ESCOPO_ATUAL"),
)

REQUISITOS_SUBCONTRATOS = (
    ("identidade_partes", "dados_completos"),
    ("produtos", "dados_completos"),
    ("tributos_itens", "dados_completos"),
    ("ajustes_comerciais", "origem_completa"),
    ("transporte", "origem_completa"),
    ("totalizacao", "origem_completa"),
    ("pagamento_fiscal", "dados_completos"),
    ("observacoes_fiscais", "origem_completa"),
    ("ipi_devolvido", "escopo_fiscal_suportado"),
    ("icms_st_fcp", "escopo_fiscal_suportado"),
    ("rtc", "vigencia_confirmada"),
    ("rtc", "escopo_fiscal_suportado"),
)


def _sem_duplicidade(itens):
    saida, vistos = [], set()
    for item in itens:
        chave = (item["grupo"], item["campo"], item["codigo"])
        if chave not in vistos:
            vistos.add(chave)
            saida.append(item)
    return saida


def _ordem_estrutural():
    return [
        {
            "posicao": posicao,
            "elemento": elemento,
            "min_ocorrencias": minimo,
            "max_ocorrencias": maximo,
            "fontes": fontes,
            "escopo": escopo,
            "estado": ESTADO_ORDEM_XSD,
        }
        for posicao, (elemento, minimo, maximo, fontes, escopo)
        in enumerate(ORDEM_ESTRUTURAL_XSD, 1)
    ]


def construir_plano_gerador_offline(resultado_extracao):
    resultado = resultado_extracao if isinstance(resultado_extracao, dict) else {}
    matriz = resultado.get("matriz_atomica", {})
    matriz_conteudo = matriz.get("conteudo", {}) if isinstance(matriz, dict) else {}
    validacao_matriz = validar_matriz_atomica_devolucao(matriz_conteudo)
    bloqueios = []

    def bloquear(grupo, campo, codigo):
        bloqueios.append({"grupo": grupo, "campo": campo, "codigo": codigo})

    if not validacao_matriz["estrutura_valida"]:
        bloquear("matriz_atomica", "$", "MATRIZ_ATOMICA_INVALIDA")
    for item in matriz_conteudo.get("itens", []) if isinstance(matriz_conteudo.get("itens"), list) else []:
        if item.get("estado_inventario") != "DISPONIVEL_NO_CONTRATO":
            bloquear(
                item.get("grupo", "matriz_atomica"),
                item.get("campo", ""),
                "CAMPO_NAO_DISPONIVEL_PARA_GERADOR",
            )
        if "[" in item.get("destino_xml_futuro", ""):
            bloquear(
                item.get("grupo", "matriz_atomica"),
                item.get("campo", ""),
                "DESTINO_XML_DEPENDE_LEIAUTE_VIGENTE",
            )

    requisitos = []
    for grupo, indicador in REQUISITOS_SUBCONTRATOS:
        validacao = resultado.get(grupo, {}).get("validacao", {})
        atendido = validacao.get(indicador) is True
        requisitos.append({"grupo": grupo, "indicador": indicador, "atendido": atendido})
        if not atendido:
            bloquear(grupo, indicador, "SUBCONTRATO_NAO_PRONTO_PARA_GERADOR")

    portoes = resultado.get("portao_prontidao", {}).get("conteudo", {}).get("portoes_externos", {})
    for nome, codigo in PORTOES_EXTERNOS:
        if portoes.get(nome) is not True:
            bloquear("portao_externo", nome, codigo)

    bloquear("evidencia_xsd", "arquivo_principal", "XSD_APLICAVEL_NAO_INSTALADO")
    bloquear("evidencia_xsd", "pacote_aprovado", "XSD_APLICAVEL_NAO_APROVADO")
    bloquear("ordem_estrutural", "$", "ORDEM_NAO_APROVADA_PARA_GERADOR")
    bloquear("gerador", "$", "SERIALIZADOR_OFFLINE_NAO_IMPLEMENTADO")
    bloqueios = _sem_duplicidade(bloqueios)

    conteudo = {
        "contrato": CONTRATO_PLANO_GERADOR,
        "operacao": "DEVOLUCAO_COMPRA",
        "matriz_contrato": matriz_conteudo.get("contrato", ""),
        "evidencia_xsd": dict(EVIDENCIA_XSD),
        "ordem_estrutural": _ordem_estrutural(),
        "requisitos_subcontratos": requisitos,
        "bloqueios": bloqueios,
        "entrada_aceita": not bloqueios,
        "politica": {
            "ordem_confirmada_na_evidencia": True,
            "ordem_aprovada_para_gerador": False,
            "serializador_implementado": False,
            "produzir_xml": False,
            "assinar": False,
            "acessar_certificado": False,
            "transmitir": False,
            "alterar_provedor": False,
        },
    }
    return {"conteudo": conteudo, "validacao": validar_plano_gerador_offline(conteudo)}


def validar_plano_gerador_offline(conteudo):
    erros = []

    def erro(caminho, codigo):
        erros.append({"caminho": caminho, "codigo": codigo})

    if not isinstance(conteudo, dict):
        conteudo = {}
        erro("$", "OBJETO_OBRIGATORIO")
    campos = {
        "contrato", "operacao", "matriz_contrato", "evidencia_xsd",
        "ordem_estrutural", "requisitos_subcontratos", "bloqueios",
        "entrada_aceita", "politica",
    }
    if set(conteudo) != campos:
        erro("$", "CAMPOS_INVALIDOS")
    if conteudo.get("contrato") != CONTRATO_PLANO_GERADOR:
        erro("contrato", "CONTRATO_INVALIDO")
    if conteudo.get("operacao") != "DEVOLUCAO_COMPRA":
        erro("operacao", "OPERACAO_NAO_SUPORTADA")
    if conteudo.get("matriz_contrato") != CONTRATO_MATRIZ_ATOMICA:
        erro("matriz_contrato", "MATRIZ_INVALIDA")
    if conteudo.get("evidencia_xsd") != EVIDENCIA_XSD:
        erro("evidencia_xsd", "EVIDENCIA_DIVERGENTE")
    if conteudo.get("ordem_estrutural") != _ordem_estrutural():
        erro("ordem_estrutural", "ORDEM_DIVERGENTE")

    requisitos_esperados = {(grupo, indicador) for grupo, indicador in REQUISITOS_SUBCONTRATOS}
    requisitos = conteudo.get("requisitos_subcontratos")
    if not isinstance(requisitos, list) or {
        (item.get("grupo"), item.get("indicador"))
        for item in requisitos if isinstance(item, dict)
    } != requisitos_esperados:
        erro("requisitos_subcontratos", "REQUISITOS_INCOMPLETOS")
        requisitos = []
    for indice, item in enumerate(requisitos):
        if not isinstance(item, dict) or set(item) != {"grupo", "indicador", "atendido"}:
            erro(f"requisitos_subcontratos.{indice}", "REQUISITO_INVALIDO")
        elif type(item["atendido"]) is not bool:
            erro(f"requisitos_subcontratos.{indice}.atendido", "BOOLEANO_OBRIGATORIO")

    bloqueios = conteudo.get("bloqueios")
    if not isinstance(bloqueios, list) or not bloqueios:
        erro("bloqueios", "BLOQUEIOS_OBRIGATORIOS")
        bloqueios = []
    elif any(
        not isinstance(item, dict) or set(item) != {"grupo", "campo", "codigo"}
        or not all(isinstance(item[chave], str) for chave in ("grupo", "campo", "codigo"))
        for item in bloqueios
    ):
        erro("bloqueios", "BLOQUEIO_INVALIDO")
    codigos = {item.get("codigo") for item in bloqueios if isinstance(item, dict)}
    for codigo in {
        "XSD_APLICAVEL_NAO_INSTALADO",
        "XSD_APLICAVEL_NAO_APROVADO",
        "ORDEM_NAO_APROVADA_PARA_GERADOR",
        "SERIALIZADOR_OFFLINE_NAO_IMPLEMENTADO",
    }:
        if codigo not in codigos:
            erro("bloqueios", "BLOQUEIO_ESTRUTURAL_REMOVIDO")

    if conteudo.get("entrada_aceita") is not False:
        erro("entrada_aceita", "ENTRADA_NAO_PODE_SER_LIBERADA")
    politica = {
        "ordem_confirmada_na_evidencia": True,
        "ordem_aprovada_para_gerador": False,
        "serializador_implementado": False,
        "produzir_xml": False,
        "assinar": False,
        "acessar_certificado": False,
        "transmitir": False,
        "alterar_provedor": False,
    }
    if conteudo.get("politica") != politica:
        erro("politica", "POLITICA_DE_BLOQUEIO_INVALIDA")
    return {
        "contrato": CONTRATO_VALIDACAO_PLANO_GERADOR,
        "estrutura_valida": not erros,
        "quantidade_etapas": len(conteudo.get("ordem_estrutural", []))
        if isinstance(conteudo.get("ordem_estrutural"), list) else 0,
        "quantidade_bloqueios": len(bloqueios),
        "entrada_aceita": False,
        "erros": erros,
        "permite_gerar_xml": False,
        "permite_focus": False,
        "permite_sefaz_direta": False,
        "permite_emissao": False,
    }