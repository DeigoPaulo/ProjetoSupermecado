"""Evidencia normativa do CNPJ alfanumerico, sem alterar o fluxo fiscal."""

import hashlib
import re
from pathlib import Path

from .plano_compatibilidade_emitente_xsd import (
    CONTRATO_PLANO_COMPATIBILIDADE_EMITENTE,
    validar_plano_compatibilidade_emitente_xsd,
)


CONTRATO_EVIDENCIA_CNPJ_ALFANUMERICO = "alphanumeric_cnpj_official_evidence_v1"
CONTRATO_VALIDACAO_EVIDENCIA_CNPJ_ALFANUMERICO = (
    "alphanumeric_cnpj_official_evidence_validation_v1"
)

FONTES = (
    {
        "codigo": "RFB_MANUAL_DV",
        "orgao": "RECEITA_FEDERAL_DO_BRASIL",
        "arquivo": "docs/evidencias/cnpj_alfanumerico_2026_09_14/manual_dv_cnpj_alfanumerico.pdf",
        "sha256": "7bb839f6c9beb968bd5bb67d31dd5db090d2333be55815759cfb293e639b4754",
        "url": "https://www.gov.br/receitafederal/pt-br/centrais-de-conteudo/publicacoes/documentos-tecnicos/cnpj/manual-dv-cnpj.pdf/@@download/file",
    },
    {
        "codigo": "RFB_PERGUNTAS_RESPOSTAS",
        "orgao": "RECEITA_FEDERAL_DO_BRASIL",
        "arquivo": "docs/evidencias/cnpj_alfanumerico_2026_09_14/perguntas_respostas_cnpj_alfanumerico.pdf",
        "sha256": "c59ab587536ca22f634373cd6a0603afc834f286d3f557e60ad488f4e6264835",
        "url": "https://www.gov.br/receitafederal/pt-br/centrais-de-conteudo/publicacoes/perguntas-e-respostas/cnpj/cnpj-alfanumerico.pdf",
    },
    {
        "codigo": "NT_CONJUNTA_DFE_2025_001_V1_00",
        "orgao": "ENCAT_DFE",
        "arquivo": "docs/evidencias/cnpj_alfanumerico_2026_09_14/nt_conjunta_dfe_2025_001_v1_00.pdf",
        "sha256": "671d546b24ad4682e267fc76a9eeca8f14ad15ead2be20721ee2aec5438cf964",
        "url": "https://www.nfe.fazenda.gov.br/Portal/exibirArquivo.aspx?conteudo=5ZkvIZt10mQ%3D",
    },
    {
        "codigo": "NT_NFE_2026_004_V1_01",
        "orgao": "PORTAL_NACIONAL_NFE",
        "arquivo": "docs/evidencias/cnpj_alfanumerico_2026_09_14/nt_nfe_2026_004_v1_01.pdf",
        "sha256": "5f24a25351e790692754b07bbefac42ac67e70167a62a7806395d880f56675be",
        "url": "https://www.nfe.fazenda.gov.br/Portal/exibirArquivo.aspx?conteudo=BTZQzgsO9Ws%3D",
    },
    {
        "codigo": "XSD_NFE_010F_V1_04",
        "orgao": "PORTAL_NACIONAL_NFE",
        "arquivo": "docs/evidencias/nfe_2026_09_10/schemas_010f.zip",
        "sha256": "b8589490a58a09a993a80e6ac4d7ed10f20892061ecfc56719337098d4b95998",
        "url": "https://www.nfe.fazenda.gov.br/portal/listaConteudo.aspx?tipoConteudo=BMPFMBoln3w%3D",
    },
)

REGRAS_CNPJ = {
    "representacao_canonica_recomendada": "14_CARACTERES_SEM_PONTUACAO_EM_MAIUSCULAS",
    "expressao_regular": r"[A-Z0-9]{12}[0-9]{2}",
    "base": "12_CARACTERES_ALFANUMERICOS",
    "digitos_verificadores": "2_DIGITOS_NUMERICOS",
    "valor_caractere": "ASCII_MENOS_48",
    "algoritmo": "MODULO_11_PESOS_2_A_9_DA_DIREITA_PARA_ESQUERDA",
    "formatos_coexistem": True,
    "cnpj_existente_permanece_valido": True,
    "zeros_a_esquerda_preservados": True,
    "sufixo_0001_identifica_matriz_permanentemente": False,
}

