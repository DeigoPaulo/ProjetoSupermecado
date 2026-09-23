"""Confronto offline da NFC-e com o XSD arquivado e os dois canais fiscais.

Esta rotina não instala schema, assina documento ou transmite dados. A validade
estrutural do pacote candidato não equivale a aprovação fiscal ou homologação.
"""

import hashlib
import json
import tempfile
import zipfile
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from lxml import etree

from .assinaturas import verificar_assinatura_xml
from .auditoria_pacote_xsd import auditar_pacote_xsd
from .focus_sefaz_adapter import FocusNFeFiscalError, FocusNFeSefazAdapter
from .sefaz_direta.adapter import NFE_NS, SefazDiretaAdapter, SefazDiretaError


CONTRATO = "nfce_pagamentos_xsd_offline_v1"
PACOTE_RELATIVO = Path("docs/evidencias/nfe_2026_09_10/schemas_010f.zip")
PACOTE_SHA256 = "b8589490a58a09a993a80e6ac4d7ed10f20892061ecfc56719337098d4b95998"
VERSAO = "PL_010f_v1.04"
CAMPOS_FOCUS = {
    "tipo_integracao": "tpIntegra",
    "cnpj_credenciadora": "CNPJ",
    "bandeira_operadora": "tBand",
    "numero_autorizacao": "cAut",
    "cnpj_beneficiario": "CNPJReceb",
    "id_terminal_pagamento": "idTermPag",
}


def _sha256(conteudo):
    return hashlib.sha256(conteudo).hexdigest()


def _projecao_xml(raiz):
    ns = {"nfe": NFE_NS}
    parcelas = []
    for det in raiz.findall("./nfe:infNFe/nfe:pag/nfe:detPag", ns):
        card = det.find("nfe:card", ns)
        item = {
            "indicador_pagamento": det.findtext("nfe:indPag", default="0", namespaces=ns) or "0",
            "forma_pagamento": det.findtext("nfe:tPag", default="", namespaces=ns),
            "valor_pagamento": det.findtext("nfe:vPag", default="", namespaces=ns),
        }
        if card is not None:
            for campo, tag in CAMPOS_FOCUS.items():
                valor = card.findtext(f"nfe:{tag}", namespaces=ns)
                if valor is not None:
                    item[campo] = valor
        parcelas.append(item)
    return parcelas


def _hash_projecao(parcelas):
    return _sha256(json.dumps(parcelas, sort_keys=True, ensure_ascii=True).encode("utf-8"))


