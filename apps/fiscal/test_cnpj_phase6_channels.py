import json
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings

from apps.compras.services_xml import ler_xml_nfe
from apps.empresas.models import Empresa, Filial

from .estrategia_normalizacao_cnpj import calcular_dv_cnpj
from .chave_acesso import construir_chave_acesso
from .dfe_adapters import normalizar_lote_dfe
from .focus_dfe_adapter import FocusNFeDFeAdapter
from .focus_sefaz_adapter import FocusNFeSefazAdapter
from .sefaz_direta.adapter import SefazDiretaAdapter
from .sefaz_direta.cadastro import SefazDiretaConsultaCadastroAdapter
from .sefaz_direta.dfe import SefazDiretaDFeAdapter
from .services_dfe import (
    consultar_distribuicao_dfe,
    registrar_evento_dfe_recebido,
    registrar_resumo_dfe_recebido,
)


def _cnpj(base):
    return base + calcular_dv_cnpj(base)


def _mascarar(valor):
    return f"{valor[:2]}.{valor[2:5]}.{valor[5:8]}/{valor[8:12]}-{valor[12:]}"


class CompatibilidadeCnpjFase6Tests(SimpleTestCase):
    def setUp(self):
        self.cnpj = _cnpj("12ABC34501DE")
        empresa = SimpleNamespace(cnpj=self.cnpj)
        filial = SimpleNamespace(cnpj="", empresa=empresa)
        self.objeto = SimpleNamespace(filial=filial)

    @override_settings(
        FOCUS_NFE_FISCAL_TOKEN="",
        FOCUS_NFE_FISCAL_TOKENS={},
        FOCUS_NFE_FISCAL_BASE_URL="https://homologacao.focusnfe.com.br",
    )
    def test_focus_seleciona_token_e_inutilizacao_sem_descartar_letras(self):
        adapter = FocusNFeSefazAdapter()
        with self.settings(FOCUS_NFE_FISCAL_TOKENS={_mascarar(self.cnpj).lower(): "token-alfa"}):
            self.assertEqual(adapter._token(self.objeto), "token-alfa")

        capturado = {}
        adapter._validar_ambiente = lambda _ambiente: None
        adapter._token = lambda *_args, **_kwargs: "token-alfa"
        adapter._json = lambda _path, **kwargs: capturado.update(kwargs) or {
            "status": "inutilizado", "protocolo": "123"
        }
        adapter.inutilizar(
            inutilizacao=self.objeto,
            cnpj=_mascarar(self.cnpj).lower(),
            tipo_documento="NFCE",
            ano=26,
            serie=1,
            numero_inicial=1,
            numero_final=1,
            justificativa="Falha técnica devidamente registrada",
            idempotency_key="fase6-focus-1",
            ambiente="HOMOLOGACAO",
        )
        self.assertEqual(capturado["payload"]["cnpj"], self.cnpj)

    @override_settings(
        FOCUS_NFE_DFE_TOKEN="",
        FOCUS_NFE_DFE_TOKENS={},
        FOCUS_NFE_DFE_FETCH_XML=False,
        FOCUS_NFE_DFE_BASE_URL="https://homologacao.focusnfe.com.br",
    )
    def test_focus_dfe_preserva_cnpj_na_consulta_e_no_retorno(self):
        adapter = FocusNFeDFeAdapter()
        documento = {
            "chave_nfe": "52260812345678000123550010000001231000001234",
            "versao": 1,
            "cnpj_emitente": _mascarar(self.cnpj).lower(),
        }
        capturado = {}

        def resposta(caminho, *, token):
            capturado.update(caminho=caminho, token=token)
            return [documento], {"X-Max-Version": "1"}

        adapter._request_json = resposta
        with self.settings(FOCUS_NFE_DFE_TOKENS={self.cnpj: "token-dfe-alfa"}):
            lote = adapter.consultar(cnpj=_mascarar(self.cnpj).lower())

        query = parse_qs(urlparse(capturado["caminho"]).query)
        self.assertEqual(query["cnpj"], [self.cnpj])
        self.assertEqual(capturado["token"], "token-dfe-alfa")
        self.assertEqual(lote["documentos"][0]["destinatario_cnpj"], self.cnpj)
        self.assertEqual(lote["documentos"][0]["emitente_cnpj"], self.cnpj)

    def test_sefaz_direta_preserva_cnpj_emissao_dfe_eventos_e_cadastro(self):
        self.assertEqual(SefazDiretaAdapter._cnpj(self.objeto), self.cnpj)
        self.assertEqual(SefazDiretaDFeAdapter._cnpj(_mascarar(self.cnpj).lower()), self.cnpj)
        self.assertEqual(
            SefazDiretaConsultaCadastroAdapter._documento(
                "CNPJ", _mascarar(self.cnpj).lower()
            ),
            ("CNPJ", self.cnpj),
        )

    def test_chaves_fiscais_continuam_no_caminho_numerico_separado(self):
        chave = "52260812345678000123550010000001231000001234"
        self.assertEqual(FocusNFeDFeAdapter._digitos(chave), chave)
        self.assertEqual(SefazDiretaDFeAdapter._digitos(chave), chave)
        self.assertEqual(json.loads(json.dumps({"chave": chave}))["chave"], chave)

    def test_chave_alfanumerica_e_preservada_nos_retornos_dos_dois_canais(self):
        chave = construir_chave_acesso(
            codigo_uf="52",
            aamm="2609",
            cnpj_emitente=self.cnpj,
            modelo="65",
            serie="001",
            numero="000000123",
            tipo_emissao="1",
            codigo_numerico="12345678",
        )
        xml = (
            '<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">'
            f'<NFe><infNFe Id="NFe{chave}" versao="4.00"/></NFe></nfeProc>'
        )
        focus = FocusNFeSefazAdapter()
        retorno = focus._normalizar(
            {"status": "autorizado", "chave_nfce": chave.lower(), "protocolo": "123", "xml": xml},
            token="token-ficticio",
            consulta=False,
        )

        self.assertEqual(retorno["chave_acesso"], chave)
        self.assertEqual(FocusNFeDFeAdapter()._normalizar_documento(
            {"chave_nfe": chave.lower(), "versao": 1}, cnpj=self.cnpj
        )["chave_acesso"], chave)
        self.assertEqual(SefazDiretaAdapter._chave(chave.lower()), chave)
        self.assertEqual(SefazDiretaDFeAdapter._chave(chave.lower()), chave)
        self.assertEqual(SefazDiretaDFeAdapter._numero_pela_chave(chave), "123")
        lote = normalizar_lote_dfe({
            "contrato": "fiscal_dfe_distribution_v1",
            "documentos": [{
                "tipo_documento": "EVENTO",
                "nsu": "1",
                "chave_acesso": chave.lower(),
                "xml": "<procEventoNFe/>",
            }],
            "ultimo_nsu": "1",
            "max_nsu": "1",
        })
        self.assertEqual(lote["documentos"][0]["chave_acesso"], chave)

    def test_parser_xml_recebido_preserva_cnpj_e_chave_alfanumericos(self):
        chave = construir_chave_acesso(
            codigo_uf="52", aamm="2609", cnpj_emitente=self.cnpj,
            modelo="55", serie="001", numero="000000123",
            tipo_emissao="1", codigo_numerico="12345678",
        )
        xml = f'''<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe">
          <NFe><infNFe Id="NFe{chave}"><ide><nNF>123</nNF><dhEmi>2026-09-17T10:00:00-03:00</dhEmi></ide>
          <emit><CNPJ>{self.cnpj.lower()}</CNPJ><xNome>Fornecedor Alfa</xNome></emit>
          <dest><CNPJ>{self.cnpj.lower()}</CNPJ></dest>
          <det nItem="1"><prod><cProd>1</cProd><xProd>Produto</xProd><qCom>1</qCom><vProd>10.00</vProd></prod></det>
          <total><ICMSTot><vNF>10.00</vNF></ICMSTot></total></infNFe></NFe>
          <protNFe><infProt><chNFe>{chave.lower()}</chNFe><cStat>100</cStat></infProt></protNFe>
        </nfeProc>'''.encode()

        dados = ler_xml_nfe(xml)

        self.assertEqual(dados["chave"], chave)
        self.assertEqual(dados["emitente_cnpj"], self.cnpj)
        self.assertEqual(dados["destinatario_cnpj"], self.cnpj)


