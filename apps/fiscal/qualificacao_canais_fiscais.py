"""Matriz estática de qualificação dos canais fiscais, sem acesso à rede."""

from pathlib import Path


CONTRATO_MATRIZ_QUALIFICACAO_CANAIS = "fiscal_channel_offline_qualification_matrix_v1"
ESTADO_COMPATIVEL_OFFLINE = "COMPATIVEL_OFFLINE"
ESTADO_LACUNA_INTERNA = "LACUNA_INTERNA"
OPERACOES_OBRIGATORIAS = ("AUTORIZACAO", "CONSULTA", "REJEICAO", "CANCELAMENTO", "INUTILIZACAO", "EVENTOS", "DFE")

DEPENDENCIAS_FOCUS = (
    "CNPJ/IE reais e credenciamento fiscal da filial piloto",
    "conta e token Focus NFe válidos para homologação, fornecidos por canal seguro",
    "cenários tributários e resultados esperados aprovados pelo responsável fiscal/contador",
    "execução externa e arquivamento dos protocolos, XMLs e retornos da homologação",
)
DEPENDENCIAS_SEFAZ_DIRETA = (
    "CNPJ/IE reais e credenciamento fiscal da filial piloto",
    (
        "certificado A1 válido e, somente se houver compatibilidade legada com QR Code "
        "v2, CSC/ID CSC obtidos por canal seguro"
    ),
    "endpoints, schemas e Notas Técnicas oficiais vigentes revalidados para Goiás",
    "cenários tributários e resultados esperados aprovados pelo responsável fiscal/contador",
    "execução externa e arquivamento dos protocolos, XMLs e retornos da homologação",
)

PONTOS_QUALIFICACAO = (
    {"codigo": "FOCUS_AUTORIZACAO", "canal": "FOCUS", "operacao": "AUTORIZACAO", "estado": ESTADO_COMPATIVEL_OFFLINE, "evidencias": (("apps/fiscal/focus_sefaz_adapter.py", ("def transmitir(", '\"status\": \"AUTORIZADO\"')),), "dependencias_externas": DEPENDENCIAS_FOCUS},
    {"codigo": "FOCUS_CONSULTA", "canal": "FOCUS", "operacao": "CONSULTA", "estado": ESTADO_COMPATIVEL_OFFLINE, "evidencias": (("apps/fiscal/focus_sefaz_adapter.py", ("def consultar(",)),), "dependencias_externas": DEPENDENCIAS_FOCUS},
    {"codigo": "FOCUS_REJEICAO", "canal": "FOCUS", "operacao": "REJEICAO", "estado": ESTADO_COMPATIVEL_OFFLINE, "evidencias": (("apps/fiscal/focus_sefaz_adapter.py", ('\"status\": \"REJEITADO\"',)),), "dependencias_externas": DEPENDENCIAS_FOCUS},
    {"codigo": "FOCUS_CANCELAMENTO", "canal": "FOCUS", "operacao": "CANCELAMENTO", "estado": ESTADO_COMPATIVEL_OFFLINE, "evidencias": (("apps/fiscal/focus_sefaz_adapter.py", ("def cancelar(", '\"status\": \"CANCELADO\"')),), "dependencias_externas": DEPENDENCIAS_FOCUS},
    {"codigo": "FOCUS_INUTILIZACAO", "canal": "FOCUS", "operacao": "INUTILIZACAO", "estado": ESTADO_COMPATIVEL_OFFLINE, "evidencias": (("apps/fiscal/focus_sefaz_adapter.py", ("def inutilizar(", '\"status\": \"INUTILIZADA\"')),), "dependencias_externas": DEPENDENCIAS_FOCUS},
    {"codigo": "FOCUS_EVENTOS", "canal": "FOCUS", "operacao": "EVENTOS", "estado": ESTADO_LACUNA_INTERNA, "evidencias": (("apps/fiscal/focus_sefaz_adapter.py", ("class FocusNFeSefazAdapter",)),), "marcadores_que_devem_estar_ausentes": (("apps/fiscal/focus_sefaz_adapter.py", ("def corrigir(", "def manifestar(")),), "motivo": "O adaptador Focus atual não expõe CC-e nem manifestação do destinatário.", "dependencias_externas": DEPENDENCIAS_FOCUS},
    {"codigo": "FOCUS_DFE", "canal": "FOCUS", "operacao": "DFE", "estado": ESTADO_COMPATIVEL_OFFLINE, "evidencias": (("apps/fiscal/focus_dfe_adapter.py", ("def consultar(",)),), "dependencias_externas": DEPENDENCIAS_FOCUS},
    {"codigo": "SEFAZ_DIRETA_AUTORIZACAO", "canal": "SEFAZ_DIRETA_GO", "operacao": "AUTORIZACAO", "estado": ESTADO_COMPATIVEL_OFFLINE, "evidencias": (("apps/fiscal/sefaz_direta/adapter.py", ("def transmitir(", '\"status\": \"AUTORIZADO\"')),), "dependencias_externas": DEPENDENCIAS_SEFAZ_DIRETA},
    {"codigo": "SEFAZ_DIRETA_CONSULTA", "canal": "SEFAZ_DIRETA_GO", "operacao": "CONSULTA", "estado": ESTADO_COMPATIVEL_OFFLINE, "evidencias": (("apps/fiscal/sefaz_direta/adapter.py", ("def consultar(",)),), "dependencias_externas": DEPENDENCIAS_SEFAZ_DIRETA},
    {"codigo": "SEFAZ_DIRETA_REJEICAO", "canal": "SEFAZ_DIRETA_GO", "operacao": "REJEICAO", "estado": ESTADO_COMPATIVEL_OFFLINE, "evidencias": (("apps/fiscal/sefaz_direta/adapter.py", ('\"status\": \"REJEITADO\"',)),), "dependencias_externas": DEPENDENCIAS_SEFAZ_DIRETA},
    {"codigo": "SEFAZ_DIRETA_CANCELAMENTO", "canal": "SEFAZ_DIRETA_GO", "operacao": "CANCELAMENTO", "estado": ESTADO_COMPATIVEL_OFFLINE, "evidencias": (("apps/fiscal/sefaz_direta/adapter.py", ("def cancelar(", '\"status\": \"CANCELADO\"')),), "dependencias_externas": DEPENDENCIAS_SEFAZ_DIRETA},
    {"codigo": "SEFAZ_DIRETA_INUTILIZACAO", "canal": "SEFAZ_DIRETA_GO", "operacao": "INUTILIZACAO", "estado": ESTADO_COMPATIVEL_OFFLINE, "evidencias": (("apps/fiscal/sefaz_direta/adapter.py", ("def inutilizar(", '\"status\": \"INUTILIZADA\"')),), "dependencias_externas": DEPENDENCIAS_SEFAZ_DIRETA},
    {"codigo": "SEFAZ_DIRETA_EVENTOS", "canal": "SEFAZ_DIRETA_GO", "operacao": "EVENTOS", "estado": ESTADO_COMPATIVEL_OFFLINE, "evidencias": (("apps/fiscal/sefaz_direta/cce.py", ("def corrigir(",)), ("apps/fiscal/sefaz_direta/manifestacao.py", ("def manifestar(",))), "dependencias_externas": DEPENDENCIAS_SEFAZ_DIRETA},
    {"codigo": "SEFAZ_DIRETA_DFE", "canal": "SEFAZ_DIRETA_GO", "operacao": "DFE", "estado": ESTADO_COMPATIVEL_OFFLINE, "evidencias": (("apps/fiscal/sefaz_direta/dfe.py", ("def consultar(",)),), "dependencias_externas": DEPENDENCIAS_SEFAZ_DIRETA},
)


