from urllib.parse import urlparse

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from lxml import etree

from ..assinaturas import assinar_xml_elemento_fiscal
from ..manifestacao_adapters import CONTRATO_MANIFESTACAO_DESTINATARIO
from ..models import ConfiguracaoFiscal
from .adapter import NFE_NS, SefazDiretaAdapter, SefazDiretaError


ENDPOINTS_MANIFESTACAO = {
    "HOMOLOGACAO": "https://hom1.nfe.fazenda.gov.br/NFeRecepcaoEvento4/NFeRecepcaoEvento4.asmx",
    "PRODUCAO": "https://www.nfe.fazenda.gov.br/NFeRecepcaoEvento4/NFeRecepcaoEvento4.asmx",
}
HOSTS_OFICIAIS_MANIFESTACAO = {"hom1.nfe.fazenda.gov.br", "www.nfe.fazenda.gov.br"}
DESCRICOES_EVENTO = {
    "210200": "Confirmacao da Operacao",
    "210210": "Ciencia da Operacao",
    "210220": "Desconhecimento da Operacao",
    "210240": "Operacao nao Realizada",
}


class SefazDiretaManifestacaoAdapter:
    nome = "SEFAZ direta - Manifestação do Destinatário"
    contrato = CONTRATO_MANIFESTACAO_DESTINATARIO

    def __init__(self, transport=None):
        self.network_enabled = bool(
            getattr(settings, "SEFAZ_DIRETA_MANIFESTACAO_NETWORK_ENABLED", False)
        )
        self.allow_production = bool(
            getattr(settings, "SEFAZ_DIRETA_MANIFESTACAO_ALLOW_PRODUCTION", False)
        )
        self.endpoints = dict(ENDPOINTS_MANIFESTACAO)
        self.endpoints.update(
            getattr(settings, "SEFAZ_DIRETA_MANIFESTACAO_ENDPOINTS", {}) or {}
        )
        self._xml = SefazDiretaAdapter(transport=transport)
        self._xml.network_enabled = self.network_enabled

    def diagnosticar(self):
        return {
            "disponivel": self.network_enabled,
            "ambiente": "Ambiente Nacional",
            "mensagem": (
                "Rede liberada para homologação controlada."
                if self.network_enabled
                else "Adaptador dormente: libere a rede somente durante a homologação."
            ),
        }

    def manifestar(self, *, documento, tipo, justificativa="", idempotency_key=""):
        del idempotency_key
        tipo = str(tipo or "")
        if tipo not in DESCRICOES_EVENTO:
            raise ValidationError("Tipo de manifestação do destinatário inválido.")
        filial = documento.filial_destino
        configuracao = (
            ConfiguracaoFiscal.objects.filter(filial=filial, ativo=True).first()
            if getattr(filial, "pk", None)
            else getattr(filial, "configuracao_fiscal", None)
        )
        if configuracao is None:
            raise SefazDiretaManifestacaoError(
                "A filial destinatária não possui configuração fiscal."
            )
        ambiente = str(configuracao.ambiente or "").upper()
        endpoint = self._endpoint(ambiente)
        chave = self._xml._chave(documento.chave_acesso)
        cnpj = self._xml._cnpj(configuracao)

        env = etree.Element(
            etree.QName(NFE_NS, "envEvento"), nsmap={None: NFE_NS}, versao="1.00"
        )
        self._xml._sub(env, "idLote", f"{int(documento.pk):015d}"[-15:])
        evento = etree.SubElement(env, etree.QName(NFE_NS, "evento"), versao="1.00")
        inf = etree.SubElement(
            evento,
            etree.QName(NFE_NS, "infEvento"),
            Id=f"ID{tipo}{chave}01",
        )
        self._xml._sub(inf, "cOrgao", "91")
        self._xml._sub(inf, "tpAmb", self._xml._tp_amb(ambiente))
        self._xml._sub(inf, "CNPJ", cnpj)
        self._xml._sub(inf, "chNFe", chave)
        self._xml._sub(inf, "dhEvento", timezone.localtime().isoformat(timespec="seconds"))
        self._xml._sub(inf, "tpEvento", tipo)
        self._xml._sub(inf, "nSeqEvento", "1")
        self._xml._sub(inf, "verEvento", "1.00")
        det = etree.SubElement(inf, etree.QName(NFE_NS, "detEvento"), versao="1.00")
        self._xml._sub(det, "descEvento", DESCRICOES_EVENTO[tipo])
        if tipo == "210240":
            self._xml._sub(det, "xJust", justificativa)

        assinado = assinar_xml_elemento_fiscal(
            etree.tostring(env, encoding="unicode"),
            configuracao,
            nome_elemento="infEvento",
            prefixo_id=f"ID{tipo}",
        )
        resposta = self._xml._enviar(
            "evento", endpoint, self._xml._parse_xml(assinado), configuracao
        )
        ret = self._xml._elemento_retorno(resposta, "retEnvEvento")
        inf_evento = self._xml._ultimo_local(ret, "infEvento")
        alvo = inf_evento if inf_evento is not None else ret
        codigo = self._xml._texto_local(alvo, "cStat")
        motivo = self._xml._mensagem(alvo)
        status = "AUTORIZADA" if codigo in {"135", "136"} else "REJEITADA"
        if codigo in {"105", "128"} and inf_evento is None:
            status = "PENDENTE"
        return {
            "contrato": self.contrato,
            "status": status,
            "codigo_status": codigo,
            "protocolo": self._xml._texto_local(alvo, "nProt"),
            "mensagem": motivo or "Manifestação processada pelo Ambiente Nacional.",
            "xml_envio": assinado,
            "xml_retorno": etree.tostring(resposta, encoding="unicode"),
        }

    def _endpoint(self, ambiente):
        if ambiente == "PRODUCAO" and not self.allow_production:
            raise SefazDiretaManifestacaoError(
                "Produção da manifestação direta permanece bloqueada."
            )
        try:
            endpoint = str(self.endpoints[ambiente])
        except KeyError as exc:
            raise SefazDiretaManifestacaoError(
                f"Endpoint de manifestação não configurado para {ambiente or 'o ambiente fiscal'}."
            ) from exc
        parsed = urlparse(endpoint)
        if parsed.scheme != "https" or parsed.hostname not in HOSTS_OFICIAIS_MANIFESTACAO:
            raise SefazDiretaManifestacaoError(
                "Endpoint de manifestação deve usar HTTPS em host oficial do Ambiente Nacional."
            )
        return endpoint


class SefazDiretaManifestacaoError(SefazDiretaError):
    pass
