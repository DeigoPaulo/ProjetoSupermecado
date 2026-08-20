import base64
import json
from types import SimpleNamespace
from urllib.error import HTTPError

from django.test import SimpleTestCase, override_settings

from .focus_sefaz_adapter import FocusNFeFiscalError, FocusNFeSefazAdapter


CHAVE = "52260812345678000199650010000000011000000010"
XML_AUTORIZADO = f"""<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">
  <NFe><infNFe Id="NFe{CHAVE}" versao="4.00"><ide><mod>65</mod></ide></infNFe></NFe>
</nfeProc>"""

XML_NFCE = """<?xml version="1.0" encoding="UTF-8"?>
<NFe xmlns="http://www.portalfiscal.inf.br/nfe">
  <infNFe Id="NFe52260812345678000199650010000000011000000010" versao="4.00">
    <ide>
      <natOp>VENDA</natOp><mod>65</mod><serie>1</serie><nNF>1</nNF>
      <dhEmi>2026-08-20T10:00:00-03:00</dhEmi><tpNF>1</tpNF>
      <idDest>1</idDest><finNFe>1</finNFe><indFinal>1</indFinal><indPres>1</indPres>
    </ide>
    <emit><CNPJ>12345678000199</CNPJ></emit>
    <det nItem="1">
      <prod>
        <cProd>1</cProd><cEAN>SEM GTIN</cEAN><xProd>Arroz</xProd>
        <NCM>10063021</NCM><CFOP>5102</CFOP><uCom>UN</uCom>
        <qCom>1.000</qCom><vUnCom>10.0000000000</vUnCom><vProd>10.00</vProd>
        <cEANTrib>SEM GTIN</cEANTrib><uTrib>UN</uTrib><qTrib>1.000</qTrib>
        <vUnTrib>10.0000000000</vUnTrib><indTot>1</indTot>
      </prod>
      <imposto>
        <ICMS><ICMSSN102><orig>0</orig><CSOSN>102</CSOSN></ICMSSN102></ICMS>
        <IPI><cEnq>999</cEnq><IPITrib><CST>50</CST><vBC>10.00</vBC><pIPI>5.0000</pIPI><vIPI>0.50</vIPI></IPITrib></IPI>
        <PIS><PISNT><CST>08</CST></PISNT></PIS>
        <COFINS><COFINSNT><CST>08</CST></COFINSNT></COFINS>
      </imposto>
    </det>
    <transp><modFrete>9</modFrete></transp>
    <pag><detPag><indPag>0</indPag><tPag>01</tPag><vPag>10.00</vPag></detPag></pag>
  </infNFe>
</NFe>"""

XML_NFE_SEM_ENDERECO = XML_NFCE.replace("<mod>65</mod>", "<mod>55</mod>").replace(
    "</emit>", "</emit><dest><CNPJ>99887766000155</CNPJ><xNome>Cliente</xNome><indIEDest>9</indIEDest></dest>"
)


class FakeResponse:
    def __init__(self, body, status=200):
        self.body = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        self.status = status
        self.headers = {}

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class FakeOpener:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def documento(tipo="NFCE", pk=7, ambiente="HOMOLOGACAO"):
    empresa = SimpleNamespace(cnpj="12.345.678/0001-99")
    filial = SimpleNamespace(cnpj="", empresa=empresa)
    return SimpleNamespace(
        pk=pk, tipo_documento=tipo, ambiente=ambiente, filial=filial
    )


