import base64
import hashlib
import hmac
from datetime import UTC, datetime

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.serialization.pkcs12 import load_key_and_certificates
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from lxml import etree

from .certificados import abrir_certificado_a1

NFE_NS = "http://www.portalfiscal.inf.br/nfe"
DSIG_NS = "http://www.w3.org/2000/09/xmldsig#"
C14N_ALGORITHM = "http://www.w3.org/TR/2001/REC-xml-c14n-20010315"
ENVELOPED_ALGORITHM = "http://www.w3.org/2000/09/xmldsig#enveloped-signature"
RSA_SHA1_ALGORITHM = "http://www.w3.org/2000/09/xmldsig#rsa-sha1"
SHA1_ALGORITHM = "http://www.w3.org/2000/09/xmldsig#sha1"


def _parser_seguro():
    return etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, remove_blank_text=False)


def _canonicalizar(elemento):
    return etree.tostring(elemento, method="c14n", exclusive=False, with_comments=False)


def _carregar_chave_certificado(configuracao):
    conteudo, senha = abrir_certificado_a1(configuracao)
    try:
        chave, certificado, _ = load_key_and_certificates(
            conteudo,
            senha.encode("utf-8") if senha else None,
        )
    except Exception as exc:
        raise ValidationError("Não foi possível abrir o certificado A1 para assinatura fiscal.") from exc
    if not isinstance(chave, rsa.RSAPrivateKey) or certificado is None:
        raise ValidationError("A assinatura fiscal exige certificado A1 com chave privada RSA.")
    agora = datetime.now(UTC)
    inicio = certificado.not_valid_before_utc
    fim = certificado.not_valid_after_utc
    if agora < inicio or agora > fim:
        raise ValidationError("Certificado A1 fora do período de validade para assinatura fiscal.")
    return chave, certificado


def assinatura_local_disponivel(configuracao=None):
    if not settings.FISCAL_LOCAL_XML_SIGNATURE_ENABLED:
        return False
    return bool(configuracao and configuracao.certificado_status == "valido")


def assinar_parametros_qrcode_nfce(configuracao, parametros):
    """Assina os parametros do QR Code em contingência com o A1 do emitente."""
    chave, _ = _carregar_chave_certificado(configuracao)
    assinatura = chave.sign(parametros.encode("utf-8"), padding.PKCS1v15(), hashes.SHA1())
    return base64.b64encode(assinatura).decode("ascii")


def assinar_xml_documento(documento):
    if not settings.FISCAL_LOCAL_XML_SIGNATURE_ENABLED:
        raise ValidationError("XML fiscal não está assinado porque a assinatura XML local está desabilitada.")
    if not documento.xml_conteudo:
        raise ValidationError("Documento fiscal sem XML para assinatura.")
    try:
        raiz = etree.fromstring(documento.xml_conteudo.encode("utf-8"), _parser_seguro())
    except etree.XMLSyntaxError as exc:
        raise ValidationError("XML fiscal malformado para assinatura.") from exc

    inf_nfe = raiz.find(f"{{{NFE_NS}}}infNFe")
    if inf_nfe is None:
        raise ValidationError("XML fiscal sem infNFe para assinatura.")
    identificador = inf_nfe.get("Id", "")
    if identificador != f"NFe{documento.chave_acesso}":
        raise ValidationError("Identificador infNFe diverge da chave antes da assinatura.")

    for assinatura_existente in raiz.findall(f"{{{DSIG_NS}}}Signature"):
        raiz.remove(assinatura_existente)

    chave, certificado = _carregar_chave_certificado(documento.filial.configuracao_fiscal)
    digest_value = base64.b64encode(hashlib.sha1(_canonicalizar(inf_nfe)).digest()).decode("ascii")

    assinatura = etree.SubElement(raiz, etree.QName(DSIG_NS, "Signature"), nsmap={"ds": DSIG_NS})
    signed_info = etree.SubElement(assinatura, etree.QName(DSIG_NS, "SignedInfo"))
    etree.SubElement(
        signed_info,
        etree.QName(DSIG_NS, "CanonicalizationMethod"),
        Algorithm=C14N_ALGORITHM,
    )
    etree.SubElement(
        signed_info,
        etree.QName(DSIG_NS, "SignatureMethod"),
        Algorithm=RSA_SHA1_ALGORITHM,
    )
    referencia = etree.SubElement(
        signed_info,
        etree.QName(DSIG_NS, "Reference"),
        URI=f"#{identificador}",
    )
    transformacoes = etree.SubElement(referencia, etree.QName(DSIG_NS, "Transforms"))
    etree.SubElement(
        transformacoes,
        etree.QName(DSIG_NS, "Transform"),
        Algorithm=ENVELOPED_ALGORITHM,
    )
    etree.SubElement(
        transformacoes,
        etree.QName(DSIG_NS, "Transform"),
        Algorithm=C14N_ALGORITHM,
    )
    etree.SubElement(referencia, etree.QName(DSIG_NS, "DigestMethod"), Algorithm=SHA1_ALGORITHM)
    etree.SubElement(referencia, etree.QName(DSIG_NS, "DigestValue")).text = digest_value

    assinatura_bytes = chave.sign(_canonicalizar(signed_info), padding.PKCS1v15(), hashes.SHA1())
    etree.SubElement(assinatura, etree.QName(DSIG_NS, "SignatureValue")).text = base64.b64encode(
        assinatura_bytes
    ).decode("ascii")
    key_info = etree.SubElement(assinatura, etree.QName(DSIG_NS, "KeyInfo"))
    x509_data = etree.SubElement(key_info, etree.QName(DSIG_NS, "X509Data"))
    certificado_der = certificado.public_bytes(serialization.Encoding.DER)
    etree.SubElement(x509_data, etree.QName(DSIG_NS, "X509Certificate")).text = base64.b64encode(
        certificado_der
    ).decode("ascii")

    documento.xml_conteudo = etree.tostring(
        raiz,
        encoding="utf-8",
        xml_declaration=True,
    ).decode("utf-8")
    documento.xml_assinado_em = timezone.now()
    documento.certificado_serial_assinatura = format(certificado.serial_number, "X")
    documento.save(
        update_fields=[
            "xml_conteudo",
            "xml_assinado_em",
            "certificado_serial_assinatura",
            "atualizado_em",
        ]
    )
    return documento


