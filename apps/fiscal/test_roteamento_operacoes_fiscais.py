from types import SimpleNamespace

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings

from .cce_adapters import carregar_adaptador_cce, caminho_adaptador_cce
from .dfe_adapters import carregar_adaptador_dfe, caminho_adaptador_dfe
from .manifestacao_adapters import (
    carregar_adaptador_manifestacao,
    caminho_adaptador_manifestacao,
)
from .roteamento_operacoes_fiscais import resolver_adaptador_operacao


class FakeDFeAdapter:
    def consultar(self, **kwargs):
        return kwargs


class FakeCCEAdapter:
    def corrigir(self, **kwargs):
        return kwargs


class FakeManifestacaoAdapter:
    def manifestar(self, **kwargs):
        return kwargs


def _filial(provedor, uf="GO"):
    configuracao = SimpleNamespace(provedor_emissao=provedor)
    return SimpleNamespace(uf=uf, configuracao_fiscal=configuracao)


class RoteamentoOperacoesFiscaisTests(SimpleTestCase):
    def test_sefaz_direta_resolve_dfe_cce_e_manifestacao(self):
        filial = _filial("SEFAZ_DIRETA_GO")

        self.assertEqual(caminho_adaptador_dfe(filial=filial)["provedor"], "SEFAZ_DIRETA_GO")
        self.assertIn("SefazDiretaDFeAdapter", caminho_adaptador_dfe(filial=filial)["adaptador"])
        self.assertIn("SefazDiretaCartaCorrecaoAdapter", caminho_adaptador_cce(filial=filial)["adaptador"])
        self.assertIn("SefazDiretaManifestacaoAdapter", caminho_adaptador_manifestacao(filial=filial)["adaptador"])

    def test_focus_resolve_dfe_e_bloqueia_eventos_nao_implementados(self):
        filial = _filial("FOCUS")

        self.assertIn("FocusNFeDFeAdapter", caminho_adaptador_dfe(filial=filial)["adaptador"])
        with self.assertRaisesMessage(ImproperlyConfigured, "não implementa"):
            carregar_adaptador_cce(filial=filial)
        with self.assertRaisesMessage(ImproperlyConfigured, "não implementa"):
            carregar_adaptador_manifestacao(filial=filial)

    def test_canal_desativado_nao_carrega_operacoes_auxiliares(self):
        filial = _filial("DESATIVADO")

        self.assertIsNone(carregar_adaptador_dfe(filial=filial))
        self.assertIsNone(carregar_adaptador_cce(filial=filial))
        self.assertIsNone(carregar_adaptador_manifestacao(filial=filial))

    @override_settings(
        FISCAL_DFE_ADAPTER="apps.fiscal.test_roteamento_operacoes_fiscais.FakeDFeAdapter",
        FISCAL_CCE_ADAPTER="apps.fiscal.test_roteamento_operacoes_fiscais.FakeCCEAdapter",
        FISCAL_MANIFESTACAO_ADAPTER="apps.fiscal.test_roteamento_operacoes_fiscais.FakeManifestacaoAdapter",
    )
    def test_padrao_servidor_preserva_compatibilidade_explicita(self):
        filial = _filial("PADRAO_SERVIDOR")

        self.assertIsInstance(carregar_adaptador_dfe(filial=filial), FakeDFeAdapter)
        self.assertIsInstance(carregar_adaptador_cce(filial=filial), FakeCCEAdapter)
        self.assertIsInstance(carregar_adaptador_manifestacao(filial=filial), FakeManifestacaoAdapter)

    def test_sefaz_direta_fora_de_go_falha_fechado(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "somente para filiais de Goiás"):
            resolver_adaptador_operacao(
                filial=_filial("SEFAZ_DIRETA_GO", uf="SP"),
                operacao="DFE",
            )