@override_settings(
    FOCUS_NFE_FISCAL_BASE_URL="https://homologacao.focusnfe.com.br",
    FOCUS_NFE_FISCAL_TOKEN="token-homologacao",
    FOCUS_NFE_FISCAL_TOKENS={},
    FOCUS_NFE_FISCAL_ALLOW_PRODUCTION=False,
)
class FocusNFeSefazAdapterTests(SimpleTestCase):
    def test_transmite_nfce_e_devolve_xml_autorizado(self):
        opener = FakeOpener(
            FakeResponse(
                {
                    "status": "autorizado",
                    "chave_nfce": CHAVE,
                    "protocolo": "152260000000001",
                    "xml": XML_AUTORIZADO,
                }
            )
        )
        adapter = FocusNFeSefazAdapter(opener=opener)

        resultado = adapter.transmitir(
            documento=documento(),
            xml=XML_NFCE,
            idempotency_key="ignorada",
            ambiente="HOMOLOGACAO",
        )

        self.assertEqual(resultado["status"], "AUTORIZADO")
        self.assertEqual(resultado["chave_acesso"], CHAVE)
        self.assertEqual(resultado["xml_autorizado"], XML_AUTORIZADO)
        request, timeout = opener.requests[0]
        self.assertIn("/v2/nfce?ref=detec-nfce-7&completa=1", request.full_url)
        self.assertEqual(timeout, 30)
        self.assertEqual(
            request.headers["Authorization"],
            "Basic " + base64.b64encode(b"token-homologacao:").decode("ascii"),
        )
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["items"][0]["descricao"], "Arroz")
        self.assertEqual(payload["items"][0]["icms_situacao_tributaria"], "102")
        self.assertEqual(payload["items"][0]["ipi_situacao_tributaria"], "50")
        self.assertEqual(payload["items"][0]["ipi_codigo_enquadramento_legal"], "999")
        self.assertEqual(payload["items"][0]["ipi_valor"], "0.50")
        self.assertNotIn("codigo_barras_comercial", payload["items"][0])
        self.assertEqual(payload["formas_pagamento"][0]["forma_pagamento"], "01")

    def test_retorno_em_processamento_fica_pendente(self):
        adapter = FocusNFeSefazAdapter(
            opener=FakeOpener(
                FakeResponse(
                    {
                        "status": "processando_autorizacao",
                        "mensagem": "Em processamento",
                    }
                )
            )
        )

        resultado = adapter.transmitir(
            documento=documento(),
            xml=XML_NFCE,
            idempotency_key="ignorada",
            ambiente="HOMOLOGACAO",
        )

        self.assertEqual(resultado["status"], "PENDENTE")
        self.assertIn("processamento", resultado["mensagem"])

    def test_consulta_404_retorna_nao_localizado(self):
        erro = HTTPError(
            "https://homologacao.focusnfe.com.br/v2/nfce/detec-nfce-7",
            404,
            "Not Found",
            {},
            None,
        )
        erro.read = lambda: b'{"mensagem":"Documento nao localizado"}'
        adapter = FocusNFeSefazAdapter(opener=FakeOpener(erro))

        resultado = adapter.consultar(
            documento=documento(),
            chave_acesso=CHAVE,
            idempotency_key="consulta",
            ambiente="HOMOLOGACAO",
        )

        self.assertEqual(resultado["status"], "NAO_LOCALIZADO")

    def test_nfe_sem_endereco_estruturado_falha_antes_da_rede(self):
        opener = FakeOpener()
        adapter = FocusNFeSefazAdapter(opener=opener)

        with self.assertRaisesMessage(
            FocusNFeFiscalError, "endereço estruturado"
        ):
            adapter.transmitir(
                documento=documento(tipo="NFE"),
                xml=XML_NFE_SEM_ENDERECO,
                idempotency_key="ignorada",
                ambiente="HOMOLOGACAO",
            )

        self.assertEqual(opener.requests, [])

    @override_settings(
        FOCUS_NFE_FISCAL_BASE_URL="https://api.focusnfe.com.br",
        FOCUS_NFE_FISCAL_ALLOW_PRODUCTION=False,
    )
    def test_producao_permanece_bloqueada_sem_opt_in(self):
        adapter = FocusNFeSefazAdapter(opener=FakeOpener())

        with self.assertRaisesMessage(FocusNFeFiscalError, "Produção Focus NFe bloqueada"):
            adapter.transmitir(
                documento=documento(ambiente="PRODUCAO"),
                xml=XML_NFCE,
                idempotency_key="ignorada",
                ambiente="PRODUCAO",
            )

    @override_settings(
        FOCUS_NFE_FISCAL_BASE_URL="https://fiscal.exemplo.com.br"
    )
    def test_rejeita_host_nao_oficial(self):
        adapter = FocusNFeSefazAdapter(opener=FakeOpener())

        with self.assertRaisesMessage(FocusNFeFiscalError, "domínio oficial"):
            adapter.transmitir(
                documento=documento(),
                xml=XML_NFCE,
                idempotency_key="ignorada",
                ambiente="HOMOLOGACAO",
            )

    @override_settings(
        FOCUS_NFE_FISCAL_TOKEN="",
        FOCUS_NFE_FISCAL_TOKENS={"12345678000199": "token-da-filial"},
    )
    def test_aceita_token_especifico_por_cnpj(self):
        adapter = FocusNFeSefazAdapter(
            opener=FakeOpener(
                FakeResponse(
                    {
                        "status": "autorizado",
                        "chave_nfce": CHAVE,
                        "protocolo": "152260000000001",
                        "xml": XML_AUTORIZADO,
                    }
                )
            )
        )

        adapter.transmitir(
            documento=documento(),
            xml=XML_NFCE,
            idempotency_key="ignorada",
            ambiente="HOMOLOGACAO",
        )

        request, _ = adapter.opener.requests[0]
        esperado = "Basic " + base64.b64encode(b"token-da-filial:").decode("ascii")
        self.assertEqual(request.headers["Authorization"], esperado)
