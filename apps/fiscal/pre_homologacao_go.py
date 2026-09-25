"""Diagnostico offline do XSD e das capacidades internas do piloto GO."""

import hashlib
import json
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path
from xml.etree import ElementTree as ET

from .auditoria_pacote_xsd import auditar_pacote_xsd
from .ibs_cbs.calculo import calcular_base_operacao_padrao, calcular_ibs_cbs_padrao
from .ibs_cbs.catalogo import METADADOS_CATALOGO, validar_classificacao
from .ibs_cbs.contrato import CONTRATO as CONTRATO_IBS_CBS, emissao_ibs_cbs_obrigatoria
from .ibs_cbs.validacao import validar_paridade_xml
from .ibs_cbs.xml import adicionar_grupo_item, adicionar_totais


CONTRATO = "fiscal_go_pre_homologation_matrix_v1"
CONTRATO_PRONTIDAO_INTERNA = "fiscal_go_internal_homologation_readiness_v1"

PRONTO_INTERNAMENTE = "PRONTO_INTERNAMENTE"
DEPENDE_DE_DADO_REAL = "DEPENDE_DE_DADO_REAL"
DEPENDE_DE_HOMOLOGACAO_EXTERNA = "DEPENDE_DE_HOMOLOGACAO_EXTERNA"
BLOQUEADO_LACUNA_INTERNA = "BLOQUEADO_LACUNA_INTERNA"
ESTADOS_PRONTIDAO_INTERNA = {
    PRONTO_INTERNAMENTE,
    DEPENDE_DE_DADO_REAL,
    DEPENDE_DE_HOMOLOGACAO_EXTERNA,
    BLOQUEADO_LACUNA_INTERNA,
}

SUPORTADO = "SUPORTADO"
BLOQUEADO = "BLOQUEADO"
DEPENDE_DE_HOMOLOGACAO = "DEPENDE_DE_HOMOLOGACAO"
DEPENDE_DE_PARAMETRIZACAO = "DEPENDE_DE_PARAMETRIZACAO"
NAO_IMPLEMENTADO = "NAO_IMPLEMENTADO"
STATUS_VALIDOS = {
    SUPORTADO,
    BLOQUEADO,
    DEPENDE_DE_HOMOLOGACAO,
    DEPENDE_DE_PARAMETRIZACAO,
    NAO_IMPLEMENTADO,
}

DIAGNOSTICO = "DIAGNOSTICO"
PREFLIGHT = "PREFLIGHT"
GERADOR = "GERADOR"
PRE_TRANSMISSAO = "PRE_TRANSMISSAO"
EXTERNO = "EXTERNO"
CONTROLES_VALIDOS = {
    DIAGNOSTICO,
    PREFLIGHT,
    GERADOR,
    PRE_TRANSMISSAO,
    EXTERNO,
}

# A matriz apenas descreve estes controles. Ela nao e chamada por nenhum deles.
CONTROLES_CAPACIDADE = {
    "modelo_65_nfce": (DIAGNOSTICO, PREFLIGHT, GERADOR),
    "modelo_55_nfe": (DIAGNOSTICO, PREFLIGHT, GERADOR),
    "crt_1_simples": (DIAGNOSTICO, PREFLIGHT, GERADOR),
    "crt_2_excesso": (DIAGNOSTICO, PREFLIGHT, GERADOR),
    "crt_3_normal": (DIAGNOSTICO, PREFLIGHT, GERADOR, PRE_TRANSMISSAO, EXTERNO),
    "crt_4_mei": (DIAGNOSTICO, PREFLIGHT, GERADOR),
    "icms_cst_suportados": (DIAGNOSTICO, PREFLIGHT, GERADOR),
    "icms_cst_desconhecido": (DIAGNOSTICO, PREFLIGHT, GERADOR),
    "icms_csosn_suportados": (DIAGNOSTICO, PREFLIGHT, GERADOR),
    "icms_csosn_desconhecido": (DIAGNOSTICO, PREFLIGHT, GERADOR),
    "pis": (DIAGNOSTICO, PREFLIGHT, GERADOR),
    "cofins": (DIAGNOSTICO, PREFLIGHT, GERADOR),
    "ipi": (DIAGNOSTICO, PREFLIGHT, GERADOR),
    "cbenef": (DIAGNOSTICO, PREFLIGHT, GERADOR),
    "ibs_cbs": (DIAGNOSTICO, PREFLIGHT, EXTERNO),
    "ibs_cbs_crt3_operacao_padrao": (
        DIAGNOSTICO, PREFLIGHT, GERADOR, PRE_TRANSMISSAO, EXTERNO,
    ),
    "pagamento_dinheiro": (DIAGNOSTICO, PREFLIGHT, GERADOR),
    "pagamento_credito": (DIAGNOSTICO, PREFLIGHT, GERADOR, PRE_TRANSMISSAO, EXTERNO),
    "pagamento_debito": (DIAGNOSTICO, PREFLIGHT, GERADOR, PRE_TRANSMISSAO, EXTERNO),
    "pagamento_pix": (DIAGNOSTICO, PREFLIGHT, GERADOR, PRE_TRANSMISSAO, EXTERNO),
    "pagamento_vale_alimentacao": (DIAGNOSTICO, PREFLIGHT, GERADOR, PRE_TRANSMISSAO, EXTERNO),
    "pagamento_vale_refeicao": (DIAGNOSTICO, PREFLIGHT, GERADOR, PRE_TRANSMISSAO, EXTERNO),
    "pagamento_dividido": (DIAGNOSTICO, PREFLIGHT, GERADOR, PRE_TRANSMISSAO, EXTERNO),
    "destinatario_nao_identificado": (DIAGNOSTICO, PREFLIGHT, GERADOR),
    "destinatario_cpf": (DIAGNOSTICO, PREFLIGHT, GERADOR),
    "destinatario_cnpj": (DIAGNOSTICO, PREFLIGHT, GERADOR, EXTERNO),
    "endereco_emitente": (DIAGNOSTICO, PREFLIGHT, GERADOR, PRE_TRANSMISSAO),
    "qrcode_nfce": (DIAGNOSTICO, GERADOR, PRE_TRANSMISSAO, EXTERNO),
    "contingencia_nfce": (DIAGNOSTICO, PREFLIGHT, GERADOR, EXTERNO),
    "sefaz_direta_go": (DIAGNOSTICO, PRE_TRANSMISSAO, EXTERNO),
    "focus": (DIAGNOSTICO, PRE_TRANSMISSAO, EXTERNO),
    "xsd_operacional": (DIAGNOSTICO, PRE_TRANSMISSAO),
    "venda_interestadual": (DIAGNOSTICO, PREFLIGHT, GERADOR),
    "destinatario_contribuinte": (DIAGNOSTICO, PREFLIGHT),
    "frete": (DIAGNOSTICO, PREFLIGHT),
    "finalidade_nao_suportada": (DIAGNOSTICO, PREFLIGHT, GERADOR),
    "producao": (DIAGNOSTICO, PRE_TRANSMISSAO),
}

