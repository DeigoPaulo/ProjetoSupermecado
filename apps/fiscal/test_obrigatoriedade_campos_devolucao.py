from copy import deepcopy

from django.test import SimpleTestCase

from .obrigatoriedade_campos_devolucao import (
    construir_obrigatoriedade_campos_devolucao,
    validar_obrigatoriedade_campos_devolucao,
)


class ObrigatoriedadeCamposDevolucaoTests(SimpleTestCase):
    def test_classifica_38_familias_sem_aplicacao_operacional(self):
        resultado = construir_obrigatoriedade_campos_devolucao()
        self.assertTrue(resultado["validacao"]["estrutura_valida"])
        self.assertEqual(resultado["validacao"]["quantidade_campos"], 38)
        self.assertGreater(resultado["validacao"]["quantidade_pendentes"], 0)
        self.assertFalse(resultado["validacao"]["analise_normativa_integral"])
        self.assertTrue(all(item["aplicacao_operacional"] is False for item in resultado["conteudo"]["itens"]))
        self.assertFalse(resultado["validacao"]["permite_gerar_xml"])
        self.assertFalse(resultado["validacao"]["permite_emissao"])

    def test_distingue_xsd_regra_contextual_e_hipotese_contabil(self):
        itens = {
            (item["grupo"], item["origem_contrato"]): item
            for item in construir_obrigatoriedade_campos_devolucao()["conteudo"]["itens"]
        }
        referencia = itens[("referencias_itens", "itens[].chave_acesso")]
        self.assertEqual(referencia["categoria"], "OBRIGATORIO_REGRA_CONTEXTO")
        self.assertEqual(referencia["cardinalidade_xsd"], "0-1/1-1")
        self.assertFalse(referencia["vigencia_operacional_confirmada"])
        pagamento = itens[("pagamento_fiscal", "politica.tpag")]
        self.assertEqual(pagamento["categoria"], "OBRIGATORIO_REGRA_CONTEXTO")
        self.assertFalse(pagamento["exige_decisao_contador"])
        ipi = itens[("ipi_devolvido", "itens[].imposto_devol.pdevol")]
        self.assertEqual(ipi["categoria"], "CONDICIONADO_HIPOTESE")
        self.assertTrue(ipi["exige_decisao_contador"])
        cenq = itens[("ipi_devolvido", "itens[].enquadramento_ipi.valor_candidato")]
        self.assertEqual(cenq["categoria"], "CONDICIONADO_GRUPO_IPI")
        self.assertEqual(cenq["cardinalidade_xsd"], "1-1_DENTRO_IPI")
        self.assertTrue(cenq["exige_decisao_contador"])
        rtc = itens[("rtc", "totais.rtc")]
        self.assertEqual(rtc["categoria"], "PENDENTE_VIGENCIA_E_ENQUADRAMENTO")

    def test_rejeita_promocao_de_regra_ou_aprovacao_antecipada(self):
        conteudo = deepcopy(construir_obrigatoriedade_campos_devolucao()["conteudo"])
        conteudo["itens"][2]["categoria"] = "OBRIGATORIO_ESTRUTURAL"
        conteudo["itens"][2]["aplicacao_operacional"] = True
        conteudo["escopo"]["vigencia_go_confirmada"] = True
        conteudo["politica"]["permitir_emissao"] = True
        resultado = validar_obrigatoriedade_campos_devolucao(conteudo)
        self.assertFalse(resultado["estrutura_valida"])
        codigos = {item["codigo"] for item in resultado["erros"]}
        self.assertIn("CLASSIFICACAO_DIVERGENTE", codigos)
        self.assertIn("APLICACAO_ANTECIPADA_PROIBIDA", codigos)
        self.assertIn("ESCOPO_OU_APROVACAO_ANTECIPADA", codigos)
        self.assertIn("POLITICA_DE_BLOQUEIO_INVALIDA", codigos)
        self.assertFalse(resultado["permite_emissao"])
