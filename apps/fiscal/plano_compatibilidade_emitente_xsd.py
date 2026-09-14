"""Plano fechado para compatibilizar o emitente com o XSD, sem executar mudanças."""

import re

from .especificacao_emit_devolucao import (
    CONTRATO_ESPECIFICACAO_EMIT,
    validar_especificacao_emit_devolucao,
)


CONTRATO_PLANO_COMPATIBILIDADE_EMITENTE = "issuer_xsd_compatibility_plan_v1"
CONTRATO_VALIDACAO_PLANO_COMPATIBILIDADE_EMITENTE = "issuer_xsd_compatibility_plan_validation_v1"


FRENTES = (
    {
        "codigo": "CNPJ_ALFANUMERICO",
        "estado_atual": "NORMALIZACAO_E_MASCARA_SOMENTE_DIGITOS",
        "alvo_xsd": "TCnpj_[0-9A-Z]{12}[0-9]{2}",
        "estrategia": "DEFINIR_REPRESENTACAO_CANONICA_RETROCOMPATIVEL",
        "dependencia": "REGRA_OFICIAL_CHAVE_ACESSO_E_IDENTIFICADORES_PENDENTE",
        "migracao_banco": "NAO_DEFINIDA",
    },
    {
        "codigo": "MINIMOS_TEXTUAIS",
        "estado_atual": "LIMITES_MAXIMOS_SEM_MINIMO_XSD",
        "alvo_xsd": "XNOME_XLGR_XBAIRRO_XMUN_MINIMO_2",
        "estrategia": "VALIDAR_NA_FRONTEIRA_FISCAL_SEM_TRUNCAR",
        "dependencia": "AUDITORIA_DADOS_REAIS_PENDENTE",
        "migracao_banco": "NAO_NECESSARIA_PARA_LARGURA",
    },
    {
        "codigo": "INSCRICAO_ESTADUAL",
        "estado_atual": "TEXTO_GENERICO_ATE_30",
        "alvo_xsd": "TIE_[0-9]{2,14}_OU_ISENTO_E_ELEMENTO_0_1",
        "estrategia": "VALIDAR_CONTEXTO_FISCAL_SEM_ESTREITAR_COLUNA",
        "dependencia": "REGRA_APLICABILIDADE_IE_PENDENTE",
        "migracao_banco": "NAO_NECESSARIA_PARA_LARGURA",
    },
    {
        "codigo": "DOMINIO_UF",
        "estado_atual": "MODELO_COM_CHOICES_COMPATIVEL_CONTRATO_FISCAL_GENERICO",
        "alvo_xsd": "TUFEMI_27_UFS",
        "estrategia": "REUTILIZAR_DOMINIO_UNICO_NA_FRONTEIRA_FISCAL",
        "dependencia": "VALIDADOR_COMPARTILHADO_PENDENTE",
        "migracao_banco": "NAO_NECESSARIA",
    },
    {
        "codigo": "ENDEREMIT_GERADORES_EXISTENTES",
        "estado_atual": "AUSENTE_NOS_GERADORES_NFCE_E_NFE_PEDIDO_ONLINE",
        "alvo_xsd": "ENDEREMIT_1_1_COM_OITO_CAMPOS_MAPEADOS",
        "estrategia": "IMPLEMENTAR_APOS_PORTAO_DE_DADOS_DO_EMITENTE",
        "dependencia": "DADOS_E_VALIDADORES_COMPATIVEIS_PENDENTES",
        "migracao_banco": "NAO_NECESSARIA_PARA_ESTRUTURA_XML",
    },
)


PONTOS_ACOPLAMENTO = (
    ("CADASTRO", "Empresa_Filial_e_ConfiguracaoFiscal", "VALIDACAO_E_NORMALIZACAO"),
    ("INTERFACE", "Mascaras_e_consulta_CNPJ_CEP", "ENTRADA_ALFANUMERICA_E_FALLBACK"),
    ("IDENTIDADE", "Licenciamento_sincronizacao_e_buscas", "CHAVE_CANONICA_SEM_COLISAO"),
    ("COMPRAS_DFE", "Importacao_XML_e_distribuicao_DFe", "COMPARACAO_DE_DOCUMENTOS"),
    ("FISCAL", "Chave_acesso_e_geradores_NFCE_NFE", "REGRA_OFICIAL_E_ENDEREMIT"),
    ("CANAIS", "Focus_e_SEFAZ_direta", "PARIDADE_E_HOMOLOGACAO_SEPARADAS"),
)


ETAPAS = (
    (1, "CONFIRMAR_REGRA_NORMATIVA_CNPJ_ALFANUMERICO"),
    (2, "DEFINIR_NORMALIZACAO_CANONICA_E_RETROCOMPATIBILIDADE"),
    (3, "AUDITAR_DADOS_REAIS_SOMENTE_LEITURA"),
    (4, "IMPLEMENTAR_VALIDADORES_COMPATIVEIS_E_TESTES"),
    (5, "INCLUIR_ENDEREMIT_NOS_GERADORES_OFFLINE"),
    (6, "HOMOLOGAR_FOCUS_E_SEFAZ_DIRETA_SEPARADAMENTE"),
)


