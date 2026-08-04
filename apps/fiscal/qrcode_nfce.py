import base64
from io import BytesIO
from xml.etree import ElementTree as ET
from urllib.parse import quote, urlsplit, urlunsplit

import qrcode
from django.core.exceptions import ValidationError
from django.utils import timezone

from .assinaturas import assinar_parametros_qrcode_nfce
from apps.vendas.models import TipoDocumentoConsumidor

from .models import AmbienteFiscal, StatusDocumentoFiscal

VERSAO_QRCODE_NFCE = "3"


def _url_com_parametro(base, parametros):
    partes = urlsplit(base.strip())
    if partes.scheme not in {"http", "https"} or not partes.netloc:
        raise ValidationError("Configure uma URL oficial valida para o QR Code NFC-e.")
    novo = f"p={quote(parametros, safe='|')}"
    consulta = f"{partes.query}&{novo}" if partes.query else novo
    return urlunsplit((partes.scheme, partes.netloc, partes.path, consulta, partes.fragment))


def _destinatario(documento):
    venda = documento.venda
    tipo = venda.documento_consumidor_tipo
    valor = "".join(ch for ch in (venda.documento_consumidor or "") if ch.isdigit())
    if tipo == TipoDocumentoConsumidor.CPF and len(valor) == 11:
        return "2", valor
    if tipo == TipoDocumentoConsumidor.CNPJ and len(valor) == 14:
        return "1", valor
    if tipo == TipoDocumentoConsumidor.ESTRANGEIRO and venda.documento_consumidor:
        return "3", venda.documento_consumidor.strip()
    return "", ""


def parametros_qrcode_nfce(documento, configuracao=None):
    configuracao = configuracao or documento.filial.configuracao_fiscal
    chave = "".join(ch for ch in documento.chave_acesso if ch.isdigit())
    if len(chave) != 44:
        raise ValidationError("A NFC-e precisa de uma chave de acesso valida para gerar o QR Code.")
    ambiente = "2" if documento.ambiente == AmbienteFiscal.HOMOLOGACAO else "1"
    parametros = [chave, VERSAO_QRCODE_NFCE, ambiente]
    if documento.status == StatusDocumentoFiscal.CONTINGENCIA:
        tipo_destino, destino = _destinatario(documento)
        parametros.extend([
            timezone.localtime(documento.criado_em).strftime("%d"),
            f"{documento.valor_total:.2f}",
            tipo_destino,
            destino,
        ])
        base_assinada = "|".join(parametros)
        parametros.append(assinar_parametros_qrcode_nfce(configuracao, base_assinada))
    return "|".join(parametros)


def gerar_url_qrcode_nfce(documento, configuracao=None):
    configuracao = configuracao or documento.filial.configuracao_fiscal
    if not configuracao.url_qrcode_nfce.strip():
        raise ValidationError("Configure a URL oficial do QR Code NFC-e para está filial.")
    return _url_com_parametro(configuracao.url_qrcode_nfce, parametros_qrcode_nfce(documento, configuracao))


def obter_url_qrcode_nfce(documento):
    """Preserva em reimpressoes o QR originalmente gravado no XML fiscal."""
    if documento.xml_conteudo:
        try:
            raiz = ET.fromstring(documento.xml_conteudo)
            elemento = raiz.find("{http://www.portalfiscal.inf.br/nfe}infNFeSupl/{http://www.portalfiscal.inf.br/nfe}qrCode")
            if elemento is not None and (elemento.text or "").strip():
                return elemento.text.strip()
        except ET.ParseError:
            pass
    return gerar_url_qrcode_nfce(documento)


def gerar_qrcode_data_uri(url):
    imagem = qrcode.make(url)
    arquivo = BytesIO()
    imagem.save(arquivo, format="PNG")
    return "data:image/png;base64," + base64.b64encode(arquivo.getvalue()).decode("ascii")