class FakeDFeAlfanumericoAdapter:
    cnpj_recebido = ""

    def consultar(self, *, cnpj, ultimo_nsu, limite):
        type(self).cnpj_recebido = cnpj
        return {
            "contrato": "fiscal_dfe_distribution_v1",
            "documentos": [],
            "ultimo_nsu": "1",
            "max_nsu": "1",
        }


class PersistenciaDFeCnpjAlfanumericoTests(TestCase):
    def setUp(self):
        self.cnpj = _cnpj("12ABC34501DE")
        self.usuario = get_user_model().objects.create_superuser(
            "dfe_alfa", "dfe-alfa@example.com", "teste"
        )
        self.empresa = Empresa.objects.create(
            razao_social="Mercado Alfa", nome_fantasia="Mercado Alfa", cnpj=self.cnpj.lower()
        )
        self.filial = Filial.objects.create(
            empresa=self.empresa, nome="Matriz Alfa", cnpj=_mascarar(self.cnpj).lower()
        )
        self.chave = construir_chave_acesso(
            codigo_uf="52", aamm="2609", cnpj_emitente=self.cnpj,
            modelo="55", serie="001", numero="000000123",
            tipo_emissao="1", codigo_numerico="12345678",
        )

    def test_resumo_e_evento_preservam_identidades_canonicas(self):
        resumo, _ = registrar_resumo_dfe_recebido({
            "chave_acesso": self.chave.lower(),
            "nsu": "10",
            "destinatario_cnpj": _mascarar(self.cnpj).lower(),
            "emitente_cnpj": self.cnpj.lower(),
        }, filial=self.filial, usuario=self.usuario)
        evento, _ = registrar_evento_dfe_recebido({
            "chave_acesso": self.chave.lower(),
            "nsu": "11",
            "destinatario_cnpj": self.cnpj.lower(),
            "xml": "<procEventoNFe/>",
        }, filial=self.filial, usuario=self.usuario)

        self.assertEqual(resumo.chave_acesso, self.chave)
        self.assertEqual(resumo.emitente_cnpj, self.cnpj)
        self.assertEqual(evento.chave_acesso, self.chave)

    @override_settings(
        FISCAL_DFE_ADAPTER="apps.fiscal.test_cnpj_phase6_channels.FakeDFeAlfanumericoAdapter"
    )
    def test_consulta_entrega_cnpj_canonico_ao_adaptador(self):
        FakeDFeAlfanumericoAdapter.cnpj_recebido = ""

        consultar_distribuicao_dfe(filial=self.filial, usuario=self.usuario)

        self.assertEqual(FakeDFeAlfanumericoAdapter.cnpj_recebido, self.cnpj)
