from copy import deepcopy

from django.test import SimpleTestCase

from .ipi_devolvido_contrato import construir_ipi_devolvido, validar_ipi_devolvido
from .tributos_itens_devolucao import CONTRATO_TRIBUTOS_ITENS


class IpiDevolvidoContratoTests(SimpleTestCase):
    def tributos(self):
        return {
            "conteudo": {
                "contrato": CONTRATO_TRIBUTOS_ITENS,
                "itens": [{
                    "nitem_novo": 1, "nitem_original": 2, "item_rascunho_id": 3,
                    "memoria_id": 4, "memoria_sha256": "a" * 64,
                    "revisao_sha256": "b" * 64,
                    "grupos": {"ipi_memoria": {
                        "estado": "NAO_EQUIVALE_IPI_DEVOLVIDO", "codigo": "NA",
                        "base": "0.00", "aliquota": "0.0000", "valor": "0.00",
                    }},
                }],
            },
            "validacao": {"origem_completa": True},
        }

    def test_preserva_ipi_memoria_sem_formar_imposto_devol(self):
        resultado = construir_ipi_devolvido(self.tributos())
        self.assertTrue(resultado["validacao"]["estrutura_valida"])
        self.assertTrue(resultado["validacao"]["origem_completa"])
        self.assertEqual(resultado["conteudo"]["itens"][0]["ipi_memoria"]["valor"], "0.00")
        self.assertEqual(resultado["conteudo"]["itens"][0]["imposto_devol"]["pdevol"], "")
        self.assertEqual(resultado["conteudo"]["total"]["vipidevol"], "")
        self.assertFalse(resultado["validacao"]["permite_emissao"])

    def test_rejeita_valores_ou_total_inseridos_sem_aprovacao(self):
        conteudo = deepcopy(construir_ipi_devolvido(self.tributos())["conteudo"])
        conteudo["itens"][0]["imposto_devol"].update({"pdevol": "100.0000", "vipidevol": "1.00"})
        conteudo["total"]["vipidevol"] = "1.00"
        resultado = validar_ipi_devolvido(conteudo)
        self.assertFalse(resultado["estrutura_valida"])
        codigos = {item["codigo"] for item in resultado["erros"]}
        self.assertIn("VALOR_IPI_DEVOLVIDO_NAO_APROVADO", codigos)
        self.assertIn("TOTAL_IPI_DEVOLVIDO_NAO_APROVADO", codigos)

    def test_rejeita_copia_ou_calculo_automatico(self):
        conteudo = construir_ipi_devolvido(self.tributos())["conteudo"]
        conteudo["politica"].update({"copiar_ipi_memoria": True, "calcular_percentual": True})
        resultado = validar_ipi_devolvido(conteudo)
        self.assertFalse(resultado["estrutura_valida"])
        self.assertIn("AUTOMACAO_PROIBIDA", {item["codigo"] for item in resultado["erros"]})
