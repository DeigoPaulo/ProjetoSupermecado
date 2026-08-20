from django.test import SimpleTestCase, override_settings

from .adapters import diagnosticar_adaptador_sefaz
from .sefaz_direta import SefazDiretaAdapter as NovoAdaptador
from .sefaz_direta_adapter import SefazDiretaAdapter as AdaptadorCompativel


class CompatibilidadeImportSefazDiretaTests(SimpleTestCase):
    def test_caminho_antigo_aponta_para_o_novo_pacote(self):
        self.assertIs(AdaptadorCompativel, NovoAdaptador)

    @override_settings(
        FISCAL_SEFAZ_ADAPTER="apps.fiscal.sefaz_direta.SefazDiretaAdapter",
        SEFAZ_DIRETA_NETWORK_ENABLED=False,
    )
    def test_novo_caminho_carrega_pelo_contrato_do_erp(self):
        diagnostico = diagnosticar_adaptador_sefaz()

        self.assertTrue(diagnostico["configurado"])
        self.assertTrue(diagnostico["carregavel"])
        self.assertEqual(
            diagnostico["adaptador"],
            "apps.fiscal.sefaz_direta.SefazDiretaAdapter",
        )