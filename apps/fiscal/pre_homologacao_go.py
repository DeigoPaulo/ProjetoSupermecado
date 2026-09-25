"""Diagnostico offline do XSD e das capacidades internas do piloto GO."""

import hashlib
import json
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

from django.core.exceptions import ValidationError
from django.utils import timezone

from .auditoria_pacote_xsd import (
    AuditoriaPacoteXSDErro,
    auditar_pacote_xsd,
    validar_xml_no_pacote_xsd,
)
from .chave_acesso import construir_chave_acesso
from .focus_sefaz_adapter import FocusNFeFiscalError, FocusNFeSefazAdapter
from .ibs_cbs.calculo import calcular_base_operacao_padrao, calcular_ibs_cbs_padrao
from .ibs_cbs.catalogo import METADADOS_CATALOGO, validar_classificacao
from .ibs_cbs.contrato import CONTRATO as CONTRATO_IBS_CBS, emissao_ibs_cbs_obrigatoria
from .ibs_cbs.validacao import validar_paridade_xml
from .ibs_cbs.xml import adicionar_grupo_item, adicionar_totais
from .qrcode_nfce import gerar_url_qrcode_nfce
from .sefaz_direta.adapter import SefazDiretaAdapter, SefazDiretaError
from .services import pendencias_endereco_emitente_nfce


CONTRATO = "fiscal_go_pre_homologation_matrix_v1"
CONTRATO_PRONTIDAO_INTERNA = "fiscal_go_internal_homologation_readiness_v1"

PRONTO_INTERNAMENTE = "PRONTO_INTERNAMENTE"
DEPENDE_DE_DADO_REAL = "DEPENDE_DE_DADO_REAL"
DEPENDE_DE_HOMOLOGACAO_EXTERNA = "DEPENDE_DE_HOMOLOGACAO_EXTERNA"
BLOQUEADO_LACUNA_INTERNA = "BLOQUEADO_LACUNA_INTERNA"
EVIDENCIA_ESTRUTURAL = "EVIDENCIA_ESTRUTURAL"
EVIDENCIA_EXECUTAVEL = "EVIDENCIA_EXECUTAVEL"
DEPENDENCIA_EXTERNA = "DEPENDENCIA_EXTERNA"
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
    "xml_assinado_xsd_55": {
        "tipo": EVIDENCIA_EXECUTAVEL,
        "origem": "SUITE_INTEGRADA",
        "teste": "apps.fiscal.tests.FiscalTests.test_nfe_go_ibs_cbs_confronta_xsd_010f_oficial",
    },
    "xml_assinado_xsd_65": {
        "tipo": EVIDENCIA_EXECUTAVEL,
        "origem": "SUITE_INTEGRADA",
        "teste": "apps.fiscal.tests.FiscalTests.test_nfce_go_ibs_cbs_confronta_xsd_010f_oficial",
    },
    "pre_transmissao_focus": {
        "tipo": EVIDENCIA_EXECUTAVEL,
        "origem": "SUITE_INTEGRADA",
        "teste": (
            "apps.fiscal.tests.FiscalTests."
            "test_pre_transmissao_focus_bloqueia_calculo_ibs_cbs_adulterado"
        ),
    },
    "pre_transmissao_sefaz_direta": {
        "tipo": EVIDENCIA_EXECUTAVEL,
        "origem": "SUITE_INTEGRADA",
        "teste": (
            "apps.fiscal.tests.FiscalTests."
            "test_pre_transmissao_sefaz_direta_bloqueia_calculo_ibs_cbs_adulterado"
        ),
    },
    "series_fiscais": {
        "tipo": EVIDENCIA_EXECUTAVEL,
        "origem": "SUITE_INTEGRADA",
        "teste": (
            "apps.fiscal.test_serie_ambiente.SerieFiscalAmbienteTests."
            "test_preparacao_venda_usa_somente_serie_do_ambiente_configurado"
        ),
    },
    "pagamentos_eletronicos": {
        "tipo": EVIDENCIA_EXECUTAVEL,
        "origem": "SUITE_INTEGRADA",
        "teste": (
            "apps.fiscal.tests.FiscalTests."
            "test_nfce_com_credito_pix_e_divisao_confronta_xsd_arquivado_e_canais"
        ),
    },
    "contingencia": {
        "tipo": EVIDENCIA_EXECUTAVEL,
        "origem": "SUITE_INTEGRADA",
        "teste": (
            "apps.fiscal.tests.FiscalTests."
            "test_contingencia_offline_gera_xml_prazo_auditoria_e_fila"
        ),
    },
    "assinatura_local": {
        "tipo": EVIDENCIA_EXECUTAVEL,
        "origem": "SUITE_INTEGRADA",
        "teste": "apps.fiscal.tests.FiscalTests.test_nfce_go_ibs_cbs_confronta_xsd_010f_oficial",
    },
    "endereco_emitente": {
        "tipo": EVIDENCIA_EXECUTAVEL,
        "origem": "SMOKE_CHECK_OFFLINE",
        "executor": "endereco_emitente",
    },
    "chave_acesso": {
        "tipo": EVIDENCIA_EXECUTAVEL,
        "origem": "SMOKE_CHECK_OFFLINE",
        "executor": "chave_acesso",
    },
    "qrcode_nfce": {
        "tipo": EVIDENCIA_EXECUTAVEL,
        "origem": "SMOKE_CHECK_OFFLINE",
        "executor": "qrcode_nfce",
    },
    "validador_xsd_offline": {
        "tipo": EVIDENCIA_EXECUTAVEL,
        "origem": "SMOKE_CHECK_OFFLINE",
        "executor": "validador_xsd_offline",
    },
    "bloqueio_producao_focus": {
        "tipo": EVIDENCIA_EXECUTAVEL,
        "origem": "SMOKE_CHECK_OFFLINE",
        "executor": "bloqueio_producao_focus",
    },
    "bloqueio_producao_sefaz": {
        "tipo": EVIDENCIA_EXECUTAVEL,
        "origem": "SMOKE_CHECK_OFFLINE",
        "executor": "bloqueio_producao_sefaz",
    },
}


