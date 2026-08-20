"""Distribuição direta de DF-e pelo Ambiente Nacional da NF-e.

A implementação consome somente a consulta sequencial distNSU. Ela não manifesta
uma NF-e e não cria movimentações no ERP.
"""

import base64
import copy
import gzip
import io
import re
import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPSHandler, Request, build_opener

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from lxml import etree

from ..dfe_adapters import CONTRATO_DISTRIBUICAO_DFE
from .adapter import NFE_NS, SOAP_NS, SefazDiretaAdapter, SefazDiretaError

WSDL_DFE_NS = "http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe"
SOAP_ACTION_DFE = f"{WSDL_DFE_NS}/nfeDistDFeInteresse"
ENDPOINTS_DFE = {
    "HOMOLOGACAO": "https://hom1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx",
    "PRODUCAO": "https://www1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx",
}
HOSTS_DFE_OFICIAIS = {"hom1.nfe.fazenda.gov.br", "www1.nfe.fazenda.gov.br"}
CODIGOS_UF = {
    "AC": "12", "AL": "27", "AP": "16", "AM": "13", "BA": "29", "CE": "23",
    "DF": "53", "ES": "32", "GO": "52", "MA": "21", "MT": "51", "MS": "50",
    "MG": "31", "PA": "15", "PB": "25", "PR": "41", "PE": "26", "PI": "22",
    "RJ": "33", "RN": "24", "RS": "43", "RO": "11", "RR": "14", "SC": "42",
    "SP": "35", "SE": "28", "TO": "17",
}


