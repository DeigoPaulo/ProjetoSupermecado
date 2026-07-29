import hashlib
from pathlib import Path
from xml.etree import ElementTree as ET

from django.conf import settings
from django.core.exceptions import ValidationError
from lxml import etree

from .models import TipoDocumentoFiscal

NFE_NS = "http://www.portalfiscal.inf.br/nfe"
DSIG_NS = "http://www.w3.org/2000/09/xmldsig#"


def _digito_verificador_valido(chave):
    pesos = [2, 3, 4, 5, 6, 7, 8, 9]
    soma = sum(int(digito) * pesos[indice % len(pesos)] for indice, digito in enumerate(reversed(chave[:-1])))
    resultado = 11 - (soma % 11)
    esperado = "0" if resultado >= 10 else str(resultado)
    return chave[-1] == esperado


def _arquivo_schema_configurado():
    diretorio = Path(settings.FISCAL_SCHEMA_DIR).resolve()
    arquivo = (diretorio / settings.FISCAL_NFE_SCHEMA_FILE).resolve()
    if diretorio != arquivo.parent and diretorio not in arquivo.parents:
        raise ValidationError("Arquivo XSD fiscal deve permanecer dentro do diretorio configurado.")
    return arquivo


def diagnosticar_schemas_fiscais():
    try:
        arquivo = _arquivo_schema_configurado()
    except (OSError, ValidationError) as exc:
        return {"configurado": False, "pronto": False, "arquivo": "", "sha256": "", "erro": str(exc)}
    if not arquivo.is_file():
        return {
            "configurado": False,
            "pronto": False,
            "arquivo": str(arquivo),
            "sha256": "",
            "erro": "Arquivo raiz do schema fiscal nao encontrado.",
        }
    conteudo = arquivo.read_bytes()
    sha256 = hashlib.sha256(conteudo).hexdigest()
    esperado = settings.FISCAL_SCHEMA_SHA256.strip().lower()
    if esperado and sha256 != esperado:
        return {
            "configurado": True,
            "pronto": False,
            "arquivo": str(arquivo),
            "sha256": sha256,
            "erro": "SHA-256 do schema fiscal diverge do valor configurado.",
        }
    try:
        parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
        schema = etree.XMLSchema(etree.parse(str(arquivo), parser))
    except (OSError, etree.XMLSyntaxError, etree.XMLSchemaParseError) as exc:
        return {
            "configurado": True,
            "pronto": False,
            "arquivo": str(arquivo),
            "sha256": sha256,
            "erro": f"Pacote XSD fiscal invalido: {exc}",
        }
    return {
        "configurado": True,
        "pronto": True,
        "arquivo": str(arquivo),
        "sha256": sha256,
        "erro": "",
        "schema": schema,
    }


def validar_xml_schema(documento):
    diagnostico = diagnosticar_schemas_fiscais()
    if not diagnostico["pronto"]:
        raise ValidationError(diagnostico["erro"] or "Pacote XSD fiscal nao esta pronto.")
    try:
        parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
        raiz = etree.fromstring(documento.xml_conteudo.encode("utf-8"), parser)
        diagnostico["schema"].assertValid(raiz)
    except (etree.XMLSyntaxError, etree.DocumentInvalid) as exc:
        detalhe = str(exc.error_log.last_error or exc)
        raise ValidationError(f"XML fiscal rejeitado pelo schema configurado: {detalhe}") from exc
    return {"valido": True, "arquivo": diagnostico["arquivo"], "sha256": diagnostico["sha256"]}

def validar_xml_pre_transmissao(documento, adapter):
    xml = documento.xml_conteudo or ""
    if "<!DOCTYPE" in xml.upper() or "<!ENTITY" in xml.upper():
        raise ValidationError("XML fiscal com DTD ou entidade externa nao pode ser transmitido.")
    try:
        raiz = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise ValidationError("XML fiscal malformado.") from exc

    chave = documento.chave_acesso or ""
    if len(chave) != 44 or not chave.isdigit() or not _digito_verificador_valido(chave):
        raise ValidationError("Chave de acesso fiscal invalida.")

    inf_nfe = raiz.find(f"{{{NFE_NS}}}infNFe")
    if inf_nfe is None or inf_nfe.get("Id") != f"NFe{chave}":
        raise ValidationError("Identificador infNFe nao corresponde a chave de acesso.")

    modelo = inf_nfe.findtext(f"{{{NFE_NS}}}ide/{{{NFE_NS}}}mod")
    modelo_esperado = "65" if documento.tipo_documento == TipoDocumentoFiscal.NFCE else "55"
    if modelo != modelo_esperado:
        raise ValidationError("Modelo fiscal do XML nao corresponde ao documento.")
    if inf_nfe.findtext(f"{{{NFE_NS}}}ide/{{{NFE_NS}}}cDV") != chave[-1]:
        raise ValidationError("Digito verificador do XML nao corresponde a chave de acesso.")

    if not bool(getattr(adapter, "valida_schema", False)):
        validar_xml_schema(documento)

    assinatura = raiz.find(f"{{{DSIG_NS}}}Signature")
    if assinatura is None and not bool(getattr(adapter, "assina_xml", False)):
        raise ValidationError(
            "XML fiscal ainda nao esta assinado e o adaptador configurado nao declarou assinatura propria."
        )
    return {
        "chave_acesso": chave,
        "modelo": modelo,
        "assinado_no_xml": assinatura is not None,
        "assinatura_pelo_adaptador": assinatura is None,
    }