def _provar_chave_acesso():
    chave = construir_chave_acesso(
        codigo_uf="52",
        aamm="2609",
        cnpj_emitente="11222333000181",
        modelo="65",
        serie="001",
        numero="000000001",
        tipo_emissao="1",
        codigo_numerico="12345678",
    )
    if len(chave) != 44:
        raise ValueError("Chave de acesso offline não possui 44 posições.")
    return {"chave_formada": True, "tamanho": len(chave)}


def _provar_endereco_emitente():
    filial = SimpleNamespace(
        uf="GO",
        logradouro="Rua Ficticia",
        numero="100",
        bairro="Centro",
        codigo_municipio_ibge="5208707",
        municipio="Goiania",
        cep="74000000",
        telefone="6230000000",
    )
    if pendencias_endereco_emitente_nfce(filial):
        raise ValidationError("Endereço fictício válido foi recusado pelo preflight.")
    filial.cep = "invalido"
    if not pendencias_endereco_emitente_nfce(filial):
        raise ValidationError("Endereço fictício inválido não foi bloqueado.")
    return {"caso_valido": True, "erro_esperado_exercitado": True}


def _provar_qrcode_nfce():
    chave = _provar_chave_acesso()
    documento = SimpleNamespace(
        chave_acesso=construir_chave_acesso(
            codigo_uf="52",
            aamm="2609",
            cnpj_emitente="11222333000181",
            modelo="65",
            serie="001",
            numero="000000001",
            tipo_emissao="1",
            codigo_numerico="12345678",
        ),
        ambiente="HOMOLOGACAO",
        status="AUTORIZADO",
        criado_em=timezone.now(),
        valor_total=Decimal("82.70"),
        venda=SimpleNamespace(
            documento_consumidor_tipo="NAO_IDENTIFICADO",
            documento_consumidor="",
        ),
    )
    configuracao = SimpleNamespace(url_qrcode_nfce="https://homologacao.exemplo.invalid/qrcode")
    url = gerar_url_qrcode_nfce(documento, configuracao)
    partes = urlsplit(url)
    if partes.scheme != "https" or "p=" not in partes.query:
        raise ValidationError("QR Code NFC-e offline não gerou URL HTTPS com parâmetros.")
    return {"url_gerada": True, "chave_formada": chave["chave_formada"]}


