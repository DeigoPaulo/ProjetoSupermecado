from decimal import Decimal
from types import SimpleNamespace
from django.test import SimpleTestCase
from .rateio_devolucao import RateioDevolucaoForm


class RateioFormTests(SimpleTestCase):
    def form(self, **alteracoes):
        itens = [SimpleNamespace(pk=i, item_rascunho_id=i, numero_item_xml=i, valor_operacao=Decimal("10.00")) for i in (1, 2)]
        dados = {"criterio": "Distribuição explícita dos centavos.", "frete_1": "0,01", "frete_2": "0,02", **{f"{campo}_{i}": "0" for campo in ("seguro", "despesas", "desconto") for i in (1, 2)}}
        return RateioDevolucaoForm({**dados, **alteracoes}, itens=itens, totais={"frete": "0.03", "seguro": "0", "despesas": "0", "desconto": "0", "total": "20.03"})

    def test_centavos_sem_arredondamento_automatico(self):
        form = self.form()
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual([linha["total"] for linha in form.linhas], ["10.01", "10.02"])

    def test_componentes_obrigatorios_precisos_e_nao_negativos(self):
        for valor in ("", "-0,01", "0,001", "NaN", "Infinity", "0,03"):
            with self.subTest(valor=valor):
                self.assertFalse(self.form(frete_2=valor).is_valid())

    def test_desconto_nao_pode_tornar_item_negativo(self):
        self.assertFalse(self.form(desconto_1="11").is_valid())
