from copy import deepcopy

from django.test import SimpleTestCase

from .pagamento_fiscal_devolucao import (
    construir_politica_pagamento_devolucao,
    validar_politica_pagamento_devolucao,
)


class PagamentoFiscalDevolucaoTests(SimpleTestCase):
    def test_politica_sem_pagamento_e_nao_emissiva(self):
        resultado = construir_politica_pagamento_devolucao()
        self.assertTrue(resultado["validacao"]["estrutura_valida"])
        self.assertEqual(resultado["conteudo"]["politica"]["tpag"], "90")
        self.assertEqual(resultado["conteudo"]["politica"]["vpag"], "0.00")
        self.assertFalse(resultado["validacao"]["permite_gerar_xml"])
        self.assertFalse(resultado["validacao"]["permite_emissao"])

    def test_rejeita_forma_ou_valor_de_pagamento(self):
        conteudo = deepcopy(construir_politica_pagamento_devolucao()["conteudo"])
        conteudo["politica"].update({"tpag": "01", "vpag": "13.00", "usa_total_comercial": True})
        validacao = validar_politica_pagamento_devolucao(conteudo)
        self.assertFalse(validacao["estrutura_valida"])
        codigos = {item["codigo"] for item in validacao["erros"]}
        self.assertIn("SOMENTE_SEM_PAGAMENTO_PERMITIDO", codigos)
        self.assertIn("SEM_PAGAMENTO_EXIGE_VALOR_ZERO", codigos)
        self.assertIn("TOTAL_COMERCIAL_NAO_PODE_ALIMENTAR_PAGAMENTO", codigos)

    def test_rejeita_qualquer_efeito_operacional(self):
        for campo in construir_politica_pagamento_devolucao()["conteudo"]["efeitos_operacionais"]:
            with self.subTest(campo=campo):
                conteudo = deepcopy(construir_politica_pagamento_devolucao()["conteudo"])
                conteudo["efeitos_operacionais"][campo] = True
                validacao = validar_politica_pagamento_devolucao(conteudo)
                self.assertFalse(validacao["estrutura_valida"])
                self.assertIn("EFEITO_OPERACIONAL_PROIBIDO", {item["codigo"] for item in validacao["erros"]})