BLOQUEIO_OPERACIONAL = {
    "crt_3_normal": "HOMOLOGACAO_EXTERNA_PENDENTE",
    "icms_cst_desconhecido": "COMPROVADO",
    "icms_csosn_desconhecido": "COMPROVADO",
    "ibs_cbs": "COMPROVADO_FORA_DO_RECORTE_CATALOGADO",
    "ibs_cbs_crt3_operacao_padrao": "HOMOLOGACAO_EXTERNA_PENDENTE",
    "xsd_operacional": "COMPROVADO_NA_PRE_TRANSMISSAO",
    "venda_interestadual": "COMPROVADO",
    "destinatario_contribuinte": "COMPROVADO",
    "frete": "COMPROVADO",
    "finalidade_nao_suportada": "COMPROVADO",
    "producao": "COMPROVADO_NOS_ADAPTADORES",
}

PACOTE_XSD = {
    "versao": "PL_010f_v1.04",
    "publicado_em": "2026-08-31",
    "fonte_oficial": (
        "https://www.nfe.fazenda.gov.br/portal/"
        "exibirArquivo.aspx?conteudo=8ITFuBLltXs%3D"
    ),
    "listagem_oficial": (
        "https://www.nfe.fazenda.gov.br/portal/"
        "listaConteudo.aspx?tipoConteudo=BMPFMBoln3w%3D"
    ),
    "arquivo_relativo": "docs/evidencias/nfe_2026_09_10/schemas_010f.zip",
    "sha256": "b8589490a58a09a993a80e6ac4d7ed10f20892061ecfc56719337098d4b95998",
    "arquivo_raiz": "PL_010f_v1.04/nfe_v4.00.xsd",
    "arquivo_raiz_sha256": (
        "adce3646c13ceb54922ec3142fc1dc45bd4fb839ac35ad583e86c733c07d27df"
    ),
}

NFE_NS = "http://www.portalfiscal.inf.br/nfe"


EVIDENCIAS_PRONTIDAO = {
    "xml_assinado_xsd_55": (
        "apps/fiscal/tests.py",
        ("test_nfe_go_ibs_cbs_confronta_xsd_010f_oficial", "assinar_xml_documento"),
    ),
    "xml_assinado_xsd_65": (
        "apps/fiscal/tests.py",
        ("test_nfce_go_ibs_cbs_confronta_xsd_010f_oficial", "assinar_xml_documento"),
    ),
    "pre_transmissao_focus": (
        "apps/fiscal/tests.py",
        ("test_pre_transmissao_focus_bloqueia_calculo_ibs_cbs_adulterado",),
    ),
    "pre_transmissao_sefaz_direta": (
        "apps/fiscal/tests.py",
        ("test_pre_transmissao_sefaz_direta_bloqueia_calculo_ibs_cbs_adulterado",),
    ),
    "endereco_emitente": (
        "apps/fiscal/services.py",
        ("pendencias_endereco_emitente_nfce", "enderEmit"),
    ),
    "series_fiscais": ("apps/fiscal/services.py", ("SerieFiscal", "proximo_numero")),
    "chave_acesso": ("apps/fiscal/chave_acesso.py", ("construir_chave_acesso",)),
    "qrcode_nfce": ("apps/fiscal/qrcode_nfce.py", ("gerar_url_qrcode_nfce",)),
    "pagamentos_eletronicos": (
        "apps/fiscal/services.py",
        ("validar_vinculos_pagamentos_xml", "_adicionar_integracao_pagamento_nfce"),
    ),
    "contingencia": ("apps/fiscal/services.py", ("ativar_contingencia_offline",)),
    "bloqueio_producao_focus": (
        "apps/fiscal/focus_sefaz_adapter.py",
        ("FOCUS_NFE_FISCAL_ALLOW_PRODUCTION", "Produção Focus NFe bloqueada"),
    ),
    "bloqueio_producao_sefaz": (
        "apps/fiscal/sefaz_direta/adapter.py",
        ("SEFAZ_DIRETA_ALLOW_PRODUCTION", "Produção da SEFAZ direta permanece bloqueada"),
    ),
}