def _verificar_marcadores(raiz, grupos, *, devem_existir):
    falhas = []
    for arquivo, marcadores in grupos:
        caminho = raiz / arquivo
        conteudo = caminho.read_text(encoding="utf-8") if caminho.is_file() else ""
        falhos = [marcador for marcador in marcadores if (marcador not in conteudo) == devem_existir]
        if not caminho.is_file():
            falhos = list(marcadores)
        falhas.extend({"arquivo": arquivo, "marcador": marcador} for marcador in falhos)
    return falhas


def construir_matriz_qualificacao_canais(raiz_projeto):
    """Qualifica somente evidências locais; nunca acessa rede nem libera produção."""
    raiz = Path(raiz_projeto)
    resultados = []
    for ponto in PONTOS_QUALIFICACAO:
        ausentes = _verificar_marcadores(raiz, ponto["evidencias"], devem_existir=True)
        inesperados = _verificar_marcadores(raiz, ponto.get("marcadores_que_devem_estar_ausentes", ()), devem_existir=False)
        achado_confirmado = not ausentes and not inesperados
        resultados.append({**ponto, "evidencias_ausentes": ausentes, "marcadores_inesperados": inesperados, "achado_confirmado": achado_confirmado, "evidencia_offline_aprovada": achado_confirmado and ponto["estado"] == ESTADO_COMPATIVEL_OFFLINE, "homologacao_real_executada": False, "producao_liberada": False})

    canais = {}
    for canal in ("FOCUS", "SEFAZ_DIRETA_GO"):
        itens = [item for item in resultados if item["canal"] == canal]
        canais[canal] = {"total_operacoes": len(itens), "compativeis_offline": sum(item["evidencia_offline_aprovada"] for item in itens), "lacunas_internas": [item["operacao"] for item in itens if item["estado"] == ESTADO_LACUNA_INTERNA], "todas_evidencias_locais_confirmadas": all(item["achado_confirmado"] for item in itens), "homologado": False}

    return {"contrato": CONTRATO_MATRIZ_QUALIFICACAO_CANAIS, "operacoes_obrigatorias": OPERACOES_OBRIGATORIAS, "resultados": resultados, "canais": canais, "rede_acessada": False, "credenciais_lidas": False, "homologacao_real_executada": False, "pode_encerrar_homologacao": False, "producao_liberada": False, "proximo_passo": "PREPARAR_HOMOLOGACAO_REAL_SEFAZ_DIRETA_GO_QUANDO_HOUVER_INSUMOS"}
