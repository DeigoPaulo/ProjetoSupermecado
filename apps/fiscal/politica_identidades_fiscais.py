"""Politica para impedir que identidades de exemplo virem identidade operacional."""


CONTRATO_POLITICA_IDENTIDADES_FISCAIS = "fiscal_identity_development_policy_v1"
AMBIENTES_NAO_OPERACIONAIS = frozenset({"development", "test"})
COMANDOS_DADOS_FICTICIOS = frozenset({"criar_dados_iniciais", "popular_demo"})
CATEGORIAS = frozenset({
    "EXEMPLO_NORMATIVO",
    "FICTICIO_DESENVOLVIMENTO",
    "REAL_PENDENTE",
    "REAL_VERIFICADA",
})


def normalizar_ambiente(ambiente):
    return str(ambiente or "").strip().lower()


def avaliar_comando_dados_ficticios(comando, ambiente):
    ambiente_normalizado = normalizar_ambiente(ambiente)
    conhecido = comando in COMANDOS_DADOS_FICTICIOS
    permitido = conhecido and ambiente_normalizado in AMBIENTES_NAO_OPERACIONAIS
    return {
        "contrato": CONTRATO_POLITICA_IDENTIDADES_FISCAIS,
        "comando": comando if conhecido else "DESCONHECIDO",
        "ambiente": ambiente_normalizado or "NAO_INFORMADO",
        "permitido": permitido,
        "motivo": (
            "DADOS_FICTICIOS_RESTRITOS_A_DESENVOLVIMENTO_TESTE"
            if conhecido else "COMANDO_FORA_DA_POLITICA"
        ),
        "seguranca": {
            "altera_dados_ao_avaliar": False,
            "libera_homologacao": False,
            "libera_producao": False,
            "libera_emissao": False,
        },
    }


def avaliar_uso_identidade_fiscal(
    categoria,
    *,
    ambiente,
    finalidade,
    titularidade_verificada=False,
    origem_documentada=False,
):
    ambiente_normalizado = normalizar_ambiente(ambiente)
    categoria_conhecida = categoria in CATEGORIAS
    finalidade_normalizada = str(finalidade or "").strip().upper()
    contexto_nao_operacional = ambiente_normalizado in AMBIENTES_NAO_OPERACIONAIS
    finalidade_segura = finalidade_normalizada in {
        "TESTE_UNITARIO", "TESTE_INTEGRACAO_LOCAL", "DEMONSTRACAO_LOCAL", "DOCUMENTACAO",
    }
    if categoria in {"EXEMPLO_NORMATIVO", "FICTICIO_DESENVOLVIMENTO"}:
        uso_permitido = contexto_nao_operacional and finalidade_segura
        motivo = "EXEMPLO_SEM_PROVA_DE_TITULARIDADE"
    elif categoria == "REAL_PENDENTE":
        uso_permitido = False
        motivo = "IDENTIDADE_REAL_AINDA_NAO_FORNECIDA_OU_VERIFICADA"
    elif categoria == "REAL_VERIFICADA":
        uso_permitido = bool(titularidade_verificada and origem_documentada)
        motivo = "REQUISITOS_CADASTRAIS_ATENDIDOS" if uso_permitido else "VERIFICACAO_INCOMPLETA"
    else:
        uso_permitido = False
        motivo = "CATEGORIA_DESCONHECIDA"
    return {
        "contrato": CONTRATO_POLITICA_IDENTIDADES_FISCAIS,
        "categoria": categoria if categoria_conhecida else "DESCONHECIDA",
        "ambiente": ambiente_normalizado or "NAO_INFORMADO",
        "finalidade": finalidade_normalizada or "NAO_INFORMADA",
        "uso_cadastral_permitido": uso_permitido,
        "motivo": motivo,
        "garantias": {
            "formato_valido_prova_titularidade": False,
            "exemplo_normativo_representa_empresa_do_cliente": False,
            "dado_ficticio_pode_receber_credencial": False,
            "dado_ficticio_pode_vincular_licenca": False,
            "dado_ficticio_pode_emitir": False,
            "politica_sozinha_libera_homologacao": False,
            "politica_sozinha_libera_producao": False,
        },
    }


def construir_politica_identidades_fiscais():
    return {
        "contrato": CONTRATO_POLITICA_IDENTIDADES_FISCAIS,
        "categorias": sorted(CATEGORIAS),
        "ambientes_dados_ficticios": sorted(AMBIENTES_NAO_OPERACIONAIS),
        "comandos_protegidos": sorted(COMANDOS_DADOS_FICTICIOS),
        "inventario_2026_09_14": {
            "arquivos_teste_com_exemplos": 48,
            "arquivos_execucao_com_exemplos": 3,
            "arquivos_documentacao_com_exemplos": 5,
            "arquivos_execucao_relevantes": [
                "apps/configuracoes/management/commands/criar_dados_iniciais.py",
                "apps/configuracoes/management/commands/popular_demo.py",
                "apps/empresas/services_lookup.py",
            ],
        },
        "estado": {
            "base_atual_alterada": False,
            "fixtures_existentes_reescritas": False,
            "cnpj_real_disponivel": False,
            "focus_ativado": False,
            "sefaz_direta_ativada": False,
            "emissao_liberada": False,
        },
        "proximo_passo": "DEFINIR_INTEGRACAO_DA_FASE_4_APOS_REVISAR_DADOS",
    }