def _evidencia_local(base, codigo):
    arquivo, marcadores = EVIDENCIAS_PRONTIDAO[codigo]
    caminho = base / arquivo
    conteudo = caminho.read_text(encoding="utf-8") if caminho.is_file() else ""
    ausentes = [marcador for marcador in marcadores if marcador not in conteudo]
    return {
        "codigo": codigo,
        "arquivo": arquivo,
        "marcadores": list(marcadores),
        "estado": PRONTO_INTERNAMENTE if not ausentes else BLOQUEADO_LACUNA_INTERNA,
        "ausentes": ausentes,
    }


def _validar_nucleo_ibs_cbs_offline(modelo):
    classificacao = validar_classificacao("000", "000001", modelo)
    base = calcular_base_operacao_padrao(
        valor_produtos=Decimal("82.70"),
        desconto=Decimal("2.70"),
        valor_pis=Decimal("1.32"),
        valor_cofins=Decimal("6.08"),
        valor_icms=Decimal("14.40"),
        valor_fcp=Decimal("0.00"),
    )
    calculo = calcular_ibs_cbs_padrao(
        valor_operacao=base,
        cst=classificacao.cst,
        cclass_trib=classificacao.cclass_trib,
        modelo=modelo,
    )
    inf_nfe = ET.Element(f"{{{NFE_NS}}}infNFe")
    det = ET.SubElement(inf_nfe, f"{{{NFE_NS}}}det", {"nItem": "1"})
    prod = ET.SubElement(det, f"{{{NFE_NS}}}prod")
    ET.SubElement(prod, f"{{{NFE_NS}}}vProd").text = "82.70"
    ET.SubElement(prod, f"{{{NFE_NS}}}vDesc").text = "2.70"
    imposto = ET.SubElement(det, f"{{{NFE_NS}}}imposto")
    icms = ET.SubElement(imposto, f"{{{NFE_NS}}}ICMS")
    icms00 = ET.SubElement(icms, f"{{{NFE_NS}}}ICMS00")
    ET.SubElement(icms00, f"{{{NFE_NS}}}vICMS").text = "14.40"
    pis = ET.SubElement(imposto, f"{{{NFE_NS}}}PIS")
    pis_aliq = ET.SubElement(pis, f"{{{NFE_NS}}}PISAliq")
    ET.SubElement(pis_aliq, f"{{{NFE_NS}}}vPIS").text = "1.32"
    cofins = ET.SubElement(imposto, f"{{{NFE_NS}}}COFINS")
    cofins_aliq = ET.SubElement(cofins, f"{{{NFE_NS}}}COFINSAliq")
    ET.SubElement(cofins_aliq, f"{{{NFE_NS}}}vCOFINS").text = "6.08"
    adicionar_grupo_item(imposto, calculo, namespace=NFE_NS)
    total = ET.SubElement(inf_nfe, f"{{{NFE_NS}}}total")
    adicionar_totais(total, [calculo], namespace=NFE_NS)
    validar_paridade_xml(
        inf_nfe,
        namespace=NFE_NS,
        modelo=modelo,
        data_emissao=date(2026, 9, 25),
    )
    return {
        "modelo": modelo,
        "base": str(calculo.base),
        "cst": calculo.cst,
        "cclass_trib": calculo.cclass_trib,
        "decimal": True,
        "validacao_matematica": True,
        "cardinalidade_exclusividade": True,
    }


def _item_gate(capacidade, canal, estado, bloqueio, evidencias=()):
    return {
        "capacidade": capacidade,
        "canal": canal,
        "estado": estado,
        "bloqueio": bloqueio,
        "evidencias": list(evidencias),
    }


