from copy import deepcopy

from django.test import SimpleTestCase

from .inventario_dados_devolucao import (
    CAMPOS_ATOMICOS,
    construir_inventario_dados_devolucao,
    validar_inventario_dados_devolucao,
)


class InventarioDadosDevolucaoTests(SimpleTestCase):
    def test_inventaria_sem_expor_valores_ou_liberar_canais(self):
        resultado = construir_inventario_dados_devolucao({})
        self.assertTrue(resultado["validacao"]["estrutura_valida"])
        self.assertEqual(resultado["validacao"]["quantidade_campos_atomicos"], len(CAMPOS_ATOMICOS))
        self.assertGreater(len(CAMPOS_ATOMICOS), 90)
        self.assertEqual(resultado["validacao"]["quantidade_campos_atomicos"], 109)
        self.assertEqual(resultado["validacao"]["quantidade_lacunas_modelagem"], 5)
        codigos = {item["codigo"] for item in resultado["conteudo"]["lacunas_modelagem"]}
        self.assertNotIn("MODALIDADE_BASE_ICMS_NAO_MODELADA", codigos)
        self.assertNotIn("INDTOT_NAO_MODELADO", codigos)
        self.assertNotIn("IND_IE_DESTINATARIO_NAO_MODELADO", codigos)
        self.assertNotIn("CADASTRO_FORNECEDOR_NAO_CONFRONTADO_COM_XML", codigos)
        self.assertNotIn("FORNECEDOR_SEM_CADASTRO_FISCAL_ESTRUTURADO", codigos)
        self.assertTrue(all(item["expoe_valor"] is False for item in resultado["conteudo"]["itens"]))
        self.assertFalse(resultado["validacao"]["permite_gerar_xml"])
        self.assertFalse(resultado["validacao"]["permite_focus"])
        self.assertFalse(resultado["validacao"]["permite_sefaz_direta"])

    def test_distingue_dado_disponivel_condicionado_e_bloqueado_por_politica(self):
        extracao = {
            "pagamento_fiscal": {"conteudo": {"politica": {"tpag": "90", "vpag": "0.00"}}},
            "produtos": {"conteudo": {"itens": [{"ean": "", "descricao": "Produto de teste"}]}},
            "ipi_devolvido": {"conteudo": {"itens": [{"imposto_devol": {"pdevol": ""}}]}},
        }
        inventario = construir_inventario_dados_devolucao(extracao)["conteudo"]["itens"]
        itens = {(item["grupo"], item["campo"]): item for item in inventario}
        self.assertEqual(itens[("pagamento_fiscal", "politica.tpag")]["estado"], "DISPONIVEL_NO_CONTRATO")
        self.assertEqual(itens[("produtos", "itens[].ean")]["estado"], "CONDICIONADO_NAO_INFORMADO")
        self.assertEqual(itens[("ipi_devolvido", "itens[].imposto_devol.pdevol")]["estado"], "NAO_DEFINIDO_POR_POLITICA")
        self.assertEqual(itens[("produtos", "itens[].descricao")]["preenchidas"], 1)
        self.assertNotIn("Produto de teste", str(inventario))

    def test_rejeita_exposicao_serializacao_ou_remocao_de_lacuna(self):
        conteudo = deepcopy(construir_inventario_dados_devolucao({})["conteudo"])
        conteudo["itens"][0]["expoe_valor"] = True
        conteudo["itens"][0]["permite_serializacao"] = True
        conteudo["lacunas_modelagem"].pop()
        conteudo["politica"]["usar_xml_historico_como_cadastro_atual"] = True
        resultado = validar_inventario_dados_devolucao(conteudo)
        self.assertFalse(resultado["estrutura_valida"])
        codigos = {item["codigo"] for item in resultado["erros"]}
        self.assertIn("EXPOSICAO_DE_VALOR_PROIBIDA", codigos)
        self.assertIn("SERIALIZACAO_ANTECIPADA_PROIBIDA", codigos)
        self.assertIn("LACUNAS_DIVERGENTES", codigos)
        self.assertIn("POLITICA_DE_BLOQUEIO_INVALIDA", codigos)
        self.assertFalse(resultado["permite_emissao"])
