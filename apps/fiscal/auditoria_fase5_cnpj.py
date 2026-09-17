"""Auditoria estática da Fase 5 do CNPJ alfanumérico, sem alterar consumidores."""

from pathlib import Path


CONTRATO_AUDITORIA_FASE5_CNPJ = "alphanumeric_cnpj_phase5_static_audit_v6"


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
            "cnpj_emitente = normalizar_cnpj_emitente(venda.filial.cnpj or empresa.cnpj)",
            '_texto(emit, "CNPJ", cnpj_emitente)',
        ),
        "estado": "COMPATIVEL_OFFLINE",
        "ordem_correcao": 2,
        "motivo": "A NFC-e usa o mesmo CNPJ canônico na chave e na tag emit/CNPJ.",
    },
    {
        "codigo": "XML_NFE_CNPJ_EMITENTE",
        "escopo": "FASE_5",
        "componente": "XML",
        "arquivo": "apps/fiscal/services.py",
        "evidencias": (
            "cnpj_emitente = normalizar_cnpj_emitente(pedido.filial.cnpj or empresa.cnpj)",
            '_texto(emit, "CNPJ", cnpj_emitente)',
        ),
        "estado": "COMPATIVEL_OFFLINE",
        "ordem_correcao": 2,
        "motivo": "A NF-e usa o mesmo CNPJ canônico na chave e na tag emit/CNPJ.",
    },
    {
        "codigo": "XML_IDENTIFICADOR_INF_NFE",
        "escopo": "FASE_5",
        "componente": "XML",
        "arquivo": "apps/fiscal/services.py",
        "evidencias": ('{"versao": "4.00", "Id": f"NFe{chave_acesso}"}',),
        "estado": "COMPATIVEL_OFFLINE",
        "ordem_correcao": 2,
        "motivo": "O identificador recebe a chave central já validada e preserva suas letras.",
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
            "chave_normalizada = normalizar_chave_acesso(chave_recebida)",
            'if status == "AUTORIZADO" and not chave_normalizada:',
        ),
        "estado": "COMPATIVEL_OFFLINE",
        "ordem_correcao": 3,
        "motivo": "Autorizações e consultas usam a validação central e preservam letras.",
    },
    {
        "codigo": "FLUXOS_POS_GERACAO",
        "escopo": "FASE_5",
        "componente": "SERVICOS",
        "arquivo": "apps/fiscal/services.py",
        "evidencias": (
            "if not normalizar_chave_acesso(documento.chave_acesso):",
            "Informe uma chave de acesso fiscal válida com 44 caracteres.",
        ),
        "estado": "COMPATIVEL_OFFLINE",
        "ordem_correcao": 3,
        "motivo": "Simulação, cancelamento e consulta usam a validação central da chave.",
    },
    {
        "codigo": "QR_CODE_NFCE",
        "escopo": "FASE_5",
        "componente": "QR_CODE",
        "arquivo": "apps/fiscal/qrcode_nfce.py",
        "evidencias": (
            "normalizar_chave_acesso(documento.chave_acesso or",
            "if not chave:",
        ),
        "estado": "COMPATIVEL_OFFLINE",
        "ordem_correcao": 4,
        "motivo": "O QR Code reutiliza a chave central válida sem descartar letras.",
    },
    {
        "codigo": "DANFE_CHAVE_TEXTO",
        "escopo": "FASE_5",
        "componente": "DANFE",
        "arquivo": "templates/fiscal/danfe_nfce.html",
        "evidencias": ("{{ documento.chave_acesso }}",),
        "estado": "COMPATIVEL_OFFLINE",
        "ordem_correcao": 5,
        "motivo": "O DANFE preserva a chave central validada em sua apresentação textual.",
    },
    {
        "codigo": "DANFE_CODIGO_BARRAS_HIBRIDO",
        "escopo": "FASE_5",
        "componente": "DANFE",
        "arquivo": "apps/fiscal/barcode_chave.py",
        "evidencias": (
            'CONTRATO_BARCODE_CHAVE_FISCAL = "fiscal_access_key_code128_ca_v1"',
            'codigos.extend(self._new_charset("A"))',
        ),
        "estado": "COMPATIVEL_OFFLINE",
        "ordem_correcao": 5,
        "motivo": "O DANFE usa gerador Code 128 híbrido restrito aos conjuntos C e A.",
    },
    {
        "codigo": "CNPJ_EMITENTE_DV",
        "escopo": "FASE_5",
        "componente": "CHAVE_ACESSO",
        "arquivo": "apps/fiscal/chave_acesso.py",
        "evidencias": (
            "validar_dv_cnpj(cnpj)",
            "CNPJ do emitente possui dígitos verificadores inválidos.",
        ),
        "estado": "COMPATIVEL_OFFLINE",
        "ordem_correcao": 5,
        "motivo": "A fronteira fiscal recusa emitente com DV de CNPJ inválido antes de formar chave ou XML.",
    },
    {
        "codigo": "NFE_DESTINATARIO_CNPJ",
        "escopo": "FASE_5",
        "componente": "XML",
        "arquivo": "apps/fiscal/services.py",
        "evidencias": (
            "normalizar_documento_cliente(",
            'return "CNPJ", documento',
        ),
        "estado": "COMPATIVEL_OFFLINE",
        "ordem_correcao": 5,
        "motivo": "O destinatário da NF-e preserva CNPJ alfanumérico canônico e exige DV válido.",
    },
    {
        "codigo": "MARKETPLACE_DOCUMENTO_DESTINATARIO",
        "escopo": "FASE_5",
        "componente": "MARKETPLACE",
        "arquivo": "apps/marketplace/models.py",
        "evidencias": (
            "normalizar_documento_cliente(",
            "self.documento_cliente_tipo = tipo",
        ),
        "estado": "COMPATIVEL_OFFLINE",
        "ordem_correcao": 5,
        "motivo": "O snapshot Cliente-Pedido respeita o tipo explícito e só infere uma identidade válida.",
    },
    {
        "codigo": "CONTINGENCIA_NFCE_CHAVE",
        "escopo": "FASE_5",
        "componente": "CONTINGENCIA",
        "arquivo": "apps/fiscal/services.py",
        "evidencias": (
            'chave = normalizar_chave_acesso(getattr(documento, "chave_acesso", ""))',
            'chave[34] == "9"',
        ),
        "estado": "COMPATIVEL_OFFLINE",
        "ordem_correcao": 5,
        "motivo": "A detecção de tpEmis 9 usa a chave central válida sem remover letras.",
    },
    {
        "codigo": "PDV_DESKTOP_CHAVE_TEXTO",
        "escopo": "FASE_5",
        "componente": "PDV_DESKTOP",
        "arquivo": "desktop_pdv/devices/printing.py",
        "evidencias": (
            "def _normalizar_chave_acesso_payload",
            "chave = str(chave or \"\").strip().upper()",
        ),
        "estado": "COMPATIVEL_OFFLINE",
        "ordem_correcao": 5,
        "motivo": "O Desktop preserva os 44 caracteres alfanuméricos recebidos do servidor fiscal validado.",
    },
    {
        "codigo": "PDV_DESKTOP_CODE128",
        "escopo": "FASE_5",
        "componente": "PDV_DESKTOP",
        "arquivo": "desktop_pdv/devices/printing.py",
        "evidencias": (
            "def montar_danfe_nfce_escpos",
            "qrcode = montar_qrcode_escpos",
        ),
        "estado": "AUSENTE",
        "ordem_correcao": 5,
        "motivo": "O caminho RAW possui texto e QR Code, mas não há base genérica de Code 128 homologada para as impressoras suportadas.",
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
            "COMPATIBILIZAR_IDENTIDADE_FORA_DO_FISCAL",
            "HOMOLOGAR_FOCUS_E_SEFAZ_DIRETA_SEPARADAMENTE",
        ],
        "proximo_passo": "COMPATIBILIZAR_IDENTIDADE_FORA_DO_FISCAL",
    }
