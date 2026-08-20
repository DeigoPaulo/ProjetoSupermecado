from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from lxml import etree

from ..assinaturas import assinar_xml_elemento_fiscal
from ..cce_adapters import CONTRATO_CARTA_CORRECAO
from .adapter import NFE_NS, SefazDiretaAdapter, SefazDiretaError


CONDICAO_USO_CCE = (
    "A Carta de Correção é disciplinada pelo § 1º-A do art. 7º do Convênio S/N, "
    "de 15 de dezembro de 1970 e pode ser utilizada para regularização de erro "
    "ocorrido na emissão de documento fiscal, desde que o erro não esteja "
    "relacionado com: I - as variáveis que determinam o valor do imposto tais "
    "como: base de cálculo, alíquota, diferença de preço, quantidade, valor da "
    "operação ou da prestação; II - a correção de dados cadastrais que implique "
    "mudança do remetente ou do destinatário; III - a data de emissão ou de saída."
)


class SefazDiretaCartaCorrecaoAdapter:
    nome = "SEFAZ direta - Carta de Correção Eletrônica"
    contrato = CONTRATO_CARTA_CORRECAO

    def __init__(self, transport=None):
        self.network_enabled = bool(
            getattr(settings, "SEFAZ_DIRETA_CCE_NETWORK_ENABLED", False)
        )
        self.allow_production = bool(
            getattr(settings, "SEFAZ_DIRETA_CCE_ALLOW_PRODUCTION", False)
        )
        self._xml = SefazDiretaAdapter(transport=transport)
        self._xml.network_enabled = self.network_enabled
        self._xml.allow_production = self.allow_production

    def diagnosticar(self):
        return {
            "disponivel": self.network_enabled,
            "ambiente": "SEFAZ Goiás",
            "mensagem": (
                "Rede liberada para homologação controlada."
                if self.network_enabled
                else "Adaptador dormente: libere a rede somente durante a homologação."
            ),
        }

    def corrigir(self, *, documento, sequencia, correcao, idempotency_key=""):
        del idempotency_key
        if not 1 <= int(sequencia) <= 20:
            raise ValidationError("A sequência da CC-e deve estar entre 1 e 20.")
        correcao = str(correcao or "").strip()
        if not 15 <= len(correcao) <= 1000:
            raise ValidationError("A correção deve ter entre 15 e 1.000 caracteres.")

        if not self.network_enabled:
            raise SefazDiretaCartaCorrecaoError(
                "Rede da CC-e direta está bloqueada. Habilite "
                "SEFAZ_DIRETA_CCE_NETWORK_ENABLED somente em homologação controlada."
            )

        configuracao = self._xml._configuracao(documento)
        ambiente = str(configuracao.ambiente or "").upper()
        endpoint = self._xml._endpoint(documento, ambiente, "evento")
        chave = self._xml._chave(documento.chave_acesso)
        sequencia_texto = f"{int(sequencia):02d}"

        env = etree.Element(
            etree.QName(NFE_NS, "envEvento"), nsmap={None: NFE_NS}, versao="1.00"
        )
        self._xml._sub(env, "idLote", f"{int(documento.pk):013d}{sequencia_texto}"[-15:])
        evento = etree.SubElement(env, etree.QName(NFE_NS, "evento"), versao="1.00")
        inf = etree.SubElement(
            evento,
            etree.QName(NFE_NS, "infEvento"),
            Id=f"ID110110{chave}{sequencia_texto}",
        )
        self._xml._sub(inf, "cOrgao", self._xml._codigo_uf(documento))
        self._xml._sub(inf, "tpAmb", self._xml._tp_amb(ambiente))
        self._xml._sub(inf, "CNPJ", self._xml._cnpj(documento))
        self._xml._sub(inf, "chNFe", chave)
        self._xml._sub(inf, "dhEvento", timezone.localtime().isoformat(timespec="seconds"))
        self._xml._sub(inf, "tpEvento", "110110")
        self._xml._sub(inf, "nSeqEvento", str(int(sequencia)))
        self._xml._sub(inf, "verEvento", "1.00")
        det = etree.SubElement(inf, etree.QName(NFE_NS, "detEvento"), versao="1.00")
        self._xml._sub(det, "descEvento", "Carta de Correcao")
        self._xml._sub(det, "xCorrecao", correcao)
        self._xml._sub(det, "xCondUso", CONDICAO_USO_CCE)

        assinado = assinar_xml_elemento_fiscal(
            etree.tostring(env, encoding="unicode"),
            configuracao,
            nome_elemento="infEvento",
            prefixo_id="ID110110",
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
            "mensagem": motivo or "Carta de Correção processada pela SEFAZ.",
            "xml_envio": assinado,
            "xml_retorno": etree.tostring(resposta, encoding="unicode"),
        }


class SefazDiretaCartaCorrecaoError(SefazDiretaError):
    pass