def diagnostico_prontidao_interna_piloto_go(base_dir):
    """Consolida prontidao offline; nao le segredos, nao acessa rede e nao homologa."""
    base = Path(base_dir).resolve()
    arquivo_xsd = base / PACOTE_XSD["arquivo_relativo"]
    auditoria_xsd = auditar_pacote_xsd(
        arquivo=arquivo_xsd,
        sha256_esperado=PACOTE_XSD["sha256"],
        versao=PACOTE_XSD["versao"],
    )
    nucleos = [_validar_nucleo_ibs_cbs_offline(modelo) for modelo in ("55", "65")]
    evidencias = {
        codigo: _evidencia_local(base, codigo) for codigo in EVIDENCIAS_PRONTIDAO
    }
    gaps = [item for item in evidencias.values() if item["estado"] == BLOQUEADO_LACUNA_INTERNA]
    evidencias_comuns = {
        "xml_assinado_xsd_55",
        "xml_assinado_xsd_65",
        "endereco_emitente",
        "series_fiscais",
        "chave_acesso",
        "qrcode_nfce",
        "pagamentos_eletronicos",
        "contingencia",
    }
    evidencias_por_canal = {
        "SEFAZ_DIRETA_GO": evidencias_comuns
        | {"pre_transmissao_sefaz_direta", "bloqueio_producao_sefaz"},
        "FOCUS": evidencias_comuns
        | {"pre_transmissao_focus", "bloqueio_producao_focus"},
    }

    def estado_evidencias_canal(canal):
        return (
            PRONTO_INTERNAMENTE
            if all(
                evidencias[codigo]["estado"] == PRONTO_INTERNAMENTE
                for codigo in evidencias_por_canal[canal]
            )
            else BLOQUEADO_LACUNA_INTERNA
        )

    contrato_ok = CONTRATO_IBS_CBS == "fiscal_ibs_cbs_go_crt3_standard_v1"
    catalogo_ok = bool(
        METADADOS_CATALOGO["versao_it"] == "IT 2025.002 v1.60"
        and METADADOS_CATALOGO["data_oficial"] == "2026-06-23"
        and METADADOS_CATALOGO["url_oficial"].startswith("https://")
        and METADADOS_CATALOGO["artefato_oficial_sha256"] is None
    )
    vigencia_ok = emissao_ibs_cbs_obrigatoria(
        uf="GO",
        crt="3",
        modelo="65",
        ambiente="HOMOLOGACAO",
        data_emissao=date(2026, 9, 25),
    )
    nucleo_ok = contrato_ok and catalogo_ok and vigencia_ok and len(nucleos) == 2
    estado_nucleo = PRONTO_INTERNAMENTE if nucleo_ok else BLOQUEADO_LACUNA_INTERNA

    capacidades = []
    for canal in ("SEFAZ_DIRETA_GO", "FOCUS"):
        evidencias_canal = (
            "xml_assinado_xsd_55",
            "xml_assinado_xsd_65",
            (
                "pre_transmissao_sefaz_direta"
                if canal == "SEFAZ_DIRETA_GO"
                else "pre_transmissao_focus"
            ),
        )
        for capacidade in ("NF-e 55", "NFC-e 65", CONTRATO_IBS_CBS):
            estado = (
                PRONTO_INTERNAMENTE
                if estado_nucleo == PRONTO_INTERNAMENTE
                and estado_evidencias_canal(canal) == PRONTO_INTERNAMENTE
                else BLOQUEADO_LACUNA_INTERNA
            )
            capacidades.append(
                _item_gate(
                    capacidade,
                    canal,
                    estado,
                    (
                        "DADOS_REAIS_E_HOMOLOGACAO_EXTERNA_PENDENTES"
                        if estado == PRONTO_INTERNAMENTE
                        else "EVIDENCIA_INTERNA_AUSENTE"
                    ),
                    evidencias_canal,
                )
            )

    dados_reais = (
        ("CNPJ da filial GO", True, "CNPJ_REAL"),
        ("Inscricao estadual da filial GO", True, "IE_REAL"),
        ("Certificado A1 e senha", True, "A1_E_SENHA_REAIS"),
        ("CSC e idCSC", False, "CONDICIONAL_APENAS_PARA_COMPATIBILIDADE_QRCODE_V2"),
        ("Token Focus NFe de homologacao", True, "CREDENCIAL_FOCUS_REAL"),
        ("Credenciamento e endpoints externos vigentes", True, "VALIDACAO_EXTERNA_POR_CANAL"),
        ("Autorizacao humana para iniciar homologacao", True, "ACEITE_FISCAL_E_OPERACIONAL"),
    )
    dia_zero = [
        {
            "item": item,
            "obrigatorio_para_o_cenario": obrigatorio,
            "estado": DEPENDE_DE_DADO_REAL,
            "bloqueio": bloqueio,
        }
        for item, obrigatorio, bloqueio in dados_reais
    ]

    canais = {
        "SEFAZ_DIRETA_GO": {
            "papel": "ALVO_PRINCIPAL",
            "estado_interno": estado_evidencias_canal("SEFAZ_DIRETA_GO"),
            "estado_para_iniciar": DEPENDE_DE_DADO_REAL,
            "estado_para_concluir": DEPENDE_DE_HOMOLOGACAO_EXTERNA,
            "fallback_automatico": False,
        },
        "FOCUS": {
            "papel": "CANAL_SECUNDARIO",
            "estado_interno": estado_evidencias_canal("FOCUS"),
            "estado_para_iniciar": DEPENDE_DE_DADO_REAL,
            "estado_para_concluir": DEPENDE_DE_HOMOLOGACAO_EXTERNA,
            "fallback_automatico": False,
            "lacuna_eventos_fora_do_gate_emissivo": (
                "CC-e e manifestacao nao expostas pelo adaptador Focus"
            ),
        },
    }
    resultado = {
        "contrato": CONTRATO_PRONTIDAO_INTERNA,
        "recorte": CONTRATO_IBS_CBS,
        "estados_validos": sorted(ESTADOS_PRONTIDAO_INTERNA),
        "estado_geral_interno": (
            PRONTO_INTERNAMENTE
            if estado_nucleo == PRONTO_INTERNAMENTE
            and estado_evidencias_canal("SEFAZ_DIRETA_GO") == PRONTO_INTERNAMENTE
            else BLOQUEADO_LACUNA_INTERNA
        ),
        "nucleo_ibs_cbs": {
            "estado": estado_nucleo,
            "contrato_carregavel": contrato_ok,
            "catalogo_rastreavel": catalogo_ok,
            "vigencia_2026": vigencia_ok,
            "modelos": nucleos,
        },
        "xsd_offline": {
            "estado": PRONTO_INTERNAMENTE,
            "pacote_integro": auditoria_xsd["pacote"]["crc_integro"],
            "sha256": auditoria_xsd["pacote"]["sha256"],
            "dependencias_validas": bool(auditoria_xsd["schema"]["dependencias"]),
            "compilacao": auditoria_xsd["schema"]["compilacao_offline"],
            "xml_55_valido_e_assinado": (
                evidencias["xml_assinado_xsd_55"]["estado"] == PRONTO_INTERNAMENTE
            ),
            "xml_65_valido_e_assinado": (
                evidencias["xml_assinado_xsd_65"]["estado"] == PRONTO_INTERNAMENTE
            ),
            "instalado": False,
            "promovido": False,
        },
        "evidencias_internas": list(evidencias.values()),
        "gaps_internos": gaps,
        "gaps_internos_por_canal": {
            canal: [
                codigo
                for codigo in sorted(codigos)
                if evidencias[codigo]["estado"] == BLOQUEADO_LACUNA_INTERNA
            ]
            for canal, codigos in evidencias_por_canal.items()
        },
        "canais": canais,
        "matriz": capacidades,
        "dia_zero_homologacao": {
            "fixture": "FILIAL_FICTICIA_GO_SEM_IDENTIDADE_OU_CREDENCIAL_REAL",
            "estado_interno": estado_nucleo,
            "dependencias": dia_zero,
            "ausencia_dados_reais_e_lacuna_interna": False,
        },
        "politica": {
            "acessou_rede": False,
            "leu_credenciais_reais": False,
            "usou_identidade_real": False,
            "transmitiu": False,
            "homologacao_real": False,
            "producao_liberada": False,
            "fallback_automatico": False,
        },
    }
    resultado["manifesto_sha256"] = _sha256_json(resultado)
    return resultado


