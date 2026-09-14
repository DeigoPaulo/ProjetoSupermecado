"""Preparacao pura da escrita canonica de CNPJ, sem persistencia."""

import hashlib

from .estrategia_normalizacao_cnpj import canonicalizar_cnpj, validar_dv_cnpj


CONTRATO_PORTAO_ESCRITA_CANONICA_CNPJ = "alphanumeric_cnpj_canonical_write_gate_v1"
FRONTEIRAS_ESCRITA = frozenset({"EMPRESA", "FILIAL", "CLIENTE_PJ", "FORNECEDOR_PJ"})
FRONTEIRAS_COM_ESCOPO_EMPRESA = frozenset({"FILIAL", "CLIENTE_PJ", "FORNECEDOR_PJ"})
OPERACOES_ESCRITA = frozenset({"CRIACAO", "ATUALIZACAO"})


def _impressao(valor):
    return hashlib.sha256(("escrita-cnpj:" + valor).encode("utf-8")).hexdigest()[:16]


def _resposta(status, fronteira, operacao, *, valor_canonico="", valor_atual_canonico=""):
    return {
        "contrato": CONTRATO_PORTAO_ESCRITA_CANONICA_CNPJ,
        "status": status,
        "fronteira": fronteira,
        "operacao": operacao,
        "proposta": {
            "valor_canonico": valor_canonico,
            "impressao_digital": _impressao(valor_canonico) if valor_canonico else "",
            "requer_consulta_colisao": bool(valor_canonico),
            "requer_verificacao_titularidade": bool(valor_canonico),
        },
        "atual": {
            "impressao_digital": (
                _impressao(valor_atual_canonico) if valor_atual_canonico else ""
            ),
            "valor_completo_exposto": False,
        },
        "decisao": {
            "estrutura_valida": status in {
                "CANONICO_PREPARADO", "SEM_ALTERACAO_CANONICA",
                "TROCA_IDENTIDADE_REQUER_CONTROLES_EXTERNOS",
            },
            "mudanca_identidade": status == "TROCA_IDENTIDADE_REQUER_CONTROLES_EXTERNOS",
            "pode_persistir": False,
            "pode_corrigir_legado_automaticamente": False,
        },
        "seguranca": {
            "funcao_pura_isolada": True,
            "consulta_banco": False,
            "altera_dados": False,
            "consumidor_operacional_alterado": False,
            "libera_credencial": False,
            "libera_licenca": False,
            "libera_certificado": False,
            "libera_homologacao": False,
            "libera_producao": False,
            "libera_focus": False,
            "libera_sefaz_direta": False,
            "libera_emissao": False,
        },
    }


def preparar_escrita_canonica_cnpj(
    valor,
    *,
    fronteira,
    operacao,
    empresa_id=None,
    valor_atual=None,
):
    """Classifica uma proposta sem gravar, consultar ou autorizar persistencia."""
    fronteira_normalizada = str(fronteira or "").strip().upper()
    operacao_normalizada = str(operacao or "").strip().upper()
    if fronteira_normalizada not in FRONTEIRAS_ESCRITA:
        return _resposta("FRONTEIRA_INVALIDA", fronteira_normalizada, operacao_normalizada)
    if operacao_normalizada not in OPERACOES_ESCRITA:
        return _resposta("OPERACAO_INVALIDA", fronteira_normalizada, operacao_normalizada)
    if fronteira_normalizada in FRONTEIRAS_COM_ESCOPO_EMPRESA and not str(
        empresa_id or ""
    ):
        return _resposta(
            "ESCOPO_EMPRESA_OBRIGATORIO", fronteira_normalizada, operacao_normalizada
        )

    try:
        canonico = canonicalizar_cnpj(valor)
    except ValueError:
        return _resposta("PROPOSTA_INVALIDA", fronteira_normalizada, operacao_normalizada)
    if not canonico or not validar_dv_cnpj(canonico):
        return _resposta("PROPOSTA_INVALIDA", fronteira_normalizada, operacao_normalizada)

    if operacao_normalizada == "CRIACAO":
        return _resposta(
            "CANONICO_PREPARADO", fronteira_normalizada, operacao_normalizada,
            valor_canonico=canonico,
        )

    if valor_atual is None:
        return _resposta(
            "VALOR_ATUAL_OBRIGATORIO", fronteira_normalizada, operacao_normalizada,
            valor_canonico=canonico,
        )
    try:
        atual_canonico = canonicalizar_cnpj(valor_atual)
    except ValueError:
        return _resposta(
            "LEGADO_INVALIDO_REQUER_REVISAO", fronteira_normalizada, operacao_normalizada,
            valor_canonico=canonico,
        )
    if not atual_canonico or not validar_dv_cnpj(atual_canonico):
        return _resposta(
            "LEGADO_INVALIDO_REQUER_REVISAO", fronteira_normalizada, operacao_normalizada,
            valor_canonico=canonico,
        )
    if atual_canonico == canonico:
        return _resposta(
            "SEM_ALTERACAO_CANONICA", fronteira_normalizada, operacao_normalizada,
            valor_canonico=canonico, valor_atual_canonico=atual_canonico,
        )
    return _resposta(
        "TROCA_IDENTIDADE_REQUER_CONTROLES_EXTERNOS",
        fronteira_normalizada,
        operacao_normalizada,
        valor_canonico=canonico,
        valor_atual_canonico=atual_canonico,
    )


def descrever_portao_escrita_canonica_cnpj():
    return {
        "contrato": CONTRATO_PORTAO_ESCRITA_CANONICA_CNPJ,
        "fronteiras": sorted(FRONTEIRAS_ESCRITA),
        "fronteiras_com_escopo_empresa": sorted(FRONTEIRAS_COM_ESCOPO_EMPRESA),
        "operacoes": sorted(OPERACOES_ESCRITA),
        "regras": {
            "formato_e_dv_obrigatorios": True,
            "escopo_empresa_quando_aplicavel": True,
            "atualizacao_exige_valor_atual": True,
            "legado_invalido_nao_e_corrigido": True,
            "troca_identidade_exige_controles_externos": True,
            "colisao_e_titularidade_permanecem_externas": True,
        },
        "estado": {
            "fase_4_estrutural_concluida": True,
            "consumidor_operacional_alterado": False,
            "persistencia_liberada": False,
            "migracao_liberada": False,
            "focus_ativado": False,
            "sefaz_direta_ativada": False,
            "emissao_liberada": False,
        },
        "proximo_passo": "DEFINIR_INTEGRACAO_DA_FASE_4_APOS_REVISAR_DADOS",
    }
