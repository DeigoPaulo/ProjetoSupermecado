from copy import deepcopy

from django.test import SimpleTestCase

from .inventario_dados_devolucao import CAMPOS_ATOMICOS, construir_inventario_dados_devolucao
from .matriz_atomica_devolucao import (
    construir_matriz_atomica_devolucao,
    validar_matriz_atomica_devolucao,
)


class MatrizAtomicaDevolucaoTests(SimpleTestCase):
    def matriz(self):
        inventario = construir_inventario_dados_devolucao({})
        return construir_matriz_atomica_devolucao(inventario)

    def test_consolida_todos_os_campos_sem_liberar_canais(self):
        resultado = self.matriz()
        self.assertTrue(resultado["validacao"]["estrutura_valida"])
        self.assertEqual(resultado["validacao"]["quantidade_campos"], len(CAMPOS_ATOMICOS))
        self.assertEqual(resultado["validacao"]["quantidade_campos"], 115)
        self.assertEqual(resultado["validacao"]["quantidade_destinos_documentados"], 115)
        self.assertTrue(all(
            item["destino_xml_futuro"].startswith("NFe/infNFe/")
            for item in resultado["conteudo"]["itens"]
        ))
        self.assertTrue(all(
            item["serializacao_implementada"] is False
            for item in resultado["conteudo"]["itens"]
        ))
        self.assertFalse(resultado["validacao"]["permite_gerar_xml"])
        self.assertFalse(resultado["validacao"]["permite_focus"])
        self.assertFalse(resultado["validacao"]["permite_sefaz_direta"])

    def test_preserva_destinos_e_regras_criticos(self):
        itens = {
            (item["grupo"], item["campo"]): item
            for item in self.matriz()["conteudo"]["itens"]
        }
        self.assertEqual(
            itens[("referencias_itens", "itens[].chave_acesso")]["destino_xml_futuro"],
            "NFe/infNFe/det/DFeReferenciado/chaveAcesso",
        )
        self.assertIn(
            "PISOutr",
            itens[("tributos_itens", "itens[].grupos.pis.variante_candidata")]["destino_xml_futuro"],
        )
        self.assertEqual(
            itens[("ipi_devolvido", "itens[].imposto_devol.vipidevol")]["regra_aplicacao"],
            "SOMENTE_APOS_DECISAO_APROVADA",
        )
        self.assertIn(
            "LEIAUTE_RTC_PENDENTE",
            itens[("rtc", "itens[].classificacao_rtc.codigo")]["destino_xml_futuro"],
        )

    def test_rejeita_destino_regra_serializacao_e_politica_adulterados(self):
        conteudo = deepcopy(self.matriz()["conteudo"])
        conteudo["itens"][0]["destino_xml_futuro"] = "NFe/infNFe/ide/errado"
        conteudo["itens"][1]["regra_aplicacao"] = "DEFAULT"
        conteudo["itens"][2]["serializacao_implementada"] = True
        conteudo["itens"][3]["estado_inventario"] = "INVENTARIO_AUSENTE"
        conteudo["politica"]["permitir_focus"] = True
        resultado = validar_matriz_atomica_devolucao(conteudo)
        self.assertFalse(resultado["estrutura_valida"])
        codigos = {item["codigo"] for item in resultado["erros"]}
        self.assertIn("DESTINO_XML_DIVERGENTE", codigos)
        self.assertIn("REGRA_DIVERGENTE", codigos)
        self.assertIn("ESTADO_INVENTARIO_INVALIDO", codigos)
        self.assertIn("SERIALIZACAO_ANTECIPADA_PROIBIDA", codigos)
        self.assertIn("POLITICA_DE_BLOQUEIO_INVALIDA", codigos)
