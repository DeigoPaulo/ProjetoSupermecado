"""Adaptador SOAP direto para os web services NF-e/NFC-e da SEFAZ.

O adaptador permanece dormente enquanto não for selecionado em FISCAL_SEFAZ_ADAPTER
e exige uma segunda liberação explícita antes de abrir conexão de rede.
"""

import copy
import os
import re
import ssl
import tempfile
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPSHandler, Request, build_opener

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization.pkcs12 import (
    load_key_and_certificates,
)
from django.conf import settings
from django.utils import timezone
from lxml import etree

from ..adapters import SefazAdapterError
from ..assinaturas import assinar_xml_elemento_fiscal
from ..certificados import abrir_certificado_a1
from .capacidades import resumo_capacidades

NFE_NS = "http://www.portalfiscal.inf.br/nfe"
SOAP_NS = "http://www.w3.org/2003/05/soap-envelope"

SERVICOS_GO = {
    "HOMOLOGACAO": {
        "autorizacao": "https://homolog.sefaz.go.gov.br/nfe/services/NFeAutorizacao4",
        "consulta": "https://homolog.sefaz.go.gov.br/nfe/services/NFeConsultaProtocolo4",
        "evento": "https://homolog.sefaz.go.gov.br/nfe/services/NFeRecepcaoEvento4",
        "inutilizacao": "https://homolog.sefaz.go.gov.br/nfe/services/NFeInutilizacao4",
        "status": "https://homolog.sefaz.go.gov.br/nfe/services/NFeStatusServico4",
        "cadastro": "https://homolog.sefaz.go.gov.br/nfe/services/CadConsultaCadastro4",
    },
    "PRODUCAO": {
        "autorizacao": "https://nfe.sefaz.go.gov.br/nfe/services/NFeAutorizacao4",
        "consulta": "https://nfe.sefaz.go.gov.br/nfe/services/NFeConsultaProtocolo4",
        "evento": "https://nfe.sefaz.go.gov.br/nfe/services/NFeRecepcaoEvento4",
        "inutilizacao": "https://nfe.sefaz.go.gov.br/nfe/services/NFeInutilizacao4",
        "status": "https://nfe.sefaz.go.gov.br/nfe/services/NFeStatusServico4",
        "cadastro": "https://nfe.sefaz.go.gov.br/nfe/services/CadConsultaCadastro4",
    },
}

WSDL_NS = {
    "autorizacao": "http://www.portalfiscal.inf.br/nfe/wsdl/NFeAutorizacao4",
    "consulta": "http://www.portalfiscal.inf.br/nfe/wsdl/NFeConsultaProtocolo4",
    "evento": "http://www.portalfiscal.inf.br/nfe/wsdl/NFeRecepcaoEvento4",
    "inutilizacao": "http://www.portalfiscal.inf.br/nfe/wsdl/NFeInutilizacao4",
    "status": "http://www.portalfiscal.inf.br/nfe/wsdl/NFeStatusServico4",
    "cadastro": "http://www.portalfiscal.inf.br/nfe/wsdl/CadConsultaCadastro4",
}

SOAP_ACTION = {
    "autorizacao": f"{WSDL_NS['autorizacao']}/nfeAutorizacaoLote",
    "consulta": f"{WSDL_NS['consulta']}/nfeConsultaNF",
    "evento": f"{WSDL_NS['evento']}/nfeRecepcaoEvento",
    "inutilizacao": f"{WSDL_NS['inutilizacao']}/nfeInutilizacaoNF",
    "status": f"{WSDL_NS['status']}/nfeStatusServicoNF",
    "cadastro": f"{WSDL_NS['cadastro']}/consultaCadastro",
}

HOSTS_OFICIAIS_GO = {"homolog.sefaz.go.gov.br", "nfe.sefaz.go.gov.br"}