class SefazDiretaDFeAdapter:
    """Implementa fiscal_dfe_distribution_v1 sem provedor comercial."""

    nome = "SEFAZ direta - Distribuição DF-e"

    def __init__(self, transport=None, configuracao_resolver=None):
        self.transport = transport
        self.configuracao_resolver = configuracao_resolver or self._resolver_configuracao
        self.network_enabled = bool(
            getattr(settings, "SEFAZ_DIRETA_DFE_NETWORK_ENABLED", False)
        )
        self.allow_production = bool(
            getattr(settings, "SEFAZ_DIRETA_DFE_ALLOW_PRODUCTION", False)
        )
        self.timeout = max(
            1, int(getattr(settings, "SEFAZ_DIRETA_DFE_TIMEOUT_SECONDS", 30))
        )
        self.max_xml_bytes = max(
            1024, int(getattr(settings, "SEFAZ_DIRETA_DFE_MAX_XML_BYTES", 5 * 1024 * 1024))
        )
        self.endpoints = dict(ENDPOINTS_DFE)
        self.endpoints.update(getattr(settings, "SEFAZ_DIRETA_DFE_ENDPOINTS", {}) or {})
        self._xml = SefazDiretaAdapter(transport=transport)

    def diagnosticar(self):
        ambiente = "por filial"
        disponivel = self.network_enabled
        if not self.network_enabled:
            mensagem = "Distribuição DF-e direta dormente; libere a rede somente em homologação controlada."
        elif not self.allow_production:
            mensagem = "Distribuição DF-e direta disponível; produção permanece bloqueada."
        else:
            mensagem = "Distribuição DF-e direta disponível conforme o ambiente de cada filial."
        return {
            "disponivel": disponivel,
            "mensagem": mensagem,
            "ambiente": ambiente.lower(),
        }

    def consultar(self, *, cnpj, ultimo_nsu="", limite=50):
        cnpj = self._cnpj(cnpj)
        configuracao = self.configuracao_resolver(cnpj)
        ambiente = str(getattr(configuracao, "ambiente", "HOMOLOGACAO") or "HOMOLOGACAO").upper()
        endpoint = self._endpoint(ambiente)
        uf = str(getattr(getattr(configuracao, "filial", None), "uf", "") or "").upper()
        codigo_uf = CODIGOS_UF.get(uf)
        if not codigo_uf:
            raise SefazDiretaDFeError(f"UF {uf or '-'} inválida para consulta DF-e.")

        cursor = self._cursor(ultimo_nsu)
        consulta = etree.Element(
            etree.QName(NFE_NS, "distDFeInt"),
            nsmap={None: NFE_NS},
            versao="1.01",
        )
        self._sub(consulta, "tpAmb", "1" if ambiente == "PRODUCAO" else "2")
        self._sub(consulta, "cUFAutor", codigo_uf)
        self._sub(consulta, "CNPJ", cnpj)
        dist_nsu = etree.SubElement(consulta, etree.QName(NFE_NS, "distNSU"))
        self._sub(dist_nsu, "ultNSU", cursor.zfill(15))

        resposta = self._enviar(endpoint, consulta, configuracao)
        retorno = self._xml._elemento_retorno(resposta, "retDistDFeInt")
        codigo = self._xml._texto_local(retorno, "cStat")
        motivo = self._xml._mensagem(retorno)
        ultimo_retorno = self._cursor(self._xml._texto_local(retorno, "ultNSU") or cursor)
        max_nsu = self._cursor(self._xml._texto_local(retorno, "maxNSU") or ultimo_retorno)

        if codigo not in {"137", "138", "656"}:
            raise SefazDiretaDFeError(
                motivo or f"Ambiente Nacional rejeitou a consulta DF-e ({codigo or '-'})."
            )

        limite = max(1, min(int(limite), 50))
        documentos = []
        for doc_zip in self._elementos_locais(retorno, "docZip"):
            if len(documentos) >= limite:
                break
            documento = self._descompactar_doc_zip(doc_zip, cnpj=cnpj)
            documentos.append(documento)

        if documentos and len(documentos) >= limite:
            ultimo_processado = documentos[-1]["nsu"]
        else:
            ultimo_processado = ultimo_retorno

        sem_pendencias = codigo in {"137", "656"} or (
            ultimo_processado and max_nsu and int(ultimo_processado) >= int(max_nsu)
        )
        aguardar_segundos = 3600 if sem_pendencias else 0
        return {
            "contrato": CONTRATO_DISTRIBUICAO_DFE,
            "documentos": documentos,
            "ultimo_nsu": ultimo_processado,
            "max_nsu": max_nsu,
            "aguardar_segundos": aguardar_segundos,
            "mensagem": (
                f"Ambiente Nacional: {motivo or codigo}; "
                f"{len(documentos)} documento(s) fiscal(is) processado(s)."
            ),
        }

    def _descompactar_doc_zip(self, elemento, *, cnpj):
        nsu = self._cursor(elemento.get("NSU") or elemento.get("nsu") or "")
        schema = str(elemento.get("schema") or "")[:80]
        try:
            comprimido = base64.b64decode((elemento.text or "").strip(), validate=True)
            with gzip.GzipFile(fileobj=io.BytesIO(comprimido), mode="rb") as arquivo:
                conteudo = arquivo.read(self.max_xml_bytes + 1)
        except (ValueError, OSError, EOFError) as exc:
            raise SefazDiretaDFeError("Documento compactado inválido no lote DF-e.") from exc
        if len(conteudo) > self.max_xml_bytes:
            raise SefazDiretaDFeError("Documento DF-e excede o limite seguro de descompactação.")

        raiz = self._xml._parse_xml(conteudo)
        tipo = self._xml._local_name(raiz)
        if tipo in {"nfeProc", "NFe"}:
            chave = self._chave_do_xml(raiz)
            return {
                "nsu": nsu,
                "chave_acesso": chave,
                "destinatario_cnpj": cnpj,
                "schema": schema or "procNFe",
                "xml": conteudo.decode("utf-8-sig"),
            }
        if tipo == "resNFe":
            return {
                "nsu": nsu,
                "chave_acesso": self._chave(self._xml._texto_local(raiz, "chNFe")),
                "destinatario_cnpj": cnpj,
                "emitente_cnpj": self._digitos(self._xml._texto_local(raiz, "CNPJ")),
                "emitente_nome": self._xml._texto_local(raiz, "xNome"),
                "numero_documento": self._numero_pela_chave(
                    self._xml._texto_local(raiz, "chNFe")
                ),
                "data_emissao": self._xml._texto_local(raiz, "dhEmi")[:10],
                "valor_total": self._xml._texto_local(raiz, "vNF"),
                "schema": schema or "resNFe",
            }
        if tipo in {"procEventoNFe", "resEvento"}:
            chave = self._xml._texto_local(raiz, "chNFe")
            sequencia = self._xml._texto_local(raiz, "nSeqEvento") or "1"
            return {
                "tipo_documento": "EVENTO",
                "nsu": nsu,
                "chave_acesso": self._chave(chave),
                "destinatario_cnpj": cnpj,
                "schema": schema or tipo,
                "tipo_evento": self._xml._texto_local(raiz, "tpEvento"),
                "sequencia": int(sequencia) if sequencia.isdigit() else 1,
                "data_evento": (
                    self._xml._texto_local(raiz, "dhRegEvento")
                    or self._xml._texto_local(raiz, "dhEvento")
                ),
                "descricao": (
                    self._xml._texto_local(raiz, "xEvento")
                    or self._xml._texto_local(raiz, "xMotivo")
                ),
                "xml": conteudo.decode("utf-8-sig"),
            }
        raise SefazDiretaDFeError(
            f"Schema DF-e {schema or tipo or '-'} ainda não é reconhecido pelo adaptador."
        )

    def _enviar(self, endpoint, payload, configuracao):
        if not self.network_enabled:
            raise SefazDiretaDFeError(
                "Rede da distribuição DF-e direta está bloqueada. "
                "Habilite SEFAZ_DIRETA_DFE_NETWORK_ENABLED apenas na homologação."
            )
        envelope = self._envelope(payload)
        if self.transport:
            resposta = self.transport(
                servico="distribuicao_dfe",
                endpoint=endpoint,
                envelope=envelope,
                timeout=self.timeout,
                configuracao=configuracao,
            )
            return self._xml._parse_xml(resposta)

        contexto = self._xml._contexto_tls(configuracao)
        requisicao = Request(
            endpoint,
            data=envelope,
            method="POST",
            headers={
                "Content-Type": (
                    f'application/soap+xml; charset=utf-8; action="{SOAP_ACTION_DFE}"'
                ),
                "Accept": "application/soap+xml, application/xml",
                "User-Agent": "Deigo-Varejo-SEFAZ-DFe/1.0",
            },
        )
        try:
            opener = build_opener(HTTPSHandler(context=contexto))
            with opener.open(requisicao, timeout=self.timeout) as resposta:
                return self._xml._parse_xml(resposta.read())
        except HTTPError as exc:
            detalhe = self._xml._erro_soap(exc.read())
            raise SefazDiretaDFeHTTPError(
                f"Ambiente Nacional retornou HTTP {exc.code}: {detalhe or exc.reason}."
            ) from exc
        except (URLError, TimeoutError, OSError, ssl.SSLError) as exc:
            raise SefazDiretaDFeConnectionError(
                "Não foi possível estabelecer conexão TLS com o Ambiente Nacional."
            ) from exc

    def _endpoint(self, ambiente):
        if ambiente not in self.endpoints:
            raise SefazDiretaDFeError(f"Ambiente DF-e {ambiente} inválido.")
        if ambiente == "PRODUCAO" and not self.allow_production:
            raise SefazDiretaDFeError("Produção da distribuição DF-e direta permanece bloqueada.")
        endpoint = str(self.endpoints[ambiente])
        parsed = urlparse(endpoint)
        if parsed.scheme != "https" or parsed.hostname not in HOSTS_DFE_OFICIAIS:
            raise SefazDiretaDFeError(
                "Endpoint DF-e deve usar HTTPS em host oficial do Ambiente Nacional."
            )
        return endpoint

    def _envelope(self, payload):
        envelope = etree.Element(etree.QName(SOAP_NS, "Envelope"), nsmap={"soap12": SOAP_NS})
        body = etree.SubElement(envelope, etree.QName(SOAP_NS, "Body"))
        mensagem = etree.SubElement(body, etree.QName(WSDL_DFE_NS, "nfeDadosMsg"))
        mensagem.append(copy.deepcopy(payload))
        return etree.tostring(envelope, encoding="utf-8", xml_declaration=True)

    @staticmethod
    def _resolver_configuracao(cnpj):
        from ..models import ConfiguracaoFiscal

        candidatas = []
        for configuracao in ConfiguracaoFiscal.objects.filter(
            ativo=True, filial__is_active=True, filial__empresa__is_active=True
        ).select_related("filial", "filial__empresa"):
            cadastrado = configuracao.filial.cnpj or configuracao.filial.empresa.cnpj
            if SefazDiretaDFeAdapter._digitos(cadastrado) == cnpj:
                candidatas.append(configuracao)
        if not candidatas:
            raise ImproperlyConfigured(
                "Não há configuração fiscal ativa com certificado para o CNPJ consultado."
            )
        if len(candidatas) > 1:
            raise ImproperlyConfigured(
                "Há mais de uma configuração fiscal para o CNPJ consultado."
            )
        configuracao = candidatas[0]
        if not configuracao.certificado_configurado:
            raise ImproperlyConfigured("Configure o certificado A1 da filial antes de consultar DF-e.")
        return configuracao

    def _chave_do_xml(self, raiz):
        inf_nfe = self._xml._primeiro_local(raiz, "infNFe")
        identificador = inf_nfe.get("Id", "") if inf_nfe is not None else ""
        return self._chave(identificador[3:] if identificador.startswith("NFe") else identificador)

    @staticmethod
    def _numero_pela_chave(chave):
        chave = SefazDiretaDFeAdapter._digitos(chave)
        return str(int(chave[25:34])) if len(chave) == 44 else ""

    @staticmethod
    def _elementos_locais(raiz, nome):
        return [item for item in raiz.iter() if etree.QName(item).localname == nome]

    @staticmethod
    def _sub(parent, nome, valor):
        etree.SubElement(parent, etree.QName(NFE_NS, nome)).text = str(valor)

    @staticmethod
    def _digitos(valor):
        return re.sub(r"\D", "", str(valor or ""))

    @classmethod
    def _cnpj(cls, valor):
        cnpj = cls._digitos(valor)
        if len(cnpj) != 14:
            raise SefazDiretaDFeError("O CNPJ da consulta DF-e deve possuir 14 dígitos.")
        return cnpj

    @staticmethod
    def _cursor(valor):
        cursor = str(valor or "0").strip()
        if not cursor.isdigit() or len(cursor) > 15:
            raise SefazDiretaDFeError("O cursor NSU deve ser numérico e ter até 15 dígitos.")
        return str(int(cursor))

    @classmethod
    def _chave(cls, valor):
        chave = cls._digitos(valor)
        if len(chave) != 44:
            raise SefazDiretaDFeError("A chave de acesso recebida no DF-e é inválida.")
        return chave


class SefazDiretaDFeError(SefazDiretaError):
    pass


class SefazDiretaDFeHTTPError(SefazDiretaDFeError):
    pass


class SefazDiretaDFeConnectionError(SefazDiretaDFeError):
    pass