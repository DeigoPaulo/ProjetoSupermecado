"""Portão diagnóstico dos contratos da devolução. Nunca autoriza XML ou emissão."""

from .ajustes_comerciais_devolucao import CONTRATO_AJUSTES_COMERCIAIS
from .contrato_devolucao import CONTRATO
from .icms_st_fcp_contrato import CONTRATO_ICMS_ST_FCP
from .identidade_partes_devolucao import CONTRATO_IDENTIDADE_PARTES
from .ipi_devolvido_contrato import CONTRATO_IPI_DEVOLVIDO
from .observacoes_fiscais_devolucao import CONTRATO_OBSERVACOES
from .pagamento_fiscal_devolucao import CONTRATO_PAGAMENTO
from .produtos_devolucao import CONTRATO_PRODUTOS
from .referencias_item_devolucao import CONTRATO_REFERENCIAS_ITEM
from .rtc_devolucao_contrato import CONTRATO_RTC
from .totalizacao_diagnostica_devolucao import CONTRATO_TOTALIZACAO
from .transporte_contrato_devolucao import CONTRATO_TRANSPORTE
from .tributos_itens_devolucao import CONTRATO_TRIBUTOS_ITENS


CONTRATO_PORTAO = "supplier_return_readiness_gate_v1"
CONTRATO_VALIDACAO_PORTAO = "supplier_return_readiness_gate_validation_v1"

SUBCONTRATOS = (
    ("envelope", CONTRATO, "validacao", "estrutura_valida"),
    ("referencias_itens", CONTRATO_REFERENCIAS_ITEM, "validacao_estrutural", "origem_conferida"),
    ("identidade_partes", CONTRATO_IDENTIDADE_PARTES, "validacao", "dados_completos"),
    ("produtos", CONTRATO_PRODUTOS, "validacao", "dados_completos"),
    ("tributos_itens", CONTRATO_TRIBUTOS_ITENS, "validacao", "origem_completa"),
    ("ajustes_comerciais", CONTRATO_AJUSTES_COMERCIAIS, "validacao", "origem_completa"),
    ("transporte", CONTRATO_TRANSPORTE, "validacao", "origem_completa"),
    ("totalizacao", CONTRATO_TOTALIZACAO, "validacao", "origem_completa"),
    ("pagamento_fiscal", CONTRATO_PAGAMENTO, "validacao", "dados_completos"),
    ("observacoes_fiscais", CONTRATO_OBSERVACOES, "validacao", "origem_completa"),
    ("ipi_devolvido", CONTRATO_IPI_DEVOLVIDO, "validacao", "origem_completa"),
    ("icms_st_fcp", CONTRATO_ICMS_ST_FCP, "validacao", "origem_completa"),
    ("rtc", CONTRATO_RTC, "validacao", "origem_completa"),
)

PORTOES_EXTERNOS = (
    ("analise_normativa_integral", "ANALISE_NORMATIVA_INTEGRAL_PENDENTE"),
    ("matriz_tributaria_aprovada", "MATRIZ_TRIBUTARIA_NAO_APROVADA"),
    ("dados_reais_filial", "DADOS_REAIS_PENDENTES"),
    ("casos_contador_aprovados", "HOMOLOGACAO_CONTADOR_PENDENTE"),
    ("schema_aplicavel_homologado", "SCHEMA_APLICAVEL_NAO_HOMOLOGADO"),
    ("paridade_focus_validada", "FOCUS_NAO_HOMOLOGADO"),
    ("paridade_sefaz_direta_validada", "SEFAZ_DIRETA_NAO_HOMOLOGADA"),
)


def _bloqueios(resultado, validacao):
    origem = resultado.get("bloqueios", []) if isinstance(resultado, dict) else []
    if not origem and isinstance(validacao, dict):
        origem = validacao.get("bloqueios", [])
    normalizados = []
    for item in origem if isinstance(origem, list) else []:
        if isinstance(item, dict) and isinstance(item.get("grupo"), str) and isinstance(item.get("codigo"), str):
            normalizados.append({"grupo": item["grupo"], "codigo": item["codigo"]})
    return normalizados


def _sem_duplicidade(itens):
    saida, vistos = [], set()
    for item in itens:
        chave = (item["grupo"], item["codigo"])
        if chave not in vistos:
            vistos.add(chave)
            saida.append(item)
    return saida


