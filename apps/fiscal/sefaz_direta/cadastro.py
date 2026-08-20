import re

from django.conf import settings
from django.core.exceptions import ValidationError
from lxml import etree

from ..cadastro_adapters import CONTRATO_CONSULTA_CADASTRO
from .adapter import NFE_NS, SefazDiretaAdapter, SefazDiretaError


TIPOS_DOCUMENTO_CADASTRO = {"CNPJ": 14, "CPF": 11, "IE": 14}


class SefazDiretaConsultaCadastroAdapter:
    nome = "SEFAZ direta - Consulta Cadastro do Contribuinte"
    contrato = CONTRATO_CONSULTA_CADASTRO

    def __init__(self, transport=None):
        self.network_enabled = bool(
            getattr(settings, "SEFAZ_DIRETA_CADASTRO_NETWORK_ENABLED", False)
        )
        self.allow_production = bool(
            getattr(settings, "SEFAZ_DIRETA_CADASTRO_ALLOW_PRODUCTION", False)
        )
        self._xml = SefazDiretaAdapter(transport=transport)
        self._xml.network_enabled = self.network_enabled
        self._xml.allow_production = self.allow_production

    def diagnosticar(self):
        return {
            "disponivel": self.network_enabled,
            "ufs": ["GO"],
            "ambiente": "SEFAZ Goiás",
            "mensagem": (
                "Consulta cadastral liberada para homologação controlada."
                if self.network_enabled
                else "Adaptador dormente: libere a rede somente durante a homologação."
            ),
        }

    def consultar(self, *, filial, uf, tipo_documento, documento):
        uf = str(uf or "").strip().upper()
        if uf != "GO":
            raise ValidationError("A consulta cadastral direta está homologada apenas para GO.")
        tipo_documento, documento = self._documento(tipo_documento, documento)
        if not self.network_enabled:
            raise SefazDiretaConsultaCadastroError(
                "Rede da consulta cadastral está bloqueada. Habilite "
                "SEFAZ_DIRETA_CADASTRO_NETWORK_ENABLED somente em homologação controlada."
            )

        objeto = type("ObjetoFiscal", (), {"filial": filial})()
        configuracao = self._xml._configuracao(objeto)
        ambiente = str(configuracao.ambiente or "HOMOLOGACAO").upper()
        endpoint = self._xml._endpoint(objeto, ambiente, "cadastro")
        consulta = etree.Element(
            etree.QName(NFE_NS, "ConsCad"), nsmap={None: NFE_NS}, versao="2.00"
        )
        inf = etree.SubElement(consulta, etree.QName(NFE_NS, "infCons"))
        self._xml._sub(inf, "xServ", "CONS-CAD")
        self._xml._sub(inf, "UF", uf)
        self._xml._sub(inf, tipo_documento, documento)
        xml_envio = etree.tostring(
            consulta, encoding="utf-8", xml_declaration=True
        ).decode("utf-8")

        resposta = self._xml._enviar("cadastro", endpoint, consulta, configuracao)
        retorno = self._xml._elemento_retorno(resposta, "retConsCad")
        codigo = self._xml._texto_local(retorno, "cStat")
        ocorrencias = [self._ocorrencia(item) for item in self._locais(retorno, "infCad")]
        status = "SUCESSO" if codigo in {"111", "112"} else "REJEITADA"
        return {
            "contrato": self.contrato,
            "status": status,
            "codigo_status": codigo,
            "mensagem": self._xml._mensagem(retorno),
            "ocorrencias": ocorrencias,
            "xml_envio": xml_envio,
            "xml_retorno": etree.tostring(resposta, encoding="unicode"),
        }

    @staticmethod
    def _documento(tipo_documento, documento):
        tipo = str(tipo_documento or "").strip().upper()
        if tipo not in TIPOS_DOCUMENTO_CADASTRO:
            raise ValidationError("Escolha CNPJ, CPF ou inscrição estadual.")
        valor = re.sub(r"\D", "", str(documento or ""))
        if tipo in {"CNPJ", "CPF"} and len(valor) != TIPOS_DOCUMENTO_CADASTRO[tipo]:
            raise ValidationError(f"{tipo} inválido para consulta cadastral.")
        if tipo == "IE" and not 2 <= len(valor) <= 14:
            raise ValidationError("Inscrição estadual inválida para consulta cadastral.")
        return tipo, valor

    def _ocorrencia(self, item):
        endereco = self._xml._primeiro_local(item, "ender")
        return {
            "ie": self._xml._texto_local(item, "IE"),
            "cnpj": self._xml._texto_local(item, "CNPJ"),
            "cpf": self._xml._texto_local(item, "CPF"),
            "uf": self._xml._texto_local(item, "UF"),
            "situacao": self._xml._texto_local(item, "cSit"),
            "credenciado_nfe": self._xml._texto_local(item, "indCredNFe"),
            "credenciado_cte": self._xml._texto_local(item, "indCredCTe"),
            "razao_social": self._xml._texto_local(item, "xNome"),
            "regime_apuracao": self._xml._texto_local(item, "xRegApur"),
            "cnae": self._xml._texto_local(item, "CNAE"),
            "inicio_atividade": self._xml._texto_local(item, "dIniAtiv"),
            "ultima_situacao": self._xml._texto_local(item, "dUltSit"),
            "endereco": {
                "logradouro": self._xml._texto_local(endereco, "xLgr"),
                "numero": self._xml._texto_local(endereco, "nro"),
                "complemento": self._xml._texto_local(endereco, "xCpl"),
                "bairro": self._xml._texto_local(endereco, "xBairro"),
                "codigo_municipio": self._xml._texto_local(endereco, "cMun"),
                "municipio": self._xml._texto_local(endereco, "xMun"),
                "cep": self._xml._texto_local(endereco, "CEP"),
            },
        }

    def _locais(self, elemento, nome):
        return [
            item
            for item in elemento.iter()
            if self._xml._local_name(item) == nome
        ]


class SefazDiretaConsultaCadastroError(SefazDiretaError):
    pass
