from decimal import Decimal
from types import SimpleNamespace

from django.test import SimpleTestCase

from .devolucao_fornecedor import TRIBUTOS_MEMORIA_CALCULO
from .rateio_devolucao import COMPONENTES
from .reflexos_devolucao import ReflexosBasesDevolucaoForm


class ReflexosBasesTests(SimpleTestCase):
    def setUp(self):
        self.itens = [SimpleNamespace(pk=i, item_rascunho_id=i + 10, numero_item_xml=str(i),
            **{f"base_{t}": Decimal("10.00") for t, _ in TRIBUTOS_MEMORIA_CALCULO}) for i in (1, 2)]
        self.rateio = [{"item_memoria_id": i.pk, "item_rascunho_id": i.item_rascunho_id,
                       "numero_item_xml": i.numero_item_xml} for i in self.itens]
        self.dados = {"fundamentacao": "Orientação sintética para teste aritmético."}
        for t, _ in TRIBUTOS_MEMORIA_CALCULO:
            self.dados[f"total_base_{t}"] = "20,00"
            for item in self.itens:
                self.dados[f"item_{item.pk}_{t}_base_final"] = "10,00"
                for c in COMPONENTES:
                    self.dados[f"item_{item.pk}_{t}_{c}"] = "0"

    def form(self, **alteracoes):
        return ReflexosBasesDevolucaoForm({**self.dados, **alteracoes}, itens=self.itens, linhas_rateio=self.rateio)

    def test_zeros_explicitos_todos_tributos_sem_emissao(self):
        form = self.form()
        self.assertTrue(form.is_valid(), form.errors)
        self.assertFalse(form.resultado["permite_emissao"])
        self.assertEqual(len(form.resultado["itens"]), 2)
        self.assertEqual(len(form.resultado["totais_bases"]), 8)

    def test_impactos_assinados_e_centavos_sem_presumir_incidencia(self):
        form = self.form(item_1_icms_frete="0,03", item_1_icms_desconto="-0,01",
                         item_1_icms_base_final="10,02", total_base_icms="20,02")
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.resultado["totais_bases"]["pis"], "20.00")
        self.assertEqual(form.resultado["totais_bases"]["icms"], "20.02")

    def test_base_divergente_e_total_divergente_nao_produzem_resultado(self):
        for dados in ({"item_1_icms_frete": "1"}, {"total_base_ipi": "21"}):
            form = self.form(**dados)
            self.assertFalse(form.is_valid())
            self.assertIsNone(form.resultado)

    def test_valores_obrigatorios_finitos_e_precisos(self):
        for valor in ("", "NaN", "Infinity", "0,001", "10000000000000"):
            with self.subTest(valor=valor):
                self.assertFalse(self.form(item_1_icms_frete=valor).is_valid())
        self.assertFalse(self.form(item_1_icms_base_final="-1").is_valid())
        self.assertFalse(self.form(fundamentacao="").is_valid())

    def test_itens_ausentes_extras_e_duplicados(self):
        original = self.rateio[:]
        for linhas in ([], original[:1], original + [original[0]], original + [{"item_memoria_id": 3}]):
            self.rateio = linhas
            self.assertFalse(self.form().is_valid())

    def test_vinculos_divergentes(self):
        self.rateio[0]["item_rascunho_id"] = 999
        self.assertFalse(self.form().is_valid())

    def test_base_final_zero_e_permitida_quando_conferida(self):
        form = self.form(item_1_icms_desconto="-10", item_1_icms_base_final="0", total_base_icms="10")
        self.assertTrue(form.is_valid(), form.errors)