def construir_portao_prontidao(resultado_extracao):
    """Consolida diagnósticos já calculados, sem transformar pendência em autorização."""
    verificacoes = []
    for grupo, contrato_esperado, chave_validacao, chave_origem in SUBCONTRATOS:
        resultado = (
            {"conteudo": resultado_extracao.get("conteudo"), "validacao": resultado_extracao.get("validacao")}
            if grupo == "envelope"
            else resultado_extracao.get(grupo)
        )
        resultado = resultado if isinstance(resultado, dict) else {}
        conteudo = resultado.get("conteudo") if isinstance(resultado.get("conteudo"), dict) else {}
        validacao = resultado.get(chave_validacao) if isinstance(resultado.get(chave_validacao), dict) else {}
        estrutura_valida = bool(validacao.get("estrutura_valida")) and conteudo.get("contrato") == contrato_esperado
        origem_conferida = estrutura_valida and bool(
            resultado.get(chave_origem) if chave_validacao == "validacao_estrutural" else validacao.get(chave_origem)
        )
        permite_gerar_xml = validacao.get("permite_gerar_xml") is not False
        permite_emissao = validacao.get("permite_emissao") is not False
        if chave_validacao == "validacao_estrutural":
            permite_gerar_xml = permite_gerar_xml or resultado.get("permite_gerar_xml") is not False
            permite_emissao = permite_emissao or resultado.get("permite_emissao") is not False
        verificacoes.append({
            "grupo": grupo,
            "contrato": conteudo.get("contrato", ""),
            "estrutura_valida": estrutura_valida,
            "origem_conferida": origem_conferida,
            "permite_gerar_xml": permite_gerar_xml,
            "permite_emissao": permite_emissao,
            "bloqueios": _bloqueios(resultado, validacao),
        })

    bloqueios = [item for verificacao in verificacoes for item in verificacao["bloqueios"]]
    bloqueios.extend({"grupo": "portao_externo", "codigo": codigo} for _, codigo in PORTOES_EXTERNOS)
    conteudo = {
        "contrato": CONTRATO_PORTAO,
        "operacao": "DEVOLUCAO_COMPRA",
        "permite_emissao": False,
        "estrutura_consolidada": all(item["estrutura_valida"] for item in verificacoes),
        "origens_conferidas": all(item["origem_conferida"] for item in verificacoes),
        "todos_nao_emissivos": all(
            not item["permite_gerar_xml"] and not item["permite_emissao"] for item in verificacoes
        ),
        "verificacoes": verificacoes,
        "portoes_externos": {nome: False for nome, _ in PORTOES_EXTERNOS},
        "politica": {
            "falhar_fechado": True,
            "permitir_xml": False,
            "permitir_emissao": False,
            "alterar_flags_provedores": False,
        },
        "bloqueios_consolidados": _sem_duplicidade(bloqueios),
    }
    return {"conteudo": conteudo, "validacao": validar_portao_prontidao(conteudo)}