def construir_plano_compatibilidade_emitente_xsd(especificacao_emit):
    conteudo_emit = especificacao_emit.get("conteudo", {}) if isinstance(especificacao_emit, dict) else {}
    if not validar_especificacao_emit_devolucao(conteudo_emit)["estrutura_valida"]:
        raise ValueError("A especificação de emit deve estar íntegra antes do plano de compatibilidade.")
    if conteudo_emit.get("contrato") != CONTRATO_ESPECIFICACAO_EMIT:
        raise ValueError("Contrato de especificação de emit não suportado.")

    conteudo = {
        "contrato": CONTRATO_PLANO_COMPATIBILIDADE_EMITENTE,
        "operacao_referencia": "DEVOLUCAO_COMPRA",
        "especificacao_emit_contrato": CONTRATO_ESPECIFICACAO_EMIT,
        "pacote_sha256": conteudo_emit["pacote_sha256"],
        "frentes": [{**item, "mudanca_liberada": False} for item in FRENTES],
        "pontos_acoplamento": [
            {"area": area, "componentes": componentes, "risco": risco,
             "alteracao_liberada": False}
            for area, componentes, risco in PONTOS_ACOPLAMENTO
        ],
        "etapas": [
            {"ordem": ordem, "codigo": codigo, "estado": "NAO_INICIADA",
             "execucao_liberada": False}
            for ordem, codigo in ETAPAS
        ],
        "portoes": {
            "regra_oficial_cnpj_confirmada": False,
            "estrategia_retrocompatibilidade_aprovada": False,
            "auditoria_dados_reais_concluida": False,
            "validadores_homologados": False,
            "enderemit_validado_offline": False,
            "aceite_fiscal_contabil": False,
            "homologacao_focus": False,
            "homologacao_sefaz_direta": False,
        },
        "politica": {
            "contem_dados_reais": False,
            "alterar_modelos": False,
            "criar_migracao": False,
            "normalizar_dados": False,
            "alterar_geradores": False,
            "alterar_credenciais": False,
            "alterar_ambiente": False,
            "ativar_focus": False,
            "ativar_sefaz_direta": False,
            "emitir": False,
        },
    }
    return {"conteudo": conteudo, "validacao": validar_plano_compatibilidade_emitente_xsd(conteudo)}


def validar_plano_compatibilidade_emitente_xsd(conteudo):
    erros = []

    def erro(caminho, codigo):
        erros.append({"caminho": caminho, "codigo": codigo})

    if not isinstance(conteudo, dict):
        conteudo = {}
        erro("$", "OBJETO_OBRIGATORIO")
    if set(conteudo) != {
        "contrato", "operacao_referencia", "especificacao_emit_contrato", "pacote_sha256",
        "frentes", "pontos_acoplamento", "etapas", "portoes", "politica",
    }:
        erro("$", "CAMPOS_INVALIDOS")
    if conteudo.get("contrato") != CONTRATO_PLANO_COMPATIBILIDADE_EMITENTE:
        erro("contrato", "CONTRATO_INVALIDO")
    if conteudo.get("operacao_referencia") != "DEVOLUCAO_COMPRA":
        erro("operacao_referencia", "OPERACAO_INVALIDA")
    if conteudo.get("especificacao_emit_contrato") != CONTRATO_ESPECIFICACAO_EMIT:
        erro("especificacao_emit_contrato", "ESPECIFICACAO_INVALIDA")
    pacote_sha256 = conteudo.get("pacote_sha256")
    if not isinstance(pacote_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", pacote_sha256):
        erro("pacote_sha256", "HASH_INVALIDO")

    frentes = conteudo.get("frentes")
    if not isinstance(frentes, list) or len(frentes) != len(FRENTES):
        erro("frentes", "FRENTES_INCOMPLETAS")
        frentes = []
    for indice, esperado in enumerate(FRENTES):
        item = frentes[indice] if indice < len(frentes) else {}
        if not isinstance(item, dict) or item != {**esperado, "mudanca_liberada": False}:
            erro(f"frentes.{indice}", "FRENTE_DIVERGENTE_OU_LIBERADA")

    pontos = conteudo.get("pontos_acoplamento")
    esperados_pontos = [
        {"area": area, "componentes": componentes, "risco": risco, "alteracao_liberada": False}
        for area, componentes, risco in PONTOS_ACOPLAMENTO
    ]
    if pontos != esperados_pontos:
        erro("pontos_acoplamento", "ACOPLAMENTO_DIVERGENTE_OU_LIBERADO")

    etapas = conteudo.get("etapas")
    esperadas_etapas = [
        {"ordem": ordem, "codigo": codigo, "estado": "NAO_INICIADA", "execucao_liberada": False}
        for ordem, codigo in ETAPAS
    ]
    if etapas != esperadas_etapas:
        erro("etapas", "ETAPAS_DIVERGENTES_OU_LIBERADAS")
    if conteudo.get("portoes") != {
        "regra_oficial_cnpj_confirmada": False,
        "estrategia_retrocompatibilidade_aprovada": False,
        "auditoria_dados_reais_concluida": False,
        "validadores_homologados": False,
        "enderemit_validado_offline": False,
        "aceite_fiscal_contabil": False,
        "homologacao_focus": False,
        "homologacao_sefaz_direta": False,
    }:
        erro("portoes", "PORTOES_LIBERADOS_OU_INVALIDOS")
    if conteudo.get("politica") != {
        "contem_dados_reais": False, "alterar_modelos": False, "criar_migracao": False,
        "normalizar_dados": False, "alterar_geradores": False, "alterar_credenciais": False,
        "alterar_ambiente": False, "ativar_focus": False, "ativar_sefaz_direta": False,
        "emitir": False,
    }:
        erro("politica", "POLITICA_INVALIDA")
    return {
        "contrato": CONTRATO_VALIDACAO_PLANO_COMPATIBILIDADE_EMITENTE,
        "estrutura_valida": not erros,
        "quantidade_frentes": len(frentes),
        "quantidade_pontos_acoplamento": len(pontos) if isinstance(pontos, list) else 0,
        "quantidade_etapas": len(etapas) if isinstance(etapas, list) else 0,
        "erros": erros,
        "permite_migracao": False,
        "permite_alterar_geradores": False,
        "permite_focus": False,
        "permite_sefaz_direta": False,
        "permite_emissao": False,
    }