def _capacidade(codigo, area, cenario, status, escopo, evidencias):
    return {
        "codigo": codigo,
        "area": area,
        "cenario": cenario,
        "status": status,
        "escopo": escopo,
        "evidencias": tuple(evidencias),
    }


CAPACIDADES = (
    _capacidade(
        "modelo_65_nfce", "documento", "NFC-e modelo 65", DEPENDE_DE_HOMOLOGACAO,
        "Gerador e preflight cobrem venda interna a consumidor final; autorizacao real continua pendente.",
        ("services.gerar_xml_nfce", "cenarios_tributarios.avaliar_cenario_fiscal_go"),
    ),
    _capacidade(
        "modelo_55_nfe", "documento", "NF-e modelo 55", DEPENDE_DE_HOMOLOGACAO,
        "Gerador atual cobre pedido online interno dentro do recorte restrito do piloto.",
        ("services.gerar_xml_nfe_pedido_online", "marketplace.tests"),
    ),
    _capacidade(
        "crt_1_simples", "tributacao", "CRT 1 - Simples Nacional", DEPENDE_DE_PARAMETRIZACAO,
        "Exige CSOSN suportado e cadastro fiscal completo por produto e operacao.",
        ("services.CSOSN_ICMS_SUPORTADOS",),
    ),
    _capacidade(
        "crt_2_excesso", "tributacao", "CRT 2 - excesso de sublimite", DEPENDE_DE_PARAMETRIZACAO,
        "Usa a matriz de CST do regime normal e decisao explicita de cBenef em GO.",
        ("services.CST_ICMS_SUPORTADOS", "diagnostico_cbenef"),
    ),
    _capacidade(
        "crt_3_normal", "tributacao", "CRT 3 - regime normal", DEPENDE_DE_HOMOLOGACAO,
        "O recorte comum GO 55/65 serializa e reconcilia IBSCBS; classificacoes especiais falham fechado.",
        ("ibs_cbs.contrato", "services.gerar_xml_nfce", "services.gerar_xml_nfe_pedido_online"),
    ),
    _capacidade(
        "crt_4_mei", "tributacao", "CRT 4 - MEI", DEPENDE_DE_PARAMETRIZACAO,
        "Compartilha o ramo CSOSN; enquadramento real depende de revisao fiscal.",
        ("services._usa_csosn",),
    ),
    _capacidade(
        "icms_cst_suportados", "tributacao", "CST ICMS 00, 20, 40, 41 e 50", SUPORTADO,
        "Serializacao interna explicita em ICMS00, ICMS20 ou ICMS40; nao libera producao.",
        ("services._icms_produto", "test_cenarios_tributarios"),
    ),
    _capacidade(
        "icms_cst_desconhecido", "tributacao", "CST ICMS fora da matriz", BLOQUEADO,
        "O preflight e o gerador recusam CST nao catalogado.",
        ("services._icms_produto", "services.pendencias_produto_fiscal"),
    ),
    _capacidade(
        "icms_csosn_suportados", "tributacao", "CSOSN 102, 103, 300 e 400", SUPORTADO,
        "Serializacao interna explicita no grupo ICMSSN102; nao libera producao.",
        ("services._icms_produto", "test_cenarios_tributarios"),
    ),
    _capacidade(
        "icms_csosn_desconhecido", "tributacao", "CSOSN fora da matriz", BLOQUEADO,
        "O preflight e o gerador recusam CSOSN nao catalogado.",
        ("services._icms_produto", "services.pendencias_produto_fiscal"),
    ),
    _capacidade(
        "pis", "tributacao", "PIS", DEPENDE_DE_PARAMETRIZACAO,
        "CST 01/02, 04-09, 49 e 99 possuem ramos explicitos; aliquota e aplicabilidade dependem do produto.",
        ("services._contribuicao_produto", "diagnostico_pagamentos_xsd"),
    ),
    _capacidade(
        "cofins", "tributacao", "COFINS", DEPENDE_DE_PARAMETRIZACAO,
        "CST 01/02, 04-09, 49 e 99 possuem ramos explicitos; aliquota e aplicabilidade dependem do produto.",
        ("services._contribuicao_produto", "diagnostico_pagamentos_xsd"),
    ),
    _capacidade(
        "ipi", "tributacao", "IPI", DEPENDE_DE_PARAMETRIZACAO,
        "Grupos tributado e nao tributado existem, mas exigem CST, cEnq e politica da natureza.",
        ("services._ipi_produto", "services._composicao_item_ipi"),
    ),
    _capacidade(
        "cbenef", "tributacao", "cBenef GO", DEPENDE_DE_PARAMETRIZACAO,
        "Decisao por produto e natureza existe; validade e divergencias exigem responsavel fiscal.",
        ("diagnostico_cbenef", "INVENTARIO_CBENEF_LEGADO.md"),
    ),
    _capacidade(
        "ibs_cbs", "tributacao", "IBS/CBS no XML", NAO_IMPLEMENTADO,
        "Suporte generico permanece ausente; somente o recorte GO CRT 3 operacao padrao esta catalogado.",
        ("ibs_cbs.catalogo", "ibs_cbs.contrato"),
    ),
    _capacidade(
        "ibs_cbs_crt3_operacao_padrao", "tributacao",
        "IBS/CBS GO CRT 3 - operacao padrao", DEPENDE_DE_HOMOLOGACAO,
        "CST 000/cClassTrib 000001 nos modelos 55/65 possui calculo, XML, total e pre-transmissao; producao segue bloqueada.",
        ("ibs_cbs.calculo", "ibs_cbs.xml", "test_ibs_cbs", "PL_010f_v1.04"),
    ),
    _capacidade(
        "pagamento_dinheiro", "pagamento", "Dinheiro", SUPORTADO,
        "Mapeamento tPag 01 e multiplas parcelas sao serializados offline.",
        ("services._codigo_pagamento", "test_diagnostico_pagamentos_xsd"),
    ),
    _capacidade(
        "pagamento_credito", "pagamento", "Cartao de credito", DEPENDE_DE_HOMOLOGACAO,
        "tPag 03 e vinculo fiscal sao cobertos offline; driver e adquirente reais estao ausentes.",
        ("services._adicionar_integracao_pagamento_nfce", "integracao_pagamentos.VERIFICADORES"),
    ),
    _capacidade(
        "pagamento_debito", "pagamento", "Cartao de debito", DEPENDE_DE_HOMOLOGACAO,
        "tPag 04 e vinculo fiscal sao cobertos offline; driver e adquirente reais estao ausentes.",
        ("services._adicionar_integracao_pagamento_nfce", "integracao_pagamentos.VERIFICADORES"),
    ),
    _capacidade(
        "pagamento_pix", "pagamento", "PIX", DEPENDE_DE_HOMOLOGACAO,
        "tPag 17 e vinculo sem bandeira inventada sao cobertos offline; provedor real esta ausente.",
        ("diagnostico_pagamentos_xsd", "integracao_pagamentos.VERIFICADORES"),
    ),
    _capacidade(
        "pagamento_vale_alimentacao", "pagamento", "Vale-alimentacao", DEPENDE_DE_HOMOLOGACAO,
        "tPag 10 passa offline, mas nao existe operadora/verificador real conectado.",
        ("services._codigo_pagamento", "integracao_pagamentos.VERIFICADORES"),
    ),
    _capacidade(
        "pagamento_vale_refeicao", "pagamento", "Vale-refeicao", DEPENDE_DE_HOMOLOGACAO,
        "tPag 11 passa offline, mas nao existe operadora/verificador real conectado.",
        ("services._codigo_pagamento", "integracao_pagamentos.VERIFICADORES"),
    ),
    _capacidade(
        "pagamento_dividido", "pagamento", "Pagamento dividido", DEPENDE_DE_HOMOLOGACAO,
        "Parcelas e paridade XML/banco sao cobertas offline; ponta a ponta real permanece pendente.",
        ("services.validar_vinculos_pagamentos_xml", "diagnostico_pagamentos_xsd"),
    ),
    _capacidade(
        "destinatario_nao_identificado", "destinatario", "Consumidor nao identificado", SUPORTADO,
        "A NFC-e omite dest de forma explicita quando essa opcao e selecionada.",
        ("services._documento_consumidor_nfce",),
    ),
    _capacidade(
        "destinatario_cpf", "destinatario", "CPF informado na NFC-e", SUPORTADO,
        "Documento e canonicalizado e serializado em dest/CPF.",
        ("services._documento_consumidor_nfce", "pdv.forms"),
    ),
    _capacidade(
        "destinatario_cnpj", "destinatario", "CNPJ quando aplicavel", DEPENDE_DE_HOMOLOGACAO,
        "Serializacao interna existe; consumidor contribuinte/B2B e aceite externo nao estao cobertos.",
        ("services._documento_consumidor_nfce", "services._dados_destinatario_nfe_pedido"),
    ),
    _capacidade(
        "endereco_emitente", "emitente", "Endereco fiscal do emitente", DEPENDE_DE_PARAMETRIZACAO,
        "Preflight GO exige endereco estruturado e CEP; nenhum valor ausente e inventado.",
        ("services.pendencias_endereco_emitente_nfce",),
    ),
    _capacidade(
        "qrcode_nfce", "documento", "QR Code NFC-e", DEPENDE_DE_HOMOLOGACAO,
        "Geracao offline existe; versao, URLs e CSC quando aplicavel exigem configuracao e homologacao.",
        ("qrcode_nfce", "AUDITORIA_PRE_HOMOLOGACAO_SEFAZ_GO.md"),
    ),
    _capacidade(
        "contingencia_nfce", "canal", "Contingencia NFC-e tpEmis 9", DEPENDE_DE_HOMOLOGACAO,
        "Fluxo offline, prazo e reconciliacao existem; comportamento real depende da SEFAZ-GO.",
        ("services.ativar_contingencia_offline", "sefaz_direta.capacidades"),
    ),
    _capacidade(
        "sefaz_direta_go", "canal", "SEFAZ direta GO", DEPENDE_DE_HOMOLOGACAO,
        "Sete capacidades estruturais estao offline; rede e producao permanecem bloqueadas.",
        ("roteamento_operacoes_fiscais", "MATRIZ_QUALIFICACAO_CANAIS_FISCAIS.md"),
    ),
    _capacidade(
        "focus", "canal", "Focus NFe", DEPENDE_DE_HOMOLOGACAO,
        "Cinco capacidades estruturais existem; CC-e e manifestacao falham fechado neste canal.",
        ("roteamento_operacoes_fiscais", "MATRIZ_QUALIFICACAO_CANAIS_FISCAIS.md"),
    ),
    _capacidade(
        "xsd_operacional", "schema", "XSD operacional do piloto", BLOQUEADO,
        "O 010f esta arquivado e integro, mas nao foi promovido, aprovado nem instalado.",
        ("auditoria_pacote_xsd", "fiscal_schemas/README.md"),
    ),
    _capacidade(
        "venda_interestadual", "operacao", "Venda interestadual", NAO_IMPLEMENTADO,
        "O gerador atual declara idDest interno e o avaliador GO recusa o cenario.",
        ("cenarios_tributarios.avaliar_cenario_fiscal_go",),
    ),
    _capacidade(
        "destinatario_contribuinte", "operacao", "Venda para contribuinte", NAO_IMPLEMENTADO,
        "A matriz GO bloqueia B2B contribuinte por exigir regras proprias.",
        ("cenarios_tributarios.avaliar_cenario_fiscal_go",),
    ),
    _capacidade(
        "frete", "operacao", "Venda com frete", NAO_IMPLEMENTADO,
        "O XML atual fixa modFrete sem frete e o avaliador recusa o cenario.",
        ("cenarios_tributarios.avaliar_cenario_fiscal_go",),
    ),
    _capacidade(
        "finalidade_nao_suportada", "operacao", "Finalidade diferente de venda normal", NAO_IMPLEMENTADO,
        "O avaliador GO recusa finalidade diferente de 1 e os geradores atuais fixam finNFe=1.",
        ("cenarios_tributarios.avaliar_cenario_fiscal_go", "services.gerar_xml_nfce"),
    ),
    _capacidade(
        "producao", "seguranca", "Emissao em producao", BLOQUEADO,
        "Nenhum resultado offline, XSD compilado ou adaptador estrutural libera producao.",
        ("sefaz_direta.adapter", "services_evidencias_homologacao"),
    ),
)