class SefazDiretaAdapter:
    """Implementa o contrato fiscal usando SOAP 1.2 e certificado A1 local."""

    nome = "SEFAZ direta - Goiás"
    assina_xml = False
    valida_schema = False
    preserva_chave_local = True

    def __init__(self, transport=None):
        self.transport = transport
        self.network_enabled = bool(
            getattr(settings, "SEFAZ_DIRETA_NETWORK_ENABLED", False)
        )
        self.allow_production = bool(
            getattr(settings, "SEFAZ_DIRETA_ALLOW_PRODUCTION", False)
        )
        self.timeout = max(
            1, int(getattr(settings, "SEFAZ_DIRETA_TIMEOUT_SECONDS", 30))
        )
        self.endpoints = self._endpoints()

    def transmitir(self, *, documento, xml, idempotency_key, ambiente):
        del idempotency_key
        configuracao = self._configuracao(documento)
        endpoint = self._endpoint(documento, ambiente, "autorizacao")
        nfe = self._parse_xml(xml)
        if self._local_name(nfe) != "NFe":
            raise SefazDiretaError("O XML de transmissão deve possuir NFe como raiz.")
        envi = etree.Element(
            etree.QName(NFE_NS, "enviNFe"),
            nsmap={None: NFE_NS},
            versao="4.00",
        )
        etree.SubElement(envi, etree.QName(NFE_NS, "idLote")).text = (
            f"{int(documento.pk):015d}"[-15:]
        )
        etree.SubElement(envi, etree.QName(NFE_NS, "indSinc")).text = "1"
        envi.append(copy.deepcopy(nfe))
        resposta = self._enviar("autorizacao", endpoint, envi, configuracao)
        ret = self._elemento_retorno(resposta, "retEnviNFe")
        inf_prot = self._primeiro_local(ret, "infProt")
        if inf_prot is not None:
            return self._resultado_protocolo(inf_prot, nfe)
        codigo = self._texto_local(ret, "cStat")
        motivo = self._mensagem(ret)
        if codigo in {"103", "105"}:
            return {"status": "PENDENTE", "mensagem": motivo}
        return {
            "status": "REJEITADO",
            "mensagem": motivo or "Autorização rejeitada pela SEFAZ.",
        }

    def consultar(self, *, documento, chave_acesso, idempotency_key, ambiente):
        del idempotency_key
        configuracao = self._configuracao(documento)
        endpoint = self._endpoint(documento, ambiente, "consulta")
        consulta = etree.Element(
            etree.QName(NFE_NS, "consSitNFe"),
            nsmap={None: NFE_NS},
            versao="4.00",
        )
        self._sub(consulta, "tpAmb", self._tp_amb(ambiente))
        self._sub(consulta, "xServ", "CONSULTAR")
        self._sub(consulta, "chNFe", self._chave(chave_acesso))
        resposta = self._enviar("consulta", endpoint, consulta, configuracao)
        ret = self._elemento_retorno(resposta, "retConsSitNFe")
        codigo = self._texto_local(ret, "cStat")
        motivo = self._mensagem(ret)
        if codigo == "100":
            inf_prot = self._primeiro_local(ret, "infProt")
            if inf_prot is None:
                raise SefazDiretaError("Consulta autorizada sem protocolo NF-e.")
            nfe = self._parse_xml(documento.xml_conteudo)
            return self._resultado_protocolo(inf_prot, nfe)
        if codigo in {"101", "151", "155"}:
            return {
                "status": "CANCELADO",
                "chave_acesso": chave_acesso,
                "protocolo": self._texto_local(ret, "nProt"),
                "protocolo_cancelamento": self._ultimo_texto_local(
                    ret, "nProt"
                ),
                "mensagem": motivo or "Documento cancelado.",
            }
        if codigo in {"110", "301", "302"}:
            return {
                "status": "DENEGADO",
                "chave_acesso": chave_acesso,
                "protocolo": self._texto_local(ret, "nProt"),
                "mensagem": motivo or "Documento denegado.",
            }
        if codigo == "217":
            return {
                "status": "NAO_LOCALIZADO",
                "mensagem": motivo or "Documento não localizado na SEFAZ.",
            }
        return {
            "status": "PENDENTE",
            "chave_acesso": chave_acesso,
            "mensagem": motivo or "Consulta ainda sem situação definitiva.",
        }

    def cancelar(
        self,
        *,
        documento,
        chave_acesso,
        protocolo_autorizacao,
        justificativa,
        idempotency_key,
        ambiente,
    ):
        del idempotency_key
        configuracao = self._configuracao(documento)
        endpoint = self._endpoint(documento, ambiente, "evento")
        chave = self._chave(chave_acesso)
        evento_id = f"ID110111{chave}01"
        env = etree.Element(
            etree.QName(NFE_NS, "envEvento"),
            nsmap={None: NFE_NS},
            versao="1.00",
        )
        self._sub(env, "idLote", f"{int(documento.pk):015d}"[-15:])
        evento = etree.SubElement(
            env, etree.QName(NFE_NS, "evento"), versao="1.00"
        )
        inf = etree.SubElement(
            evento,
            etree.QName(NFE_NS, "infEvento"),
            Id=evento_id,
        )
        self._sub(inf, "cOrgao", chave[:2])
        self._sub(inf, "tpAmb", self._tp_amb(ambiente))
        self._sub(inf, "CNPJ", self._cnpj(documento))
        self._sub(inf, "chNFe", chave)
        self._sub(inf, "dhEvento", timezone.localtime().isoformat(timespec="seconds"))
        self._sub(inf, "tpEvento", "110111")
        self._sub(inf, "nSeqEvento", "1")
        self._sub(inf, "verEvento", "1.00")
        det = etree.SubElement(
            inf,
            etree.QName(NFE_NS, "detEvento"),
            versao="1.00",
        )
        self._sub(det, "descEvento", "Cancelamento")
        self._sub(det, "nProt", protocolo_autorizacao)
        self._sub(det, "xJust", justificativa)
        assinado = assinar_xml_elemento_fiscal(
            etree.tostring(env, encoding="unicode"),
            configuracao,
            nome_elemento="infEvento",
            prefixo_id="ID110111",
        )
        resposta = self._enviar(
            "evento", endpoint, self._parse_xml(assinado), configuracao
        )
        ret = self._elemento_retorno(resposta, "retEnvEvento")
        inf_evento = self._ultimo_local(ret, "infEvento")
        if inf_evento is None:
            inf_evento = ret
        codigo = self._texto_local(inf_evento, "cStat")
        motivo = self._mensagem(inf_evento)
        if codigo in {"135", "136", "155"}:
            return {
                "status": "CANCELADO",
                "protocolo": self._texto_local(inf_evento, "nProt"),
                "mensagem": motivo or "Cancelamento registrado.",
            }
        if codigo in {"105", "128"} and self._ultimo_local(ret, "infEvento") is None:
            return {"status": "PENDENTE", "mensagem": motivo}
        return {
            "status": "REJEITADO",
            "mensagem": motivo or "Cancelamento rejeitado pela SEFAZ.",
        }

    def inutilizar(
        self,
        *,
        inutilizacao,
        cnpj,
        tipo_documento,
        ano,
        serie,
        numero_inicial,
        numero_final,
        justificativa,
        idempotency_key,
        ambiente,
    ):
        del idempotency_key
        configuracao = self._configuracao(inutilizacao)
        endpoint = self._endpoint(inutilizacao, ambiente, "inutilizacao")
        cnpj = re.sub(r"\D", "", cnpj or "")
        modelo = "65" if str(tipo_documento).upper() == "NFCE" else "55"
        codigo_uf = self._codigo_uf(inutilizacao)
        identificador = (
            f"ID{codigo_uf}{int(ano) % 100:02d}{cnpj}{modelo}"
            f"{int(serie):03d}{int(numero_inicial):09d}{int(numero_final):09d}"
        )
        inut = etree.Element(
            etree.QName(NFE_NS, "inutNFe"),
            nsmap={None: NFE_NS},
            versao="4.00",
        )
        inf = etree.SubElement(
            inut,
            etree.QName(NFE_NS, "infInut"),
            Id=identificador,
        )
        self._sub(inf, "tpAmb", self._tp_amb(ambiente))
        self._sub(inf, "xServ", "INUTILIZAR")
        self._sub(inf, "cUF", codigo_uf)
        self._sub(inf, "ano", f"{int(ano) % 100:02d}")
        self._sub(inf, "CNPJ", cnpj)
        self._sub(inf, "mod", modelo)
        self._sub(inf, "serie", str(int(serie)))
        self._sub(inf, "nNFIni", str(int(numero_inicial)))
        self._sub(inf, "nNFFin", str(int(numero_final)))
        self._sub(inf, "xJust", justificativa)
        assinado = assinar_xml_elemento_fiscal(
            etree.tostring(inut, encoding="unicode"),
            configuracao,
            nome_elemento="infInut",
            prefixo_id="ID",
        )
        resposta = self._enviar(
            "inutilizacao", endpoint, self._parse_xml(assinado), configuracao
        )
        ret = self._elemento_retorno(resposta, "retInutNFe")
        codigo = self._texto_local(ret, "cStat")
        motivo = self._mensagem(ret)
        if codigo == "102":
            return {
                "status": "INUTILIZADA",
                "protocolo": self._texto_local(ret, "nProt"),
                "mensagem": motivo or "Numeração inutilizada.",
            }
        if codigo in {"105"}:
            return {"status": "PENDENTE", "mensagem": motivo}
        return {
            "status": "REJEITADA",
            "mensagem": motivo or "Inutilização rejeitada pela SEFAZ.",
        }

    def consultar_status_servico(self, *, documento, ambiente):
        """Consulta a disponibilidade do autorizador sem transmitir documento."""
        configuracao = self._configuracao(documento)
        endpoint = self._endpoint(documento, ambiente, "status")
        consulta = etree.Element(
            etree.QName(NFE_NS, "consStatServ"),
            nsmap={None: NFE_NS},
            versao="4.00",
        )
        self._sub(consulta, "tpAmb", self._tp_amb(ambiente))
        self._sub(consulta, "cUF", self._codigo_uf(documento))
        self._sub(consulta, "xServ", "STATUS")
        resposta = self._enviar("status", endpoint, consulta, configuracao)
        retorno = self._elemento_retorno(resposta, "retConsStatServ")
        codigo = self._texto_local(retorno, "cStat")
        motivo = self._mensagem(retorno)
        disponivel = codigo == "107"
        return {
            "status": "DISPONIVEL" if disponivel else "INDISPONIVEL",
            "disponivel": disponivel,
            "codigo": codigo,
            "mensagem": motivo or "Situação do serviço não informada pela SEFAZ.",
            "tempo_medio": self._texto_local(retorno, "tMed"),
            "observacao": self._texto_local(retorno, "xObs"),
        }
    def diagnosticar(self):
        return {
            "pronto": False,
            "provedor": self.nome,
            "ufs": sorted(self.endpoints),
            "rede_habilitada": self.network_enabled,
            "producao_habilitada": self.allow_production,
            "capacidades": resumo_capacidades(),
            "erro": (
                "Adaptador dormente: habilite a rede somente durante a homologação."
                if not self.network_enabled
                else "Diagnóstico exige filial e certificado A1."
            ),
        }

    def _enviar(self, servico, endpoint, payload, configuracao):
        if not self.network_enabled:
            raise SefazDiretaError(
                "Rede da SEFAZ direta está bloqueada. "
                "Habilite SEFAZ_DIRETA_NETWORK_ENABLED somente em homologação controlada."
            )
        envelope = self._envelope(servico, payload)
        if self.transport:
            resposta = self.transport(
                servico=servico,
                endpoint=endpoint,
                envelope=envelope,
                timeout=self.timeout,
                configuracao=configuracao,
            )
            return self._parse_xml(resposta)

        contexto = self._contexto_tls(configuracao)
        request = Request(
            endpoint,
            data=envelope,
            method="POST",
            headers={
                "Content-Type": (
                    f'application/soap+xml; charset=utf-8; '
                    f'action="{SOAP_ACTION[servico]}"'
                ),
                "Accept": "application/soap+xml, application/xml",
                "User-Agent": "Deigo-Varejo-SEFAZ-Direta/1.0",
            },
        )
        try:
            opener = build_opener(HTTPSHandler(context=contexto))
            with opener.open(request, timeout=self.timeout) as response:
                return self._parse_xml(response.read())
        except HTTPError as exc:
            corpo = exc.read()
            detalhe = self._erro_soap(corpo)
            raise SefazDiretaHTTPError(
                f"SEFAZ retornou HTTP {exc.code}: {detalhe or exc.reason}."
            ) from exc
        except (URLError, TimeoutError, OSError, ssl.SSLError) as exc:
            raise SefazDiretaConnectionError(
                "Não foi possível estabelecer conexão TLS com a SEFAZ."
            ) from exc

    def _contexto_tls(self, configuracao):
        conteudo, senha = abrir_certificado_a1(configuracao)
        try:
            chave, certificado, cadeia = load_key_and_certificates(
                conteudo,
                senha.encode("utf-8") if senha else None,
            )
        except Exception as exc:
            raise SefazDiretaError(
                "Não foi possível abrir o certificado A1 para conexão com a SEFAZ."
            ) from exc
        if chave is None or certificado is None:
            raise SefazDiretaError("Certificado A1 sem chave privada.")
        contexto = ssl.create_default_context()
        with tempfile.TemporaryDirectory(prefix="detec-sefaz-") as pasta:
            cert_path = os.path.join(pasta, "cert.pem")
            key_path = os.path.join(pasta, "key.pem")
            cert_pem = certificado.public_bytes(serialization.Encoding.PEM)
            for item in cadeia or ():
                cert_pem += item.public_bytes(serialization.Encoding.PEM)
            with open(cert_path, "wb") as arquivo:
                arquivo.write(cert_pem)
            with open(key_path, "wb") as arquivo:
                arquivo.write(
                    chave.private_bytes(
                        serialization.Encoding.PEM,
                        serialization.PrivateFormat.PKCS8,
                        serialization.NoEncryption(),
                    )
                )
            contexto.load_cert_chain(cert_path, key_path)
        return contexto

    def _endpoint(self, objeto, ambiente, servico):
        filial = getattr(objeto, "filial", None)
        uf = str(getattr(filial, "uf", "") or "").upper()
        ambiente = str(ambiente or "").upper()
        if uf not in self.endpoints:
            raise SefazDiretaError(
                f"SEFAZ direta ainda não possui endpoints homologados para {uf or 'a UF da filial'}."
            )
        if ambiente == "PRODUCAO" and not self.allow_production:
            raise SefazDiretaError(
                "Produção da SEFAZ direta permanece bloqueada."
            )
        try:
            endpoint = self.endpoints[uf][ambiente][servico]
        except KeyError as exc:
            raise SefazDiretaError(
                f"Endpoint {servico} não configurado para {uf}/{ambiente}."
            ) from exc
        parsed = urlparse(endpoint)
        if parsed.scheme != "https" or parsed.hostname not in HOSTS_OFICIAIS_GO:
            raise SefazDiretaError(
                "Endpoint da SEFAZ direta deve usar HTTPS em host oficial de Goiás."
            )
        return endpoint

    def _endpoints(self):
        endpoints = {"GO": copy.deepcopy(SERVICOS_GO)}
        extras = getattr(settings, "SEFAZ_DIRETA_ENDPOINTS", {}) or {}
        for uf, ambientes in extras.items():
            uf = str(uf).upper()
            endpoints.setdefault(uf, {})
            for ambiente, servicos in (ambientes or {}).items():
                ambiente = str(ambiente).upper()
                endpoints[uf].setdefault(ambiente, {}).update(servicos or {})
        return endpoints

    @staticmethod
    def _configuracao(objeto):
        filial = getattr(objeto, "filial", None)
        configuracao = getattr(filial, "configuracao_fiscal", None)
        if configuracao is None:
            raise SefazDiretaError("Configuração fiscal da filial não encontrada.")
        return configuracao

    @staticmethod
    def _cnpj(objeto):
        filial = getattr(objeto, "filial", None)
        empresa = getattr(filial, "empresa", None)
        cnpj = re.sub(
            r"\D",
            "",
            getattr(filial, "cnpj", "")
            or getattr(empresa, "cnpj", "")
            or "",
        )
        if len(cnpj) != 14:
            raise SefazDiretaError("CNPJ do emitente inválido.")
        return cnpj

    @staticmethod
    def _codigo_uf(objeto):
        filial = getattr(objeto, "filial", None)
        uf = str(getattr(filial, "uf", "") or "").upper()
        if uf == "GO":
            return "52"
        raise SefazDiretaError(f"Código da UF {uf or '-'} ainda não homologado.")

    @staticmethod
    def _chave(valor):
        chave = re.sub(r"\D", "", valor or "")
        if len(chave) != 44:
            raise SefazDiretaError("Chave de acesso inválida.")
        return chave

    @staticmethod
    def _tp_amb(ambiente):
        return "1" if str(ambiente).upper() == "PRODUCAO" else "2"

    def _resultado_protocolo(self, inf_prot, nfe):
        codigo = self._texto_local(inf_prot, "cStat")
        motivo = self._mensagem(inf_prot)
        if codigo == "100":
            chave = self._chave(self._texto_local(inf_prot, "chNFe"))
            protocolo = self._texto_local(inf_prot, "nProt")
            proc = etree.Element(
                etree.QName(NFE_NS, "nfeProc"),
                nsmap={None: NFE_NS},
                versao="4.00",
            )
            proc.append(copy.deepcopy(nfe))
            prot = inf_prot.getparent()
            if prot is None or self._local_name(prot) != "protNFe":
                prot = inf_prot
            proc.append(copy.deepcopy(prot))
            return {
                "status": "AUTORIZADO",
                "chave_acesso": chave,
                "protocolo": protocolo,
                "mensagem": motivo or "Uso autorizado pela SEFAZ.",
                "xml_autorizado": etree.tostring(
                    proc,
                    encoding="utf-8",
                    xml_declaration=True,
                ).decode("utf-8"),
            }
        return {
            "status": "REJEITADO",
            "mensagem": motivo or f"SEFAZ rejeitou o documento ({codigo or '-'}).",
        }

    def _envelope(self, servico, payload):
        envelope = etree.Element(
            etree.QName(SOAP_NS, "Envelope"),
            nsmap={"soap12": SOAP_NS},
        )
        body = etree.SubElement(envelope, etree.QName(SOAP_NS, "Body"))
        mensagem = etree.SubElement(
            body,
            etree.QName(WSDL_NS[servico], "nfeDadosMsg"),
        )
        mensagem.append(copy.deepcopy(payload))
        return etree.tostring(
            envelope,
            encoding="utf-8",
            xml_declaration=True,
        )

    def _elemento_retorno(self, raiz, nome):
        atual = self._primeiro_local(raiz, nome)
        if atual is not None:
            return atual
        for elemento in raiz.iter():
            texto = (elemento.text or "").strip()
            if texto.startswith("<") and nome in texto:
                interno = self._parse_xml(texto)
                atual = self._primeiro_local(interno, nome)
                if atual is not None:
                    return atual
        raise SefazDiretaError(f"Resposta SOAP sem {nome}.")

    @staticmethod
    def _parse_xml(conteudo):
        if isinstance(conteudo, etree._Element):
            return conteudo
        if isinstance(conteudo, str):
            conteudo = conteudo.encode("utf-8")
        try:
            parser = etree.XMLParser(
                resolve_entities=False,
                no_network=True,
                load_dtd=False,
                huge_tree=False,
            )
            return etree.fromstring(conteudo, parser)
        except (TypeError, etree.XMLSyntaxError) as exc:
            raise SefazDiretaError("Resposta XML inválida da SEFAZ.") from exc

    @staticmethod
    def _local_name(elemento):
        return etree.QName(elemento).localname

    def _primeiro_local(self, elemento, nome):
        if elemento is None:
            return None
        return next(
            (item for item in elemento.iter() if self._local_name(item) == nome),
            None,
        )

    def _ultimo_local(self, elemento, nome):
        itens = [
            item for item in elemento.iter() if self._local_name(item) == nome
        ]
        return itens[-1] if itens else None

    def _texto_local(self, elemento, nome):
        item = self._primeiro_local(elemento, nome)
        return (item.text or "").strip() if item is not None else ""

    def _ultimo_texto_local(self, elemento, nome):
        item = self._ultimo_local(elemento, nome)
        return (item.text or "").strip() if item is not None else ""

    def _mensagem(self, elemento):
        codigo = self._texto_local(elemento, "cStat")
        motivo = self._texto_local(elemento, "xMotivo")
        if codigo and motivo:
            return f"{codigo} - {motivo}"
        return motivo or codigo

    @staticmethod
    def _sub(parent, nome, valor):
        etree.SubElement(parent, etree.QName(NFE_NS, nome)).text = str(valor)

    def _erro_soap(self, conteudo):
        try:
            raiz = self._parse_xml(conteudo)
        except SefazDiretaError:
            return ""
        return (
            self._texto_local(raiz, "Text")
            or self._texto_local(raiz, "faultstring")
            or self._mensagem(raiz)
        )


class SefazDiretaError(SefazAdapterError):
    pass


class SefazDiretaHTTPError(SefazDiretaError):
    pass


class SefazDiretaConnectionError(SefazDiretaError):
    pass
