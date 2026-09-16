"""Auditoria estática da Fase 5 do CNPJ alfanumérico, sem alterar consumidores."""

from pathlib import Path


CONTRATO_AUDITORIA_FASE5_CNPJ = "alphanumeric_cnpj_phase5_static_audit_v2"


PONTOS = (
    {
        "codigo": "CHAVE_FORMACAO_EMITENTE",
        "escopo": "FASE_5",
        "componente": "CHAVE_ACESSO",
        "arquivo": "apps/fiscal/chave_acesso.py",
        "evidencias": (
            "cnpj = canonicalizar_cnpj",
            "calcular_dv_chave_acesso(base)",
        ),
        "estado": "COMPATIVEL_OFFLINE",
        "ordem_correcao": 1,
        "motivo": "A formação central preserva o CNPJ canônico e valida a chave resultante.",
    },
    {
        "codigo": "CHAVE_DIGITO_VERIFICADOR",
        "escopo": "FASE_5",
        "componente": "CHAVE_ACESSO",
        "arquivo": "apps/fiscal/chave_acesso.py",
        "evidencias": ("calcular_dv_chave_acesso(base)",),
        "estado": "COMPATIVEL_OFFLINE",
        "ordem_correcao": 1,
        "motivo": "O DV central usa o algoritmo ASCII menos 48 já comprovado.",
    },
    {
        "codigo": "XML_NFCE_CNPJ_EMITENTE",
        "escopo": "FASE_5",
        "componente": "XML",
        "arquivo": "apps/fiscal/services.py",
        "evidencias": (
            "cnpj_emitente = _somente_digitos(venda.filial.cnpj or empresa.cnpj)",
            '_texto(emit, "CNPJ", cnpj_emitente)',
        ),
        "estado": "INCOMPATIVEL",
        "ordem_correcao": 2,
        "motivo": "O XML da NFC-e recebe um CNPJ previamente reduzido a dígitos.",
    },
    {
        "codigo": "XML_NFE_CNPJ_EMITENTE",
        "escopo": "FASE_5",
        "componente": "XML",
        "arquivo": "apps/fiscal/services.py",
        "evidencias": (
            "cnpj_emitente = _somente_digitos(pedido.filial.cnpj or empresa.cnpj)",
            '_texto(emit, "CNPJ", cnpj_emitente)',
        ),
        "estado": "INCOMPATIVEL",
        "ordem_correcao": 2,
        "motivo": "O XML da NF-e de pedido recebe um CNPJ previamente reduzido a dígitos.",
    },
    {
        "codigo": "XML_IDENTIFICADOR_INF_NFE",
        "escopo": "FASE_5",
        "componente": "XML",
        "arquivo": "apps/fiscal/services.py",
        "evidencias": ('{"versao": "4.00", "Id": f"NFe{chave_acesso}"}',),
        "estado": "COMPATIVEL_CONDICIONAL",
        "ordem_correcao": 2,
        "motivo": "O identificador preserva a chave recebida, mas depende da formação correta.",
    },
    {
        "codigo": "VALIDACAO_CHAVE_XML",
        "escopo": "FASE_5",
        "componente": "VALIDACAO",
        "arquivo": "apps/fiscal/validacoes.py",
        "evidencias": (
            "normalizar_chave_acesso(documento.chave_acesso or",
            "if not chave:",
        ),
        "estado": "COMPATIVEL_OFFLINE",
        "ordem_correcao": 3,
        "motivo": "A validação central aceita apenas a estrutura e o DV oficiais.",
    },
    {
        "codigo": "VALIDACAO_RETORNO_ADAPTADORES",
        "escopo": "FASE_5",
        "componente": "VALIDACAO",
        "arquivo": "apps/fiscal/adapters.py",
        "evidencias": (
            "not resultado.chave_acesso.isdigit()",
            "len(resultado.chave_acesso) != 44",
        ),
        "estado": "INCOMPATIVEL",
        "ordem_correcao": 3,
        "motivo": "Autorizações e consultas recusam retorno com letras na chave.",
    },
    {
        "codigo": "FLUXOS_POS_GERACAO",
        "escopo": "FASE_5",
        "componente": "SERVICOS",
        "arquivo": "apps/fiscal/services.py",
        "evidencias": (
            "not documento.chave_acesso.isdigit()",
            "Informe uma chave de acesso fiscal válida com 44 dígitos.",
        ),
        "estado": "INCOMPATIVEL",
        "ordem_correcao": 3,
        "motivo": "Simulação, cancelamento e consulta ainda impõem chave numérica.",
    },
    {
        "codigo": "QR_CODE_NFCE",
        "escopo": "FASE_5",
        "componente": "QR_CODE",
        "arquivo": "apps/fiscal/qrcode_nfce.py",
        "evidencias": (
            'if ch.isdigit()',
            "if len(chave) != 44",
        ),
        "estado": "INCOMPATIVEL",
        "ordem_correcao": 4,
        "motivo": "A chave usada no QR Code perde todas as letras.",
    },
    {
        "codigo": "DANFE_CHAVE_TEXTO",
        "escopo": "FASE_5",
        "componente": "DANFE",
        "arquivo": "templates/fiscal/danfe_nfce.html",
        "evidencias": ("{{ documento.chave_acesso }}",),
        "estado": "COMPATIVEL_CONDICIONAL",
        "ordem_correcao": 5,
        "motivo": "A apresentação textual preserva a chave, se ela chegar correta.",
    },
    {
        "codigo": "DANFE_CODIGO_BARRAS_HIBRIDO",
        "escopo": "FASE_5",
        "componente": "DANFE",
        "arquivo": "templates/fiscal/danfe_nfce.html",
        "evidencias": ("{{ documento.chave_acesso }}",),
        "estado": "AUSENTE",
        "ordem_correcao": 5,
        "motivo": "Não há gerador Code 128 híbrido C/A para a chave alfanumérica.",
    },
    {
        "codigo": "FOCUS_RETORNO_CHAVE",
        "escopo": "FASE_6",
        "componente": "CANAL_FOCUS",
        "arquivo": "apps/fiscal/focus_sefaz_adapter.py",
        "evidencias": ("if len(chave) != 44",),
        "estado": "COMPATIVEL_CONDICIONAL",
        "ordem_correcao": 6,
        "motivo": "O canal não exige somente dígitos nesse ponto, mas depende de homologação própria.",
    },
    {
        "codigo": "SEFAZ_DIRETA_CHAVE",
        "escopo": "FASE_6",
        "componente": "CANAL_SEFAZ_DIRETA",
        "arquivo": "apps/fiscal/sefaz_direta/adapter.py",
        "evidencias": (
            r're.sub(r"\D", "", valor or "")',
            "if len(chave) != 44",
        ),
        "estado": "INCOMPATIVEL",
        "ordem_correcao": 6,
        "motivo": "O adaptador direto reduz a chave a dígitos antes de enviá-la.",
    },
    {
        "codigo": "DISTRIBUICAO_DFE_CHAVE",
        "escopo": "FASE_6",
        "componente": "DFE",
        "arquivo": "apps/fiscal/dfe_adapters.py",
        "evidencias": (
            'if c.isdigit()',
            "if not xml and len(chave) != 44",
        ),
        "estado": "INCOMPATIVEL",
        "ordem_correcao": 6,
        "motivo": "A ingestão genérica de DF-e também descarta letras da chave.",
    },
)


