"""Estrategia pura de normalizacao do CNPJ alfa, ainda sem consumidores operacionais."""

import re

from .evidencia_cnpj_alfanumerico import (
    CONTRATO_EVIDENCIA_CNPJ_ALFANUMERICO,
    validar_evidencia_cnpj_alfanumerico,
)


CONTRATO_ESTRATEGIA_NORMALIZACAO_CNPJ = "alphanumeric_cnpj_canonicalization_strategy_v1"
CONTRATO_VALIDACAO_ESTRATEGIA_NORMALIZACAO_CNPJ = (
    "alphanumeric_cnpj_canonicalization_strategy_validation_v1"
)

PADRAO_CNPJ_CANONICO = re.compile(r"^[A-Z0-9]{12}[0-9]{2}$")
PADRAO_CNPJ_SEM_MASCARA = re.compile(r"^[A-Za-z0-9]{12}[0-9]{2}$")
PADRAO_CNPJ_COM_MASCARA = re.compile(
    r"^[A-Za-z0-9]{2}\.[A-Za-z0-9]{3}\.[A-Za-z0-9]{3}/[A-Za-z0-9]{4}-[0-9]{2}$"
)
PADRAO_BASE_CHAVE = re.compile(r"^[0-9]{6}[A-Z0-9]{12}[0-9]{25}$")
PADRAO_CHAVE = re.compile(r"^[0-9]{6}[A-Z0-9]{12}[0-9]{26}$")

CONSUMIDORES = (
    ("CADASTRO_EMPRESA_FILIAL", "CADASTRO", "apps/empresas/models.py;apps/empresas/forms.py", "UNICIDADE_E_GRAVACAO_TEXTUAL"),
    ("CONSULTA_CADASTRAL", "CADASTRO", "apps/empresas/views.py", "VALIDADOR_BUSCA_LOCAL_E_PROVEDOR"),
    ("DETECCAO_MATRIZ", "CADASTRO", "apps/empresas/views.py", "COMPARACAO_EMPRESA_FILIAL"),
    ("MASCARA_WEB", "INTERFACE", "static/js/app.js", "ENTRADA_E_LOOKUP_SOMENTE_DIGITOS"),
    ("CLIENTE_FORNECEDOR", "CADASTRO", "apps/clientes/forms.py;apps/fornecedores/forms.py", "MASCARA_COMPARTILHADA_CPF_CNPJ"),
    ("CREDENCIAL_SINCRONIZACAO", "IDENTIDADE", "apps/empresas/credenciais_sincronizacao.py", "CHAVE_DE_TOKEN_POR_CNPJ"),
    ("EVENTO_SINCRONIZACAO_ENTRADA", "IDENTIDADE", "apps/empresas/views.py", "BUSCA_EXATA_DO_CNPJ_RECEBIDO"),
    ("OBJETOS_SINCRONIZADOS", "IDENTIDADE", "apps/empresas/services_eventos_entrada.py", "BUSCA_EXATA_DE_FILIAL"),
    ("LICENCA_LOCAL", "LICENCIAMENTO", "apps/licenciamento/services.py;apps/licenciamento/views.py", "VINCULO_ASSINADO_ENTRE_PAYLOAD_E_INSTALACAO"),
    ("PAGADOR_LICENCIAMENTO", "LICENCIAMENTO", "apps/licenciamento/services.py", "CPF_CNPJ_ENVIADO_AO_PROVEDOR"),
    ("DOCUMENTO_CONSUMIDOR", "VENDAS", "apps/vendas/services.py", "SEPARACAO_CPF_CNPJ_E_FLUXO_MODELO_55"),
    ("IMPORTACAO_XML_COMPRA", "COMPRAS_DFE", "apps/compras/services_xml.py", "EXTRACAO_E_LOCALIZACAO_POR_CNPJ"),
    ("CONTRATO_ADAPTADOR_DFE", "COMPRAS_DFE", "apps/fiscal/dfe_adapters.py", "NORMALIZACAO_DE_CHAVE_DISTRIBUIDA"),
    ("ARMAZENAMENTO_DFE", "COMPRAS_DFE", "apps/fiscal/services_dfe.py", "CNPJ_DESTINATARIO_CHAVE_E_UNICIDADE"),
    ("ADAPTADOR_FOCUS_DFE", "CANAIS", "apps/fiscal/focus_dfe_adapter.py", "CONSULTA_XML_CNPJ_E_CHAVE"),
    ("ADAPTADOR_FOCUS_FISCAL", "CANAIS", "apps/fiscal/focus_sefaz_adapter.py", "RETORNO_DE_CHAVE"),
    ("ADAPTADOR_SEFAZ_DIRETA", "CANAIS", "apps/fiscal/sefaz_direta/adapter.py;apps/fiscal/sefaz_direta/dfe.py", "CONSULTA_EVENTOS_CNPJ_E_CHAVE"),
    ("GERADORES_FISCAIS", "FISCAL", "apps/fiscal/services.py", "CNPJ_EMITENTE_FORMACAO_E_DV_DA_CHAVE"),
    ("VALIDACAO_XML_ASSINADO", "FISCAL", "apps/fiscal/validacoes.py;apps/fiscal/adapters.py", "LEI_DE_FORMACAO_E_RETORNO_DA_CHAVE"),
    ("QR_CODE_NFCE", "FISCAL", "apps/fiscal/qrcode_nfce.py", "CHAVE_NO_QR_CODE"),
    ("DEVOLUCAO_FORNECEDOR", "DEVOLUCAO", "apps/fiscal/devolucao_fornecedor.py;apps/fiscal/extracao_contrato_devolucao.py;apps/fiscal/referencias_item_devolucao.py", "CONFRONTO_DE_PARTES_E_REFERENCIAS"),
    ("TRANSPORTE_DEVOLUCAO", "DEVOLUCAO", "apps/fiscal/transporte_devolucao.py", "CAMPO_MISTO_CPF_CNPJ"),
    ("DANFE_CODIGO_BARRAS", "DANFE", "NAO_LOCALIZADO_NO_GERADOR_ATUAL", "CODE_128_HIBRIDO_A_IMPLEMENTAR"),
)

