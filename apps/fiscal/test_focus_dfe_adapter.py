import base64
import json
from urllib.error import HTTPError

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings

from .dfe_adapters import diagnostico_adaptador_dfe
from .focus_dfe_adapter import FocusNFeDFeAdapter, FocusNFeDFeHTTPError


class _RespostaHTTP:
    def __init__(self, dados, headers=None):
        self._dados = dados if isinstance(dados, bytes) else json.dumps(dados).encode("utf-8")
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return self._dados


class _OpenerFila:
    def __init__(self, *respostas):
        self.respostas = list(respostas)
        self.requisicoes = []

    def __call__(self, requisicao, timeout):
        self.requisicoes.append((requisicao, timeout))
        resposta = self.respostas.pop(0)
        if isinstance(resposta, Exception):
            raise resposta
        return resposta


class FocusNFeDFeAdapterTests(SimpleTestCase):
    documento_base = {
        "chave_nfe": "52260812345678000123550010000001231000001234",
        "versao": 42,
        "cnpj_emitente": "12.345.678/0001-23",
        "nome_emitente": "Fornecedor de Teste",
        "numero": "123",
        "data_emissao": "2026-08-18T10:30:00-03:00",
        "valor_total": "149.90",
    }

    @override_settings(
        FOCUS_NFE_DFE_TOKEN="token-de-homologacao",
        FOCUS_NFE_DFE_TOKENS={},
        FOCUS_NFE_DFE_FETCH_XML=False,
        FOCUS_NFE_DFE_BASE_URL="https://homologacao.focusnfe.com.br",
    )
    def test_consulta_normaliza_documento_cursor_e_autenticacao(self):
        opener = _OpenerFila(
            _RespostaHTTP(
                [self.documento_base],
                {"X-Max-Version": "45", "X-Total-Count": "1"},
            )
        )
        adaptador = FocusNFeDFeAdapter(opener=opener)

        lote = adaptador.consultar(
            cnpj="12.345.678/0001-99", ultimo_nsu="40", limite=50
        )

        self.assertEqual(lote["contrato"], "fiscal_dfe_distribution_v1")
        self.assertEqual(lote["ultimo_nsu"], "42")
        self.assertEqual(lote["max_nsu"], "45")
        self.assertEqual(lote["documentos"][0]["emitente_nome"], "Fornecedor de Teste")
        requisicao, timeout = opener.requisicoes[0]
        self.assertIn("cnpj=12345678000199", requisicao.full_url)
        self.assertIn("versao=40", requisicao.full_url)
        esperado = base64.b64encode(b"token-de-homologacao:").decode("ascii")
        self.assertEqual(requisicao.get_header("Authorization"), f"Basic {esperado}")
        self.assertEqual(timeout, 20)

    @override_settings(
        FOCUS_NFE_DFE_TOKEN="",
        FOCUS_NFE_DFE_TOKENS={"12345678000199": "token-da-filial"},
        FOCUS_NFE_DFE_FETCH_XML=False,
        FOCUS_NFE_DFE_BASE_URL="https://homologacao.focusnfe.com.br",
    )
    def test_token_pode_ser_configurado_por_cnpj(self):
        opener = _OpenerFila(_RespostaHTTP([], {"X-Max-Version": "8"}))
        lote = FocusNFeDFeAdapter(opener=opener).consultar(
            cnpj="12345678000199", ultimo_nsu="8", limite=10
        )
        esperado = base64.b64encode(b"token-da-filial:").decode("ascii")
        self.assertEqual(
            opener.requisicoes[0][0].get_header("Authorization"), f"Basic {esperado}"
        )
        self.assertEqual(lote["ultimo_nsu"], "8")

    @override_settings(
        FOCUS_NFE_DFE_TOKEN="token",
        FOCUS_NFE_DFE_TOKENS={},
        FOCUS_NFE_DFE_FETCH_XML=False,
        FOCUS_NFE_DFE_BASE_URL="https://homologacao.focusnfe.com.br",
    )
    def test_limite_nao_avanca_cursor_alem_dos_documentos_processados(self):
        primeiro = dict(self.documento_base, versao=41)
        segundo = dict(
            self.documento_base,
            chave_nfe="52260812345678000123550010000001241000001235",
            versao=42,
        )
        opener = _OpenerFila(
            _RespostaHTTP([primeiro, segundo], {"X-Max-Version": "42"})
        )
        lote = FocusNFeDFeAdapter(opener=opener).consultar(
            cnpj="12345678000199", ultimo_nsu="40", limite=1
        )
        self.assertEqual(len(lote["documentos"]), 1)
        self.assertEqual(lote["ultimo_nsu"], "41")
        self.assertEqual(lote["max_nsu"], "42")

    @override_settings(
        FOCUS_NFE_DFE_TOKEN="token",
        FOCUS_NFE_DFE_TOKENS={},
        FOCUS_NFE_DFE_FETCH_XML=True,
        FOCUS_NFE_DFE_BASE_URL="https://homologacao.focusnfe.com.br",
    )
    def test_xml_completo_disponivel_e_incorporado_sem_manifestacao(self):
        xml = "<nfeProc><NFe><infNFe Id='NFe52260812345678000123550010000001231000001234'/></NFe></nfeProc>"
        opener = _OpenerFila(
            _RespostaHTTP([self.documento_base], {"X-Max-Version": "42"}),
            _RespostaHTTP(xml.encode("utf-8")),
        )
        lote = FocusNFeDFeAdapter(opener=opener).consultar(
            cnpj="12345678000199", ultimo_nsu="", limite=10
        )
        self.assertEqual(lote["documentos"][0]["xml"], xml)
        self.assertTrue(opener.requisicoes[1][0].full_url.endswith(".xml"))
        self.assertTrue(all(req.method == "GET" for req, _ in opener.requisicoes))

    @override_settings(
        FOCUS_NFE_DFE_TOKEN="token",
        FOCUS_NFE_DFE_TOKENS={},
        FOCUS_NFE_DFE_FETCH_XML=True,
        FOCUS_NFE_DFE_BASE_URL="https://homologacao.focusnfe.com.br",
    )
    def test_xml_ainda_indisponivel_preserva_resumo(self):
        erro_404 = HTTPError("https://focus/nota", 404, "Not found", {}, None)
        opener = _OpenerFila(
            _RespostaHTTP([self.documento_base], {"X-Max-Version": "42"}),
            erro_404,
        )
        lote = FocusNFeDFeAdapter(opener=opener).consultar(
            cnpj="12345678000199", ultimo_nsu="", limite=10
        )
        self.assertEqual(lote["documentos"][0]["xml"], "")
        self.assertEqual(lote["documentos"][0]["schema"], "resNFe")

    @override_settings(
        FOCUS_NFE_DFE_TOKEN="token",
        FOCUS_NFE_DFE_TOKENS={},
        FOCUS_NFE_DFE_BASE_URL="https://api.focusnfe.com.br",
        FOCUS_NFE_DFE_ALLOW_PRODUCTION=False,
    )
    def test_producao_permanece_bloqueada_por_padrao(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "produção está bloqueada"):
            FocusNFeDFeAdapter(opener=_OpenerFila()).consultar(
                cnpj="12345678000199", ultimo_nsu="", limite=10
            )

    @override_settings(
        FOCUS_NFE_DFE_TOKEN="token",
        FOCUS_NFE_DFE_TOKENS={},
        FOCUS_NFE_DFE_BASE_URL="https://integracao.exemplo.com.br",
    )
    def test_host_nao_oficial_e_bloqueado_antes_de_enviar_credencial(self):
        opener = _OpenerFila()
        with self.assertRaisesMessage(ImproperlyConfigured, "ambiente oficial"):
            FocusNFeDFeAdapter(opener=opener).consultar(
                cnpj="12345678000199", ultimo_nsu="", limite=10
            )
        self.assertEqual(opener.requisicoes, [])

    @override_settings(
        FISCAL_DFE_ADAPTER="apps.fiscal.focus_dfe_adapter.FocusNFeDFeAdapter",
        FOCUS_NFE_DFE_TOKEN="",
        FOCUS_NFE_DFE_TOKENS={},
        FOCUS_NFE_DFE_BASE_URL="https://homologacao.focusnfe.com.br",
    )
    def test_diagnostico_nao_expoe_segredo_e_bloqueia_botao_sem_token(self):
        diagnostico = diagnostico_adaptador_dfe()
        self.assertTrue(diagnostico["configurado"])
        self.assertFalse(diagnostico["disponivel"])
        self.assertEqual(diagnostico["ambiente"], "homologação")
        self.assertNotIn("Authorization", diagnostico["mensagem"])

    @override_settings(
        FOCUS_NFE_DFE_TOKEN="token",
        FOCUS_NFE_DFE_TOKENS={},
        FOCUS_NFE_DFE_FETCH_XML=False,
        FOCUS_NFE_DFE_BASE_URL="https://homologacao.focusnfe.com.br",
    )
    def test_erro_de_autenticacao_e_exibido_sem_corpo_da_resposta(self):
        erro_401 = HTTPError("https://focus/lista", 401, "Unauthorized", {}, None)
        with self.assertRaisesMessage(FocusNFeDFeHTTPError, "não foi autorizado"):
            FocusNFeDFeAdapter(opener=_OpenerFila(erro_401)).consultar(
                cnpj="12345678000199", ultimo_nsu="", limite=10
            )