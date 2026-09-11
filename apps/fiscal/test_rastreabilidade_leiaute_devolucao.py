from copy import deepcopy

from django.test import SimpleTestCase

from .rastreabilidade_leiaute_devolucao import (
    construir_rastreabilidade_leiaute_devolucao,
    validar_rastreabilidade_leiaute_devolucao,
)


class RastreabilidadeLeiauteDevolucaoTests(SimpleTestCase):
    def test_mapeia_todos_os_contratos_sem_liberar_canais(self):
        resultado = construir_rastreabilidade_leiaute_devolucao()
        self.assertTrue(resultado["validacao"]["estrutura_valida"])
        self.assertEqual(resultado["validacao"]["quantidade_grupos"], 13)
        self.assertEqual(resultado["validacao"]["quantidade_campos"], 42)
        self.assertFalse(resultado["validacao"]["permite_gerar_xml"])
        self.assertFalse(resultado["validacao"]["permite_focus"])
        self.assertFalse(resultado["validacao"]["permite_sefaz_direta"])
        self.assertFalse(resultado["validacao"]["permite_emissao"])
        evidencia = resultado["conteudo"]["evidencia_xsd"]
        self.assertTrue(evidencia["evidencia_arquivada"])
        self.assertTrue(evidencia["hash_reproduzivel"])
        self.assertFalse(evidencia["instalado_em_fiscal_schemas"])
        self.assertEqual(evidencia["contrato_auditoria_offline"], "fiscal_schema_package_audit_v1")
        self.assertTrue(evidencia["auditoria_offline_disponivel"])
        self.assertFalse(evidencia["pacote_aprovado"])
        self.assertTrue(all(
            campo["serializacao_local_implementada"] is False
            for grupo in resultado["conteudo"]["grupos"] for campo in grupo["campos"]
        ))

    def test_registra_lacunas_criticas_do_focus_e_transporte_integral_direto(self):
        conteudo = construir_rastreabilidade_leiaute_devolucao()["conteudo"]
        campos = {
            (grupo["grupo"], campo["origem_contrato"]): campo
            for grupo in conteudo["grupos"] for campo in grupo["campos"]
        }
        self.assertEqual(campos[("referencias_itens", "itens[].chave_acesso")]["focus"], "NAO_MAPEADO")
        self.assertEqual(campos[("ipi_devolvido", "itens[].imposto_devol.vipidevol")]["focus"], "NAO_MAPEADO")
        self.assertEqual(campos[("ipi_devolvido", "itens[].enquadramento_ipi.valor_candidato")]["focus"], "PARCIAL")
        self.assertEqual(campos[("tributos_itens", "itens[].grupos.pis.variante_candidata")]["focus"], "PARCIAL")
        self.assertEqual(campos[("tributos_itens", "itens[].grupos.cofins.modalidade_calculo_candidata")]["focus"], "PARCIAL")
        self.assertEqual(campos[("pagamento_fiscal", "politica.tpag")]["focus"], "MAPEADO")
        self.assertTrue(all(
            campo["sefaz_direta"] == "SEM_TRANSFORMACAO_DE_CONTEUDO"
            for campo in campos.values()
        ))
        self.assertFalse(conteudo["conclusoes"]["sefaz_direta_paridade_conteudo"])

    def test_rejeita_falsa_prontidao_ou_serializacao_antecipada(self):
        conteudo = deepcopy(construir_rastreabilidade_leiaute_devolucao()["conteudo"])
        conteudo["grupos"][0]["campos"][0]["serializacao_local_implementada"] = True
        conteudo["grupos"][1]["campos"][0]["focus"] = "MAPEADO"
        conteudo["evidencia_xsd"]["sha256_arquivo_principal"] = "0" * 64
        conteudo["conclusoes"]["focus_paridade_conteudo"] = True
        conteudo["politica"]["permitir_sefaz_direta"] = True
        resultado = validar_rastreabilidade_leiaute_devolucao(conteudo)
        self.assertFalse(resultado["estrutura_valida"])
        codigos = {item["codigo"] for item in resultado["erros"]}
        self.assertIn("SERIALIZACAO_ANTECIPADA_PROIBIDA", codigos)
        self.assertIn("MAPEAMENTO_DIVERGENTE", codigos)
        self.assertIn("EVIDENCIA_INVALIDA", codigos)
        self.assertIn("CONCLUSAO_ANTECIPADA_PROIBIDA", codigos)
        self.assertIn("POLITICA_DE_BLOQUEIO_INVALIDA", codigos)
        self.assertFalse(resultado["permite_sefaz_direta"])
        self.assertFalse(resultado["permite_emissao"])