REGRAS_CHAVE = {
    "tamanho": 44,
    "expressao_regular": r"[0-9]{6}[A-Z0-9]{12}[0-9]{26}",
    "posicoes_cnpj": "7_A_20",
    "valor_caractere_para_dv": "ASCII_MENOS_48",
    "algoritmo_dv": "MODULO_11_SOBRE_AS_43_POSICOES_ANTERIORES",
    "codigo_barras": "CODE_128_HIBRIDO_C_E_A_QUANDO_HOUVER_LETRAS",
}

VIGENCIA = {
    "nfce_nfe_homologacao_limite": "2026-06-15",
    "nfce_nfe_producao": "2026-07-01",
    "rfb_inicio_novos_cnpj": "2026-07",
    "regra_depende_do_ambiente_e_data_emissao": True,
}

IMPACTOS = (
    ("CADASTRO", "ACEITAR_E_PRESERVAR_LETRAS_SEM_QUEBRAR_CNPJ_NUMERICO"),
    ("INTERFACE", "REMOVER_MASCARA_EXCLUSIVAMENTE_NUMERICA"),
    ("IDENTIDADE", "SUBSTITUIR_NORMALIZACAO_QUE_DESCARTA_LETRAS"),
    ("COMPRAS_DFE", "COMPARAR_CNPJ_E_CHAVES_ALFANUMERICAS"),
    ("FISCAL", "ATUALIZAR_FORMACAO_E_DV_DA_CHAVE_DE_44_CARACTERES"),
    ("DANFE", "SUPORTAR_CODE_128_HIBRIDO_C_E_A_QUANDO_HOUVER_LETRAS"),
    ("CANAIS", "HOMOLOGAR_FOCUS_E_SEFAZ_DIRETA_SEPARADAMENTE"),
)


def _sha256(arquivo):
    resumo = hashlib.sha256()
    with arquivo.open("rb") as entrada:
        for bloco in iter(lambda: entrada.read(1024 * 1024), b""):
            resumo.update(bloco)
    return resumo.hexdigest()