def diagnosticar_nfce_pagamentos_xsd_offline(xml):
    """Aceita XML já gerado; retorna somente hashes/estados, nunca XML ou dados fiscais."""
    pacote = Path(settings.BASE_DIR) / PACOTE_RELATIVO
    auditoria = auditar_pacote_xsd(
        arquivo=pacote, sha256_esperado=PACOTE_SHA256, versao=VERSAO,
    )
    xml_bytes = xml.encode("utf-8") if isinstance(xml, str) else bytes(xml)
    resultado = {
        "contrato": CONTRATO,
        "pacote_arquivado": str(PACOTE_RELATIVO).replace("\\", "/"),
        "pacote_sha256": auditoria["pacote"]["sha256"],
        "xsd_raiz_sha256": auditoria["schema"]["arquivo_raiz_sha256"],
        "xml_sha256": _sha256(xml_bytes),
        "xsd": {"conforme": False},
        "assinatura": {"conforme": False},
        "focus": {"conforme": False},
        "sefaz_direta": {"conforme": False},
        "conforme_offline": False,
        "homologacao_real": False,
        "promocao_schema": False,
    }
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    try:
        raiz = etree.fromstring(xml_bytes, parser)
    except etree.XMLSyntaxError:
        resultado["xsd"]["erro"] = "XML_MALFORMADO"
        return resultado

    # Somente os membros previamente aprovados pela auditoria são extraídos para
    # um diretório descartável. Imports/includes XSD permanecem sem acesso à rede.
    with tempfile.TemporaryDirectory(prefix="nfce-pagamentos-xsd-") as temporario:
        base = Path(temporario)
        with zipfile.ZipFile(pacote) as arquivo_zip:
            for membro in auditoria["schema"]["arquivos_xsd"]:
                destino = base.joinpath(*Path(membro["caminho"]).parts)
                destino.parent.mkdir(parents=True, exist_ok=True)
                destino.write_bytes(arquivo_zip.read(membro["caminho"]))
        raiz_xsd = base.joinpath(*Path(auditoria["schema"]["arquivo_raiz"]).parts)
        schema = etree.XMLSchema(etree.parse(str(raiz_xsd), parser))
        if schema.validate(raiz):
            resultado["xsd"]["conforme"] = True
        else:
            erro = schema.error_log.last_error
            resultado["xsd"].update({
                "erro": "DIVERGENTE_DO_XSD_ARQUIVADO",
                "tipo": erro.type_name if erro is not None else "INDETERMINADO",
                "linha": erro.line if erro is not None else None,
                "caminho": erro.path if erro is not None else None,
            })

    try:
        verificar_assinatura_xml(xml_bytes.decode("utf-8"))
        resultado["assinatura"]["conforme"] = True
    except (ValidationError, UnicodeError):
        resultado["assinatura"]["erro"] = "ASSINATURA_AUSENTE_OU_INVALIDA"

    if etree.QName(raiz).localname != "NFe" or etree.QName(raiz).namespace != NFE_NS:
        return resultado
    parcelas = _projecao_xml(raiz)
    resultado["parcelas"] = len(parcelas)
    resultado["projecao_xml_sha256"] = _hash_projecao(parcelas)
    try:
        payload, modelo = FocusNFeSefazAdapter()._payload_xml(xml_bytes.decode("utf-8"))
        projecao_focus = payload.get("formas_pagamento", [])
        resultado["focus"] = {
            "conforme": modelo == "65" and projecao_focus == parcelas,
            "parcelas": len(projecao_focus),
            "projecao_sha256": _hash_projecao(projecao_focus),
        }
    except (FocusNFeFiscalError, ValueError, UnicodeError, AttributeError, TypeError):
        resultado["focus"]["erro"] = "CONVERSAO_OFFLINE_FALHOU"

    try:
        adapter = SefazDiretaAdapter()
        xml_integral = etree.tostring(raiz, method="c14n", exclusive=True)
        envi = etree.Element(etree.QName(NFE_NS, "enviNFe"), nsmap={None: NFE_NS}, versao="4.00")
        etree.SubElement(envi, etree.QName(NFE_NS, "idLote")).text = "000000000000001"
        etree.SubElement(envi, etree.QName(NFE_NS, "indSinc")).text = "1"
        envi.append(raiz)
        envelope = etree.fromstring(adapter._envelope("autorizacao", envi), parser)
        nfe_transportada = envelope.find(f".//{{{NFE_NS}}}NFe")
        projecao_direta = _projecao_xml(nfe_transportada) if nfe_transportada is not None else []
        xml_integral_preservado = (
            nfe_transportada is not None
            and etree.tostring(nfe_transportada, method="c14n", exclusive=True) == xml_integral
        )
        resultado["sefaz_direta"] = {
            "conforme": xml_integral_preservado and projecao_direta == parcelas,
            "parcelas": len(projecao_direta),
            "projecao_sha256": _hash_projecao(projecao_direta),
            "xml_integral_preservado": xml_integral_preservado,
        }
    except (SefazDiretaError, ValueError, etree.XMLSyntaxError, TypeError):
        resultado["sefaz_direta"]["erro"] = "ENVELOPE_OFFLINE_FALHOU"

    resultado["conforme_offline"] = all(resultado[canal]["conforme"] for canal in (
        "xsd", "assinatura", "focus", "sefaz_direta",
    ))
    return resultado