def matriz_capacidades_piloto_go():
    itens = []
    for capacidade in CAPACIDADES:
        item = dict(capacidade)
        item["evidencias"] = list(item["evidencias"])
        item["controle"] = list(CONTROLES_CAPACIDADE.get(item["codigo"], (DIAGNOSTICO,)))
        item["efeito_da_consulta"] = "SOMENTE_DIAGNOSTICO"
        item["bloqueio_operacional"] = BLOQUEIO_OPERACIONAL.get(
            item["codigo"], "NAO_COMPROVADO"
        )
        item["autoriza_producao"] = False
        itens.append(item)
    return itens


def consultar_capacidade_piloto_go(codigo):
    codigo = str(codigo or "").strip()
    for item in matriz_capacidades_piloto_go():
        if item["codigo"] == codigo:
            return item
    return {
        "codigo": codigo,
        "area": "desconhecida",
        "cenario": "Cenario nao catalogado",
        "status": BLOQUEADO,
        "escopo": (
            "Codigo ausente do catalogo diagnostico. Este resultado nao prova, por si so, "
            "que preflight, gerador ou transmissao recusarao o cenario."
        ),
        "evidencias": [],
        "controle": [DIAGNOSTICO],
        "efeito_da_consulta": "SOMENTE_DIAGNOSTICO",
        "bloqueio_operacional": "NAO_COMPROVADO",
        "autoriza_producao": False,
        "motivo": "CENARIO_NAO_CATALOGADO",
    }