def verificar_assinatura_xml(xml):
    try:
        raiz = etree.fromstring(xml.encode("utf-8"), _parser_seguro())
        assinatura = raiz.find(f"{{{DSIG_NS}}}Signature")
        signed_info = assinatura.find(f"{{{DSIG_NS}}}SignedInfo")
        referencia = signed_info.find(f"{{{DSIG_NS}}}Reference")
        assinatura_valor = assinatura.findtext(f"{{{DSIG_NS}}}SignatureValue")
        certificado_valor = assinatura.findtext(
            f"{{{DSIG_NS}}}KeyInfo/{{{DSIG_NS}}}X509Data/{{{DSIG_NS}}}X509Certificate"
        )
        digest_informado = referencia.findtext(f"{{{DSIG_NS}}}DigestValue")
    except (AttributeError, etree.XMLSyntaxError) as exc:
        raise ValidationError("Estrutura de assinatura XML fiscal incompleta.") from exc

    uri = referencia.get("URI", "")
    if not uri.startswith("#"):
        raise ValidationError("Referência da assinatura fiscal inválida.")
    alvos = [elemento for elemento in raiz.iter() if elemento.get("Id") == uri[1:]]
    if not alvos:
        raise ValidationError("Elemento referenciado pela assinatura fiscal não foi encontrado.")
    if len(alvos) != 1:
        raise ValidationError("Referência duplicada na assinatura fiscal.")
    alvo = alvos[0]
    if alvo.tag != f"{{{NFE_NS}}}infNFe" or not uri.startswith("#NFe"):
        raise ValidationError("Referência da assinatura fiscal não aponta para infNFe.")
    try:
        algoritmos = {
            "canonicalizacao": signed_info.find(f"{{{DSIG_NS}}}CanonicalizationMethod").get("Algorithm"),
            "assinatura": signed_info.find(f"{{{DSIG_NS}}}SignatureMethod").get("Algorithm"),
            "digest": referencia.find(f"{{{DSIG_NS}}}DigestMethod").get("Algorithm"),
        }
        transformacoes = [
            item.get("Algorithm")
            for item in referencia.findall(f"{{{DSIG_NS}}}Transforms/{{{DSIG_NS}}}Transform")
        ]
    except AttributeError as exc:
        raise ValidationError("Algoritmos da assinatura fiscal não foram informados.") from exc
    if algoritmos != {
        "canonicalizacao": C14N_ALGORITHM,
        "assinatura": RSA_SHA1_ALGORITHM,
        "digest": SHA1_ALGORITHM,
    }:
        raise ValidationError("Algoritmos da assinatura fiscal divergem do padrão NF-e.")
    if transformacoes != [ENVELOPED_ALGORITHM, C14N_ALGORITHM]:
        raise ValidationError("Transformacoes da assinatura fiscal divergem do padrão NF-e.")
    digest_calculado = base64.b64encode(hashlib.sha1(_canonicalizar(alvo)).digest()).decode("ascii")
    if not hmac.compare_digest(digest_informado or "", digest_calculado):
        raise ValidationError("Digest da assinatura fiscal inválido.")

    try:
        certificado = x509.load_der_x509_certificate(base64.b64decode(certificado_valor))
        certificado.public_key().verify(
            base64.b64decode(assinatura_valor),
            _canonicalizar(signed_info),
            padding.PKCS1v15(),
            hashes.SHA1(),
        )
    except (ValueError, TypeError, InvalidSignature) as exc:
        raise ValidationError("Assinatura criptografica do XML fiscal inválida.") from exc
    return {
        "valida": True,
        "certificado_serial": format(certificado.serial_number, "X"),
        "referencia": uri,
    }