def construir_evidencia_cnpj_alfanumerico(plano, raiz_projeto):
    conteudo_plano = plano.get("conteudo", {}) if isinstance(plano, dict) else {}
    if not validar_plano_compatibilidade_emitente_xsd(conteudo_plano)["estrutura_valida"]:
        raise ValueError("O plano de compatibilidade deve estar integro antes da evidencia normativa.")
    if conteudo_plano.get("contrato") != CONTRATO_PLANO_COMPATIBILIDADE_EMITENTE:
        raise ValueError("Contrato do plano de compatibilidade nao suportado.")

    raiz = Path(raiz_projeto)
    fontes = []
    for fonte in FONTES:
        arquivo = raiz / fonte["arquivo"]
        if not arquivo.is_file() or _sha256(arquivo) != fonte["sha256"]:
            raise ValueError(f"Evidencia oficial ausente ou adulterada: {fonte['codigo']}.")
        fontes.append(dict(fonte))

    conteudo = {
        "contrato": CONTRATO_EVIDENCIA_CNPJ_ALFANUMERICO,
        "plano_contrato": CONTRATO_PLANO_COMPATIBILIDADE_EMITENTE,
        "data_corte": "2026-09-14",
        "fontes": fontes,
        "regras_cnpj": dict(REGRAS_CNPJ),
        "regras_chave_acesso": dict(REGRAS_CHAVE),
        "vigencia": dict(VIGENCIA),
        "impactos": [
            {"area": area, "adequacao": adequacao, "alteracao_liberada": False}
            for area, adequacao in IMPACTOS
        ],
        "conclusao": {
            "regra_normativa_confirmada": True,
            "etapa_normativa_concluida": True,
            "largura_atual_cnpj_suficiente": True,
            "compatibilidade_semantica_atual": False,
            "migracao_de_largura_necessaria": False,
            "mudancas_de_validacao_e_integracao_necessarias": True,
            "auditoria_dados_reais_pendente": True,
        },
        "politica": {
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
        "proximo_passo": "DEFINIR_NORMALIZACAO_CANONICA_E_RETROCOMPATIBILIDADE",
    }
    return {"conteudo": conteudo, "validacao": validar_evidencia_cnpj_alfanumerico(conteudo)}


def validar_evidencia_cnpj_alfanumerico(conteudo):
    erros = []

    def erro(caminho, codigo):
        erros.append({"caminho": caminho, "codigo": codigo})

    if not isinstance(conteudo, dict):
        conteudo = {}
        erro("$", "OBJETO_OBRIGATORIO")
    if set(conteudo) != {
        "contrato", "plano_contrato", "data_corte", "fontes", "regras_cnpj",
        "regras_chave_acesso", "vigencia", "impactos", "conclusao", "politica",
        "proximo_passo",
    }:
        erro("$", "CAMPOS_INVALIDOS")
    if conteudo.get("contrato") != CONTRATO_EVIDENCIA_CNPJ_ALFANUMERICO:
        erro("contrato", "CONTRATO_INVALIDO")
    if conteudo.get("plano_contrato") != CONTRATO_PLANO_COMPATIBILIDADE_EMITENTE:
        erro("plano_contrato", "PLANO_INVALIDO")
    if conteudo.get("data_corte") != "2026-09-14":
        erro("data_corte", "DATA_CORTE_INVALIDA")
    if conteudo.get("fontes") != [dict(fonte) for fonte in FONTES]:
        erro("fontes", "FONTES_DIVERGENTES")
    if conteudo.get("regras_cnpj") != REGRAS_CNPJ:
        erro("regras_cnpj", "REGRA_CNPJ_DIVERGENTE")
    if conteudo.get("regras_chave_acesso") != REGRAS_CHAVE:
        erro("regras_chave_acesso", "REGRA_CHAVE_DIVERGENTE")
    if conteudo.get("vigencia") != VIGENCIA:
        erro("vigencia", "VIGENCIA_DIVERGENTE")
    impactos_esperados = [
        {"area": area, "adequacao": adequacao, "alteracao_liberada": False}
        for area, adequacao in IMPACTOS
    ]
    if conteudo.get("impactos") != impactos_esperados:
        erro("impactos", "IMPACTOS_DIVERGENTES_OU_LIBERADOS")
    if conteudo.get("conclusao") != {
        "regra_normativa_confirmada": True,
        "etapa_normativa_concluida": True,
        "largura_atual_cnpj_suficiente": True,
        "compatibilidade_semantica_atual": False,
        "migracao_de_largura_necessaria": False,
        "mudancas_de_validacao_e_integracao_necessarias": True,
        "auditoria_dados_reais_pendente": True,
    }:
        erro("conclusao", "CONCLUSAO_DIVERGENTE")
    politica = conteudo.get("politica")
    if not isinstance(politica, dict) or set(politica) != {
        "alterar_modelos", "criar_migracao", "normalizar_dados", "alterar_geradores",
        "alterar_credenciais", "alterar_ambiente", "ativar_focus", "ativar_sefaz_direta",
        "emitir",
    } or any(valor is not False for valor in politica.values()):
        erro("politica", "POLITICA_INVALIDA")
    if conteudo.get("proximo_passo") != "DEFINIR_NORMALIZACAO_CANONICA_E_RETROCOMPATIBILIDADE":
        erro("proximo_passo", "PROXIMO_PASSO_INVALIDO")

    for caminho, padrao in (
        ("regras_cnpj.expressao_regular", REGRAS_CNPJ["expressao_regular"]),
        ("regras_chave_acesso.expressao_regular", REGRAS_CHAVE["expressao_regular"]),
    ):
        try:
            re.compile(rf"^(?:{padrao})$")
        except re.error:
            erro(caminho, "EXPRESSAO_REGULAR_INVALIDA")

    fontes = conteudo.get("fontes")
    impactos = conteudo.get("impactos")
    return {
        "contrato": CONTRATO_VALIDACAO_EVIDENCIA_CNPJ_ALFANUMERICO,
        "estrutura_valida": not erros,
        "quantidade_fontes": len(fontes) if isinstance(fontes, list) else 0,
        "quantidade_impactos": len(impactos) if isinstance(impactos, list) else 0,
        "erros": erros,
        "permite_migracao": False,
        "permite_alterar_geradores": False,
        "permite_focus": False,
        "permite_sefaz_direta": False,
        "permite_emissao": False,
    }