def _provar_validador_xsd_offline(base):
    try:
        validar_xml_no_pacote_xsd(
            xml=f'<NFe xmlns="{NFE_NS}"><infNFe versao="4.00"/></NFe>',
            arquivo=base / PACOTE_XSD["arquivo_relativo"],
            sha256_esperado=PACOTE_XSD["sha256"],
            versao=PACOTE_XSD["versao"],
        )
    except AuditoriaPacoteXSDErro:
        return {"validador_executado": True, "xml_invalido_rejeitado": True}
    raise AuditoriaPacoteXSDErro("Validador XSD aceitou XML deliberadamente incompleto.")


def _provar_bloqueio_producao_focus():
    adapter = FocusNFeSefazAdapter()
    adapter.base_url = "https://api.focusnfe.com.br"
    adapter.allow_production = False
    try:
        adapter._validar_ambiente("PRODUCAO")
    except FocusNFeFiscalError as exc:
        if "Produção Focus NFe bloqueada" in str(exc):
            return {"erro_esperado_exercitado": True}
        raise
    raise FocusNFeFiscalError("Produção Focus não foi bloqueada no smoke check.")


def _provar_bloqueio_producao_sefaz():
    adapter = SefazDiretaAdapter()
    adapter.allow_production = False
    documento = SimpleNamespace(filial=SimpleNamespace(uf="GO"), tipo_documento="NFCE")
    try:
        adapter._endpoint(documento, "PRODUCAO", "autorizacao")
    except SefazDiretaError as exc:
        if "Produção da SEFAZ direta permanece bloqueada" in str(exc):
            return {"erro_esperado_exercitado": True}
        raise
    raise SefazDiretaError("Produção SEFAZ direta não foi bloqueada no smoke check.")


EXECUTORES_EVIDENCIA = {
    "chave_acesso": lambda base: _provar_chave_acesso(),
    "endereco_emitente": lambda base: _provar_endereco_emitente(),
    "qrcode_nfce": lambda base: _provar_qrcode_nfce(),
    "validador_xsd_offline": _provar_validador_xsd_offline,
    "bloqueio_producao_focus": lambda base: _provar_bloqueio_producao_focus(),
    "bloqueio_producao_sefaz": lambda base: _provar_bloqueio_producao_sefaz(),
}