def validar_portao_prontidao(conteudo):
    erros, pendencias = [], []

    def erro(caminho, codigo):
        erros.append({"caminho": caminho, "codigo": codigo})

    if not isinstance(conteudo, dict):
        erro("$", "OBJETO_OBRIGATORIO")
        conteudo = {}
    campos = {
        "contrato", "operacao", "permite_emissao", "estrutura_consolidada",
        "origens_conferidas", "todos_nao_emissivos", "verificacoes",
        "portoes_externos", "politica", "bloqueios_consolidados",
    }
    if set(conteudo) != campos:
        erro("$", "CAMPOS_INVALIDOS")
    if conteudo.get("contrato") != CONTRATO_PORTAO:
        erro("contrato", "CONTRATO_INVALIDO")
    if conteudo.get("operacao") != "DEVOLUCAO_COMPRA":
        erro("operacao", "OPERACAO_NAO_SUPORTADA")
    if conteudo.get("permite_emissao") is not False:
        erro("permite_emissao", "EMISSAO_PROIBIDA")

    verificacoes = conteudo.get("verificacoes")
    if not isinstance(verificacoes, list):
        erro("verificacoes", "LISTA_OBRIGATORIA")
        verificacoes = []
    if len(verificacoes) != len(SUBCONTRATOS):
        erro("verificacoes", "SUBCONTRATOS_INCOMPLETOS")
    for indice, esperado in enumerate(SUBCONTRATOS):
        caminho = f"verificacoes.{indice}"
        item = verificacoes[indice] if indice < len(verificacoes) else {}
        if not isinstance(item, dict) or set(item) != {
            "grupo", "contrato", "estrutura_valida", "origem_conferida",
            "permite_gerar_xml", "permite_emissao", "bloqueios",
        }:
            erro(caminho, "VERIFICACAO_INVALIDA")
            continue
        if item["grupo"] != esperado[0] or item["contrato"] != esperado[1]:
            erro(caminho, "SUBCONTRATO_DIVERGENTE")
        for campo in ("estrutura_valida", "origem_conferida", "permite_gerar_xml", "permite_emissao"):
            if type(item[campo]) is not bool:
                erro(f"{caminho}.{campo}", "BOOLEANO_OBRIGATORIO")
        if item["permite_gerar_xml"]:
            erro(caminho, "SUBCONTRATO_TENTOU_LIBERAR_XML")
        if item["permite_emissao"]:
            erro(caminho, "SUBCONTRATO_TENTOU_LIBERAR_EMISSAO")
        if not isinstance(item["bloqueios"], list):
            erro(f"{caminho}.bloqueios", "LISTA_OBRIGATORIA")
        if item["estrutura_valida"] is False:
            pendencias.append({"grupo": item["grupo"], "codigo": "ESTRUTURA_INVALIDA"})
        if item["origem_conferida"] is False:
            pendencias.append({"grupo": item["grupo"], "codigo": "ORIGEM_NAO_CONFERIDA"})

    calculos = {
        "estrutura_consolidada": len(verificacoes) == len(SUBCONTRATOS) and all(
            isinstance(item, dict) and item.get("estrutura_valida") is True for item in verificacoes
        ),
        "origens_conferidas": len(verificacoes) == len(SUBCONTRATOS) and all(
            isinstance(item, dict) and item.get("origem_conferida") is True for item in verificacoes
        ),
        "todos_nao_emissivos": len(verificacoes) == len(SUBCONTRATOS) and all(
            isinstance(item, dict) and item.get("permite_gerar_xml") is False
            and item.get("permite_emissao") is False for item in verificacoes
        ),
    }
    for campo, esperado in calculos.items():
        if conteudo.get(campo) is not esperado:
            erro(campo, "TOTALIZADOR_DIVERGENTE")

    externos = conteudo.get("portoes_externos")
    nomes_externos = {nome for nome, _ in PORTOES_EXTERNOS}
    if not isinstance(externos, dict) or set(externos) != nomes_externos:
        erro("portoes_externos", "PORTOES_EXTERNOS_INVALIDOS")
        externos = {}
    for nome, codigo in PORTOES_EXTERNOS:
        if externos.get(nome) is not False:
            erro(f"portoes_externos.{nome}", "PORTAO_EXTERNO_NAO_PODE_SER_ATIVADO")
        pendencias.append({"grupo": "portao_externo", "codigo": codigo})

    politica = conteudo.get("politica")
    politica_esperada = {
        "falhar_fechado": True,
        "permitir_xml": False,
        "permitir_emissao": False,
        "alterar_flags_provedores": False,
    }
    if politica != politica_esperada:
        erro("politica", "POLITICA_DE_BLOQUEIO_INVALIDA")
    bloqueios = conteudo.get("bloqueios_consolidados")
    if not isinstance(bloqueios, list) or any(
        not isinstance(item, dict) or set(item) != {"grupo", "codigo"}
        or not isinstance(item["grupo"], str) or not isinstance(item["codigo"], str)
        for item in bloqueios if isinstance(bloqueios, list)
    ):
        erro("bloqueios_consolidados", "BLOQUEIOS_INVALIDOS")

    return {
        "contrato": CONTRATO_VALIDACAO_PORTAO,
        "estrutura_valida": not erros,
        "estrutura_consolidada": calculos["estrutura_consolidada"],
        "origens_conferidas": calculos["origens_conferidas"],
        "pronto_para_gerador": False,
        "pronto_para_homologacao": False,
        "erros": erros,
        "pendencias": _sem_duplicidade(pendencias),
        "bloqueios": bloqueios if isinstance(bloqueios, list) else [],
        "permite_gerar_xml": False,
        "permite_emissao": False,
    }