FASES = (
    (1, "NORMALIZADOR_PURO_ISOLADO", "CONCLUIDA_SEM_ACOPLAMENTO"),
    (2, "AUDITORIA_SOMENTE_LEITURA", "CONCLUIDA_SEM_ACEITE_PRODUCAO"),
    (3, "LEITURA_DUPLA_CONTROLADA", "CONCLUIDA_ISOLADA_SEM_CONSUMIDORES"),
    (4, "ESCRITA_CANONICA_POR_FRONTEIRA", "CONCLUIDA_ISOLADA_SEM_CONSUMIDORES"),
    (5, "CHAVE_XML_QRCODE_E_DANFE", "PENDENTE"),
    (6, "HOMOLOGACAO_SEPARADA_DOS_CANAIS", "PENDENTE"),
)


def canonicalizar_cnpj(valor):
    """Aceita somente o formato puro ou a mascara oficial e devolve 14 caracteres."""
    if not isinstance(valor, str):
        raise ValueError("CNPJ deve ser texto.")
    texto = valor.strip()
    if not texto:
        return ""
    if PADRAO_CNPJ_SEM_MASCARA.fullmatch(texto):
        canonico = texto.upper()
    elif PADRAO_CNPJ_COM_MASCARA.fullmatch(texto):
        canonico = texto.translate(str.maketrans("", "", "./-")).upper()
    else:
        raise ValueError("CNPJ deve usar 14 caracteres ou a mascara oficial, sem simbolos extras.")
    if not PADRAO_CNPJ_CANONICO.fullmatch(canonico):
        raise ValueError("As 12 primeiras posicoes aceitam A-Z/0-9 e as duas ultimas somente digitos.")
    return canonico


def _valor_ascii_menos_48(caractere):
    return ord(caractere) - 48


def _digito_modulo_11(caracteres):
    peso = 2
    soma = 0
    for caractere in reversed(caracteres):
        soma += _valor_ascii_menos_48(caractere) * peso
        peso = 2 if peso == 9 else peso + 1
    resto = soma % 11
    return "0" if resto in (0, 1) else str(11 - resto)


def calcular_dv_cnpj(base):
    if not isinstance(base, str) or not re.fullmatch(r"[A-Z0-9]{12}", base):
        raise ValueError("A base do CNPJ deve conter 12 caracteres canonicos.")
    primeiro = _digito_modulo_11(base)
    return primeiro + _digito_modulo_11(base + primeiro)


def validar_dv_cnpj(valor):
    try:
        canonico = canonicalizar_cnpj(valor)
    except ValueError:
        return False
    return bool(canonico) and canonico[-2:] == calcular_dv_cnpj(canonico[:12])


def calcular_dv_chave_acesso(base):
    if not isinstance(base, str):
        raise ValueError("A base da chave deve ser texto.")
    canonica = base.strip().upper()
    if not PADRAO_BASE_CHAVE.fullmatch(canonica):
        raise ValueError("A base da chave deve conter 43 caracteres na estrutura oficial.")
    return _digito_modulo_11(canonica)