def _sha256_json(conteudo):
    serializado = json.dumps(
        conteudo, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(serializado).hexdigest()


def diagnostico_pre_homologacao_go(base_dir):
    base = Path(base_dir).resolve()
    arquivo = base / PACOTE_XSD["arquivo_relativo"]
    auditoria = auditar_pacote_xsd(
        arquivo=arquivo,
        sha256_esperado=PACOTE_XSD["sha256"],
        versao=PACOTE_XSD["versao"],
    )
    xsd_operacionais = sorted(
        str(item.relative_to(base)).replace("\\", "/")
        for item in (base / "fiscal_schemas").glob("**/*.xsd")
    )
    itens = matriz_capacidades_piloto_go()
    contagem = Counter(item["status"] for item in itens)
    resultado = {
        "contrato": CONTRATO,
        "escopo": "DIAGNOSTICO_INTERNO_OFFLINE_SEM_HOMOLOGACAO",
        "xsd": {
            "pacote_atual": {
                "papel": "ARQUIVADO_PARA_TESTES_E_AUDITORIA",
                "versao": PACOTE_XSD["versao"],
                "arquivo": PACOTE_XSD["arquivo_relativo"],
                "sha256": auditoria["pacote"]["sha256"],
                "arquivo_raiz": auditoria["schema"]["arquivo_raiz"],
                "arquivo_raiz_sha256": auditoria["schema"]["arquivo_raiz_sha256"],
                "arquivos_xsd": auditoria["schema"]["arquivos_xsd"],
            },
            "pacote_oficial_identificado": {
                "versao": PACOTE_XSD["versao"],
                "publicado_em": PACOTE_XSD["publicado_em"],
                "fonte": PACOTE_XSD["fonte_oficial"],
                "listagem": PACOTE_XSD["listagem_oficial"],
                "sha256": PACOTE_XSD["sha256"],
            },
            "comparacao": "IGUAIS_POR_SHA256",
            "impacto": "SEM_SUBSTITUICAO; PROMOCAO E APROVACAO CONTINUAM PENDENTES",
            "arquivos_afetados": [],
            "operacional_no_repositorio": {
                "estado": "NAO_INSTALADO" if not xsd_operacionais else "XSD_PRESENTE_NAO_AVALIADO",
                "arquivos_xsd": xsd_operacionais,
            },
            "modelos_estruturais": ["55", "65"],
            "compilacao_offline": auditoria["schema"]["compilacao_offline"],
        },
        "capacidades": {
            "status_validos": sorted(STATUS_VALIDOS),
            "total": len(itens),
            "contagem": {status: contagem.get(status, 0) for status in sorted(STATUS_VALIDOS)},
            "itens": itens,
        },
        "politica": {
            "acessou_rede": False,
            "alterou_configuracao": False,
            "instalou_schema": False,
            "gerou_xml": False,
            "transmitiu": False,
            "homologacao_real": False,
            "producao_liberada": False,
        },
    }
    resultado["manifesto_sha256"] = _sha256_json(resultado)
    return resultado
