"""Roteiros não executáveis para homologação externa futura dos canais fiscais."""

from .qualificacao_canais_fiscais import (
    ESTADO_COMPATIVEL_OFFLINE,
    construir_matriz_qualificacao_canais,
)


CONTRATO_ROTEIROS_HOMOLOGACAO = "fiscal_channel_homologation_runbook_v1"

EVIDENCIAS_COMUNS = (
    "filial, CNPJ, ambiente, canal e operação identificados",
    "data/hora, responsável técnico e versão implantada",
    "hash do conteúdo enviado sem credenciais, certificado, CSC ou token",
    "retorno integral protegido, código de status, motivo e protocolo quando existente",
    "resultado esperado confrontado com o resultado obtido",
    "registro da recuperação após falha sem duplicidade quando aplicável",
)

CENARIOS = {
    "AUTORIZACAO": (
        "autorizar documento fiscal válido no ambiente de homologação",
        "repetir a mesma referência/idempotência e comprovar ausência de duplicidade",
        "simular timeout controlado e consultar antes de retransmitir",
    ),
    "CONSULTA": (
        "consultar documento autorizado e comparar chave, protocolo e XML processado",
        "consultar documento cancelado quando houver cenário preparado",
        "consultar referência inexistente e comprovar tratamento sem retransmissão automática",
    ),
    "REJEICAO": (
        "executar rejeição controlada previamente aprovada pelo responsável fiscal",
        "comprovar que o documento permanece rejeitado e não movimenta operação indevida",
        "corrigir o cenário e emitir nova tentativa sem reutilização insegura",
    ),
    "CANCELAMENTO": (
        "cancelar documento autorizado dentro do prazo aplicável",
        "consultar o evento e confrontar protocolo e situação final",
        "repetir a solicitação e comprovar idempotência ou rejeição controlada",
    ),
    "INUTILIZACAO": (
        "inutilizar faixa realmente disponível e aprovada para o teste",
        "confrontar ano, modelo, série, faixa, justificativa e protocolo",
        "repetir a faixa e comprovar resposta controlada sem novo efeito",
    ),
    "EVENTOS": (
        "registrar CC-e válida em NF-e autorizada e consultar seu protocolo",
        "registrar manifestação permitida em DF-e da filial destinatária",
        "executar rejeições controladas de sequência, prazo ou justificativa",
    ),
    "DFE": (
        "consultar a distribuição a partir do NSU controlado da filial",
        "comprovar paginação, deduplicação, eventos e avanço atômico do cursor",
        "respeitar intervalo de consumo e retomar sem perda nem duplicidade",
    ),
}

CRITERIOS = {
    "AUTORIZACAO": "chave, protocolo e XML processado convergem e a repetição não duplica",
    "CONSULTA": "situação, chave, protocolos e XML convergem com o autorizador",
    "REJEICAO": "código e motivo são preservados e nenhuma autorização indevida é registrada",
    "CANCELAMENTO": "evento autorizado, protocolo preservado e documento final cancelado",
    "INUTILIZACAO": "faixa e protocolo autorizados coincidem com o pedido aprovado",
    "EVENTOS": "cada evento mantém tipo, sequência, protocolo, XML e vínculo com o documento",
    "DFE": "cursor, NSU, documentos e eventos são íntegros, deduplicados e isolados por filial",
}


def construir_roteiros_homologacao(raiz_projeto):
    matriz = construir_matriz_qualificacao_canais(raiz_projeto)
    roteiros = []
    for item in matriz["resultados"]:
        lacuna_interna = item["estado"] != ESTADO_COMPATIVEL_OFFLINE
        evidencias_locais_ok = bool(item["achado_confirmado"])
        bloqueios = list(item["dependencias_externas"])
        if lacuna_interna:
            bloqueios.insert(0, item.get("motivo") or "Operação não implementada no canal.")
        if not evidencias_locais_ok:
            bloqueios.insert(0, "Evidências locais da implementação estão incompletas.")
        roteiros.append({
            "codigo": item["codigo"],
            "canal": item["canal"],
            "operacao": item["operacao"],
            "estado_pre_homologacao": (
                "BLOQUEADO_LACUNA_INTERNA" if lacuna_interna else "AGUARDA_DEPENDENCIAS_EXTERNAS"
            ),
            "cenarios_obrigatorios": CENARIOS[item["operacao"]],
            "evidencias_obrigatorias": EVIDENCIAS_COMUNS,
            "criterio_aprovacao": CRITERIOS[item["operacao"]],
            "bloqueios": tuple(bloqueios),
            "evidencias_locais_confirmadas": evidencias_locais_ok,
            "executavel_agora": False,
            "rede_permitida": False,
            "producao_permitida": False,
            "aprovado": False,
        })

    return {
        "contrato": CONTRATO_ROTEIROS_HOMOLOGACAO,
        "matriz_origem": matriz["contrato"],
        "roteiros": roteiros,
        "total": len(roteiros),
        "aguardam_dependencias_externas": sum(
            item["estado_pre_homologacao"] == "AGUARDA_DEPENDENCIAS_EXTERNAS"
            for item in roteiros
        ),
        "bloqueados_por_lacuna_interna": sum(
            item["estado_pre_homologacao"] == "BLOQUEADO_LACUNA_INTERNA"
            for item in roteiros
        ),
        "rede_executada": False,
        "segredos_incluidos": False,
        "homologacao_real_executada": False,
        "producao_liberada": False,
        "proximo_passo": "OBTER_DADOS_REAIS_E_EXECUTAR_UM_CANAL_POR_VEZ",
    }
