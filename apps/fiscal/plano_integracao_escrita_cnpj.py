"""Classifica a prontidão da integração cadastral de CNPJ sem alterar dados."""


CONTRATO_PLANO_INTEGRACAO_ESCRITA_CNPJ = (
    "alphanumeric_cnpj_company_branch_integration_plan_v1"
)


def planejar_integracao_escrita_empresa_filial(resultado_auditoria):
    """Transforma a auditoria protegida em decisões agregadas e não operacionais."""
    if not isinstance(resultado_auditoria, dict):
        raise ValueError("AUDITORIA_OBRIGATORIA")
    if resultado_auditoria.get("contrato") != "alphanumeric_cnpj_readonly_audit_v1":
        raise ValueError("CONTRATO_AUDITORIA_NAO_SUPORTADO")

    resumo = resultado_auditoria.get("resumo") or {}
    cnpj_por_status = resumo.get("cnpj_por_status") or {}
    colisoes = resumo.get("colisoes_por_classificacao") or {}
    correcoes_manuais = {
        "dv_invalido": int(cnpj_por_status.get("DV_INVALIDO", 0)),
        "formato_invalido": int(cnpj_por_status.get("FORMATO_INVALIDO", 0)),
        "ausente_obrigatorio": int(cnpj_por_status.get("AUSENTE_OBRIGATORIO", 0)),
        "colisao_bloqueante": int(colisoes.get("BLOQUEANTE", 0)),
    }
    quantidade_correcoes_manuais = sum(correcoes_manuais.values())
    equivalencias_esperadas = int(colisoes.get("ESPERADA_EMPRESA_FILIAL", 0))
    papeis_distintos_para_revisao = int(colisoes.get("REVISAR_PAPEIS_DISTINTOS", 0))

    return {
        "contrato": CONTRATO_PLANO_INTEGRACAO_ESCRITA_CNPJ,
        "base": resultado_auditoria.get("base", ""),
        "dados_existentes": {
            "requerem_correcao_manual": correcoes_manuais,
            "quantidade_correcoes_manuais": quantidade_correcoes_manuais,
            "equivalencias_empresa_filial_esperadas": equivalencias_esperadas,
            "papeis_distintos_requerem_revisao": papeis_distintos_para_revisao,
            "correcao_automatica_permitida": False,
            "migracao_de_conteudo_liberada": False,
        },
        "validacao_local": {
            "liberada": True,
            "cenarios_obrigatorios": [
                "CRIACAO_COM_CNPJ_VALIDO_GRAVA_CANONICO",
                "CRIACAO_COM_DV_INVALIDO_E_REJEITADA",
                "ATUALIZACAO_EQUIVALENTE_MANTEM_IDENTIDADE",
                "COLISAO_CANONICA_E_REJEITADA_NO_ESCOPO_CORRETO",
                "LEGADO_INVALIDO_NAO_E_CORRIGIDO_SILENCIOSAMENTE",
                "TROCA_DE_IDENTIDADE_CONTINUA_BLOQUEADA",
            ],
            "fronteiras": ["EmpresaForm.clean_cnpj", "FilialForm.clean_cnpj"],
        },
        "integracao_operacional": {
            "persistencia_liberada": False,
            "constraints_liberadas": False,
            "consumidor_alterado": False,
            "motivos_bloqueio": [
                motivo
                for condicao, motivo in (
                    (
                        quantidade_correcoes_manuais > 0,
                        "DADOS_LEGADOS_REQUEREM_DECISAO_MANUAL",
                    ),
                    (
                        papeis_distintos_para_revisao > 0,
                        "IDENTIDADES_EM_PAPEIS_DISTINTOS_REQUEREM_REVISAO",
                    ),
                )
                if condicao
            ],
        },
        "seguranca": {
            "altera_dados": False,
            "expoe_identificadores": False,
            "consulta_credenciais": False,
            "libera_homologacao": False,
            "libera_producao": False,
            "libera_focus": False,
            "libera_sefaz_direta": False,
            "libera_emissao": False,
        },
        "proximo_passo": "VALIDAR_INTEGRACAO_LOCAL_NOS_FORMULARIOS_EMPRESA_FILIAL",
    }