def auditar_fase5_cnpj(raiz_projeto):
    raiz = Path(raiz_projeto)
    resultados = []
    for ponto in PONTOS:
        caminho = raiz / ponto["arquivo"]
        conteudo = caminho.read_text(encoding="utf-8") if caminho.is_file() else ""
        evidencias_ausentes = [
            evidencia for evidencia in ponto["evidencias"] if evidencia not in conteudo
        ]
        resultados.append({
            **ponto,
            "arquivo_presente": caminho.is_file(),
            "evidencias_ausentes": evidencias_ausentes,
            "achado_confirmado": caminho.is_file() and not evidencias_ausentes,
            "alteracao_executada": False,
        })

    fase5 = [item for item in resultados if item["escopo"] == "FASE_5"]
    fase6 = [item for item in resultados if item["escopo"] == "FASE_6"]
    return {
        "contrato": CONTRATO_AUDITORIA_FASE5_CNPJ,
        "resultados": resultados,
        "resumo": {
            "pontos_fase5": len(fase5),
            "incompativeis_fase5": sum(item["estado"] == "INCOMPATIVEL" for item in fase5),
            "ausentes_fase5": sum(item["estado"] == "AUSENTE" for item in fase5),
            "condicionais_fase5": sum(
                item["estado"] == "COMPATIVEL_CONDICIONAL" for item in fase5
            ),
            "compativeis_offline_fase5": sum(
                item["estado"] == "COMPATIVEL_OFFLINE" for item in fase5
            ),
            "pontos_fase6_inventariados": len(fase6),
            "todos_achados_confirmados": all(item["achado_confirmado"] for item in resultados),
            "altera_codigo_operacional": False,
        },
        "sequencia_recomendada": [
            "INTEGRAR_CNPJ_CANONICO_AOS_XML_NFCE_E_NFE",
            "SUBSTITUIR_VALIDACOES_NUMERICAS_NOS_FLUXOS_INTERNOS",
            "ADEQUAR_QR_CODE_NFCE",
            "IMPLEMENTAR_DANFE_CODE128_HIBRIDO",
            "HOMOLOGAR_FOCUS_E_SEFAZ_DIRETA_SEPARADAMENTE",
        ],
        "proximo_passo": "INTEGRAR_CNPJ_CANONICO_AOS_XML_NFCE_E_NFE_OFFLINE",
    }