def validar_chave_acesso(valor):
    if not isinstance(valor, str):
        return False
    chave = valor.strip().upper()
    return bool(PADRAO_CHAVE.fullmatch(chave)) and chave[-1] == calcular_dv_chave_acesso(chave[:-1])


def analisar_identidades_cnpj(registros):
    """Agrupa identidades equivalentes sem consultar nem modificar o banco."""
    grupos = {}
    invalidos = []
    vazios = []
    for registro in registros:
        origem = str(registro.get("origem") or "")
        identificador = str(registro.get("identificador") or "")
        valor = registro.get("cnpj")
        referencia = {"origem": origem, "identificador": identificador, "valor": valor}
        try:
            canonico = canonicalizar_cnpj(valor)
        except ValueError as exc:
            invalidos.append({**referencia, "erro": str(exc)})
            continue
        if not canonico:
            vazios.append(referencia)
            continue
        grupos.setdefault(canonico, []).append(referencia)
    colisoes = [
        {"cnpj_canonico": canonico, "registros": itens}
        for canonico, itens in sorted(grupos.items())
        if len(itens) > 1
    ]
    return {
        "contrato": "alphanumeric_cnpj_identity_audit_preview_v1",
        "colisoes": colisoes,
        "invalidos": invalidos,
        "vazios": vazios,
        "altera_dados": False,
    }


def construir_estrategia_normalizacao_cnpj(evidencia):
    conteudo_evidencia = evidencia.get("conteudo", {}) if isinstance(evidencia, dict) else {}
    if not validar_evidencia_cnpj_alfanumerico(conteudo_evidencia)["estrutura_valida"]:
        raise ValueError("A evidencia normativa deve estar integra antes da estrategia.")
    if conteudo_evidencia.get("contrato") != CONTRATO_EVIDENCIA_CNPJ_ALFANUMERICO:
        raise ValueError("Contrato de evidencia normativa nao suportado.")

    conteudo = {
        "contrato": CONTRATO_ESTRATEGIA_NORMALIZACAO_CNPJ,
        "evidencia_contrato": CONTRATO_EVIDENCIA_CNPJ_ALFANUMERICO,
        "representacao": {
            "armazenamento": "A_Z_0_9_14_CARACTERES_SEM_PONTUACAO",
            "apresentacao": "AA.AAA.AAA/AAAA-DD",
            "caixa": "MAIUSCULAS",
            "remove_somente": [".", "/", "-"],
            "trim_externo": True,
            "preserva_zeros_esquerda": True,
            "rejeita_simbolos_desconhecidos": True,
            "valida_dv_separadamente": True,
        },
        "compatibilidade": {
            "cnpj_numerico_mantem_mesmo_canonico": True,
            "formato_mascarado_e_puro_equivalentes": True,
            "minusculas_convertidas_para_maiusculas": True,
            "comparacao_por_canonico": True,
            "gravacao_imediata_em_dados_existentes": False,
            "fallback_para_normalizador_antigo": False,
            "colisao_bloqueia_escrita": True,
            "valor_invalido_nao_e_corrigido_silenciosamente": True,
        },
        "consumidores": [
            {
                "codigo": codigo,
                "area": area,
                "arquivos": arquivos,
                "risco": risco,
                "alteracao_liberada": False,
            }
            for codigo, area, arquivos, risco in CONSUMIDORES
        ],
        "fases": [
            {"ordem": ordem, "codigo": codigo, "estado": estado, "execucao_operacional_liberada": False}
            for ordem, codigo, estado in FASES
        ],
        "conclusao": {
            "estrategia_definida": True,
            "normalizador_puro_testavel": True,
            "portao_escrita_puro_definido": True,
            "consumidor_operacional_alterado": False,
            "auditoria_dados_reais_pendente": True,
            "migracao_de_largura_necessaria": False,
            "migracao_de_conteudo_liberada": False,
        },
        "politica": {
            "consultar_dados_reais": False,
            "alterar_modelos": False,
            "criar_migracao": False,
            "normalizar_dados": False,
            "alterar_consumidores": False,
            "alterar_credenciais": False,
            "alterar_ambiente": False,
            "ativar_focus": False,
            "ativar_sefaz_direta": False,
            "emitir": False,
        },
        "proximo_passo": "ESPECIFICAR_ADAPTADOR_SOMBRA_DE_ESCRITA_SEM_PERSISTENCIA",
    }
    return {"conteudo": conteudo, "validacao": validar_estrategia_normalizacao_cnpj(conteudo)}