def _evidencia_local(base, codigo):
    """Executa smoke checks ou registra explicitamente a prova da suíte integrada."""
    definicao = EVIDENCIAS_PRONTIDAO[codigo]
    resultado = {
        "codigo": codigo,
        "tipo": definicao["tipo"],
        "origem": definicao["origem"],
        "estado": PRONTO_INTERNAMENTE,
        "executada_no_gate": definicao["origem"] == "SMOKE_CHECK_OFFLINE",
    }
    if definicao["origem"] == "SUITE_INTEGRADA":
        resultado.update(
            {
                "teste": definicao["teste"],
                "observacao": (
                    "Prova executável exige banco temporário e é validada pela "
                    "suíte, não por busca textual."
                ),
            }
        )
        return resultado
    try:
        resultado["resultado"] = EXECUTORES_EVIDENCIA[definicao["executor"]](base)
    except Exception as exc:
        resultado.update(
            {
                "estado": BLOQUEADO_LACUNA_INTERNA,
                "erro": exc.__class__.__name__,
            }
        )
    return resultado


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
    try:
        auditoria_xsd = auditar_pacote_xsd(
            arquivo=arquivo_xsd,
            sha256_esperado=PACOTE_XSD["sha256"],
            versao=PACOTE_XSD["versao"],
        )
    except Exception as exc:
        auditoria_xsd = None
        evidencia_pacote_xsd = {
            "codigo": "pacote_xsd_offline",
            "tipo": EVIDENCIA_EXECUTAVEL,
            "origem": "SMOKE_CHECK_OFFLINE",
            "estado": BLOQUEADO_LACUNA_INTERNA,
            "executada_no_gate": True,
            "erro": exc.__class__.__name__,
        }
    else:
        evidencia_pacote_xsd = {
            "codigo": "pacote_xsd_offline",
            "tipo": EVIDENCIA_EXECUTAVEL,
            "origem": "SMOKE_CHECK_OFFLINE",
            "estado": PRONTO_INTERNAMENTE,
            "executada_no_gate": True,
            "resultado": {
                "crc_integro": auditoria_xsd["pacote"]["crc_integro"],
                "sha256": auditoria_xsd["pacote"]["sha256"],
                "dependencias": len(auditoria_xsd["schema"]["dependencias"]),
                "compilacao_offline": auditoria_xsd["schema"]["compilacao_offline"],
            },
        }

    evidencias = {
        codigo: _evidencia_local(base, codigo) for codigo in EVIDENCIAS_PRONTIDAO
    }
    evidencias["pacote_xsd_offline"] = evidencia_pacote_xsd

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
    evidencias.update(
        {
            "contrato_ibs_cbs": {
                "codigo": "contrato_ibs_cbs",
                "tipo": EVIDENCIA_ESTRUTURAL,
                "origem": "CONTRATO_IMPORTADO",
                "estado": PRONTO_INTERNAMENTE if contrato_ok else BLOQUEADO_LACUNA_INTERNA,
                "executada_no_gate": True,
            },
            "catalogo_ibs_cbs": {
                "codigo": "catalogo_ibs_cbs",
                "tipo": EVIDENCIA_ESTRUTURAL,
                "origem": "METADADOS_VERSIONADOS",
                "estado": PRONTO_INTERNAMENTE if catalogo_ok else BLOQUEADO_LACUNA_INTERNA,
                "executada_no_gate": True,
            },
            "vigencia_ibs_cbs_2026": {
                "codigo": "vigencia_ibs_cbs_2026",
                "tipo": EVIDENCIA_EXECUTAVEL,
                "origem": "SMOKE_CHECK_OFFLINE",
                "estado": PRONTO_INTERNAMENTE if vigencia_ok else BLOQUEADO_LACUNA_INTERNA,
                "executada_no_gate": True,
            },
        }
    )
    nucleos = []
    for modelo in ("55", "65"):
        codigo = f"nucleo_ibs_cbs_{modelo}"
        try:
            nucleo = _validar_nucleo_ibs_cbs_offline(modelo)
        except Exception as exc:
            evidencias[codigo] = {
                "codigo": codigo,
                "tipo": EVIDENCIA_EXECUTAVEL,
                "origem": "SMOKE_CHECK_OFFLINE",
                "estado": BLOQUEADO_LACUNA_INTERNA,
                "executada_no_gate": True,
                "erro": exc.__class__.__name__,
            }
        else:
            nucleos.append(nucleo)
            evidencias[codigo] = {
                "codigo": codigo,
                "tipo": EVIDENCIA_EXECUTAVEL,
                "origem": "SMOKE_CHECK_OFFLINE",
                "estado": PRONTO_INTERNAMENTE,
                "executada_no_gate": True,
                "resultado": nucleo,
            }

    evidencias_nucleo = {
        "contrato_ibs_cbs",
        "catalogo_ibs_cbs",
        "vigencia_ibs_cbs_2026",
        "nucleo_ibs_cbs_55",
        "nucleo_ibs_cbs_65",
        "pacote_xsd_offline",
        "validador_xsd_offline",
        "xml_assinado_xsd_55",
        "xml_assinado_xsd_65",
        "assinatura_local",
    }
    evidencias_comuns = {
        "endereco_emitente",
        "series_fiscais",
        "chave_acesso",
        "qrcode_nfce",
        "pagamentos_eletronicos",
        "contingencia",
    }
    evidencias_por_canal = {
        "SEFAZ_DIRETA_GO": evidencias_nucleo
        | evidencias_comuns
        | {"pre_transmissao_sefaz_direta", "bloqueio_producao_sefaz"},
        "FOCUS": evidencias_nucleo
        | evidencias_comuns
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

    gaps = [
        item
        for item in evidencias.values()
        if item["estado"] == BLOQUEADO_LACUNA_INTERNA
    ]
    evidencias_xsd = {
        "pacote_xsd_offline",
        "validador_xsd_offline",
        "xml_assinado_xsd_55",
        "xml_assinado_xsd_65",
    }
    estado_xsd = (
        PRONTO_INTERNAMENTE
        if all(
            evidencias[codigo]["estado"] == PRONTO_INTERNAMENTE
            for codigo in evidencias_xsd
        )
        else BLOQUEADO_LACUNA_INTERNA
    )
    nucleo_ok = all(
        evidencias[codigo]["estado"] == PRONTO_INTERNAMENTE
        for codigo in evidencias_nucleo
    )
    estado_nucleo = PRONTO_INTERNAMENTE if nucleo_ok else BLOQUEADO_LACUNA_INTERNA

    capacidades = []
    for canal in ("SEFAZ_DIRETA_GO", "FOCUS"):
        evidencias_canal = sorted(evidencias_por_canal[canal])
        for capacidade in ("NF-e 55", "NFC-e 65", CONTRATO_IBS_CBS):
            estado = estado_evidencias_canal(canal)
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

    dependencias_comuns = (
        ("CNPJ da filial GO", True, "CNPJ_REAL"),
        ("Inscricao estadual da filial GO", True, "IE_REAL"),
        ("Certificado A1", True, "A1_REAL"),
        ("Senha do certificado A1", True, "SENHA_A1_REAL"),
        ("CSC e idCSC", False, "CONDICIONAL_APENAS_PARA_COMPATIBILIDADE_QRCODE_V2"),
        ("Autorizacao humana para iniciar homologacao", True, "ACEITE_FISCAL_E_OPERACIONAL"),
    )
    dependencias_por_canal = {
        "SEFAZ_DIRETA_GO": (
            (
                "Credenciamento e configuracoes reais da SEFAZ direta GO",
                True,
                "CREDENCIAMENTO_SEFAZ_DIRETA_REAL",
            ),
        ),
        "FOCUS": (
            ("Token Focus NFe de homologacao", True, "CREDENCIAL_FOCUS_REAL"),
            (
                "Endpoint vigente da Focus NFe",
                True,
                "CONFIGURACAO_FOCUS_REAL",
            ),
        ),
    }

    def dependencia_externa(item, obrigatorio, bloqueio):
        return {
            "item": item,
            "obrigatorio_para_o_cenario": obrigatorio,
            "tipo": DEPENDENCIA_EXTERNA,
            "estado": DEPENDE_DE_DADO_REAL,
            "bloqueio": bloqueio,
        }

    dia_zero_por_canal = {}
    for canal in ("SEFAZ_DIRETA_GO", "FOCUS"):
        estado = estado_evidencias_canal(canal)
        dependencias = [
            dependencia_externa(item, obrigatorio, bloqueio)
            for item, obrigatorio, bloqueio in (
                dependencias_comuns + dependencias_por_canal[canal]
            )
        ]
        dia_zero_por_canal[canal] = {
            "estado_interno": estado,
            "dependencias": dependencias,
            "ausencia_dados_reais_e_lacuna_interna": (
                estado == BLOQUEADO_LACUNA_INTERNA
            ),
        }

    dependencias_externas = [
        {
            "item": item,
            "obrigatorio_para_o_cenario": obrigatorio,
            "tipo": DEPENDENCIA_EXTERNA,
            "estado": DEPENDE_DE_DADO_REAL,
            "bloqueio": bloqueio,
        }
        for item, obrigatorio, bloqueio in dependencias_comuns
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
            "estado": estado_xsd,
            "pacote_integro": bool(
                auditoria_xsd and auditoria_xsd["pacote"]["crc_integro"]
            ),
            "sha256": (
                auditoria_xsd["pacote"]["sha256"] if auditoria_xsd else ""
            ),
            "dependencias_validas": bool(
                auditoria_xsd and auditoria_xsd["schema"]["dependencias"]
            ),
            "compilacao": bool(
                auditoria_xsd and auditoria_xsd["schema"]["compilacao_offline"]
            ),
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
            "canal_principal": "SEFAZ_DIRETA_GO",
            "estado_interno": dia_zero_por_canal["SEFAZ_DIRETA_GO"]["estado_interno"],
            "dependencias": (
                dependencias_externas
                + dia_zero_por_canal["SEFAZ_DIRETA_GO"]["dependencias"][-1:]
            ),
            "ausencia_dados_reais_e_lacuna_interna": dia_zero_por_canal[
                "SEFAZ_DIRETA_GO"
            ]["ausencia_dados_reais_e_lacuna_interna"],
            "por_canal": dia_zero_por_canal,
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