def validar_estrategia_normalizacao_cnpj(conteudo):
    erros = []

    def erro(caminho, codigo):
        erros.append({"caminho": caminho, "codigo": codigo})

    if not isinstance(conteudo, dict):
        conteudo = {}
        erro("$", "OBJETO_OBRIGATORIO")
    if set(conteudo) != {
        "contrato", "evidencia_contrato", "representacao", "compatibilidade",
        "consumidores", "fases", "conclusao", "politica", "proximo_passo",
    }:
        erro("$", "CAMPOS_INVALIDOS")
    if conteudo.get("contrato") != CONTRATO_ESTRATEGIA_NORMALIZACAO_CNPJ:
        erro("contrato", "CONTRATO_INVALIDO")
    if conteudo.get("evidencia_contrato") != CONTRATO_EVIDENCIA_CNPJ_ALFANUMERICO:
        erro("evidencia_contrato", "EVIDENCIA_INVALIDA")
    representacao_esperada = {
        "armazenamento": "A_Z_0_9_14_CARACTERES_SEM_PONTUACAO",
        "apresentacao": "AA.AAA.AAA/AAAA-DD",
        "caixa": "MAIUSCULAS",
        "remove_somente": [".", "/", "-"],
        "trim_externo": True,
        "preserva_zeros_esquerda": True,
        "rejeita_simbolos_desconhecidos": True,
        "valida_dv_separadamente": True,
    }
    if conteudo.get("representacao") != representacao_esperada:
        erro("representacao", "REPRESENTACAO_DIVERGENTE")
    compatibilidade_esperada = {
        "cnpj_numerico_mantem_mesmo_canonico": True,
        "formato_mascarado_e_puro_equivalentes": True,
        "minusculas_convertidas_para_maiusculas": True,
        "comparacao_por_canonico": True,
        "gravacao_imediata_em_dados_existentes": False,
        "fallback_para_normalizador_antigo": False,
        "colisao_bloqueia_escrita": True,
        "valor_invalido_nao_e_corrigido_silenciosamente": True,
    }
    if conteudo.get("compatibilidade") != compatibilidade_esperada:
        erro("compatibilidade", "COMPATIBILIDADE_DIVERGENTE")
    consumidores_esperados = [
        {"codigo": codigo, "area": area, "arquivos": arquivos, "risco": risco, "alteracao_liberada": False}
        for codigo, area, arquivos, risco in CONSUMIDORES
    ]
    if conteudo.get("consumidores") != consumidores_esperados:
        erro("consumidores", "CONSUMIDORES_DIVERGENTES_OU_LIBERADOS")
    fases_esperadas = [
        {"ordem": ordem, "codigo": codigo, "estado": estado, "execucao_operacional_liberada": False}
        for ordem, codigo, estado in FASES
    ]
    if conteudo.get("fases") != fases_esperadas:
        erro("fases", "FASES_DIVERGENTES_OU_LIBERADAS")
    if conteudo.get("conclusao") != {
        "estrategia_definida": True,
        "normalizador_puro_testavel": True,
        "portao_escrita_puro_definido": True,
        "consumidor_operacional_alterado": False,
        "auditoria_dados_reais_pendente": True,
        "migracao_de_largura_necessaria": False,
        "migracao_de_conteudo_liberada": False,
    }:
        erro("conclusao", "CONCLUSAO_DIVERGENTE")
    politica = conteudo.get("politica")
    if not isinstance(politica, dict) or set(politica) != {
        "consultar_dados_reais", "alterar_modelos", "criar_migracao", "normalizar_dados",
        "alterar_consumidores", "alterar_credenciais", "alterar_ambiente", "ativar_focus",
        "ativar_sefaz_direta", "emitir",
    } or any(valor is not False for valor in politica.values()):
        erro("politica", "POLITICA_INVALIDA")
    if conteudo.get("proximo_passo") != "ESPECIFICAR_ADAPTADOR_SOMBRA_DE_ESCRITA_SEM_PERSISTENCIA":
        erro("proximo_passo", "PROXIMO_PASSO_INVALIDO")

    return {
        "contrato": CONTRATO_VALIDACAO_ESTRATEGIA_NORMALIZACAO_CNPJ,
        "estrutura_valida": not erros,
        "quantidade_consumidores": len(conteudo.get("consumidores", [])) if isinstance(conteudo.get("consumidores"), list) else 0,
        "quantidade_fases": len(conteudo.get("fases", [])) if isinstance(conteudo.get("fases"), list) else 0,
        "erros": erros,
        "permite_migracao": False,
        "permite_alterar_consumidores": False,
        "permite_focus": False,
        "permite_sefaz_direta": False,
        "permite_emissao": False,
    }
