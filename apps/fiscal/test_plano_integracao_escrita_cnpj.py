from django.test import SimpleTestCase

from .plano_integracao_escrita_cnpj import (
    CONTRATO_PLANO_INTEGRACAO_ESCRITA_CNPJ,
    planejar_integracao_escrita_empresa_filial,
)


class PlanoIntegracaoEscritaCNPJTests(SimpleTestCase):
    def auditoria(self, *, cnpj=None, colisoes=None):
        return {
            "contrato": "alphanumeric_cnpj_readonly_audit_v1",
            "base": "ENSAIO_LOCAL_NAO_ACEITE_PRODUCAO",
            "resumo": {
                "cnpj_por_status": cnpj or {},
                "colisoes_por_classificacao": colisoes or {},
            },
        }

    def test_classifica_bloqueios_locais_sem_autorizar_correcao(self):
        plano = planejar_integracao_escrita_empresa_filial(
            self.auditoria(
                cnpj={"DV_INVALIDO": 17, "VALIDO": 1},
                colisoes={"BLOQUEANTE": 1, "ESPERADA_EMPRESA_FILIAL": 6},
            )
        )

        self.assertEqual(plano["contrato"], CONTRATO_PLANO_INTEGRACAO_ESCRITA_CNPJ)
        self.assertEqual(plano["dados_existentes"]["quantidade_correcoes_manuais"], 18)
        self.assertEqual(plano["dados_existentes"]["equivalencias_empresa_filial_esperadas"], 6)
        self.assertFalse(plano["dados_existentes"]["correcao_automatica_permitida"])
        self.assertIn(
            "DADOS_LEGADOS_REQUEREM_DECISAO_MANUAL",
            plano["integracao_operacional"]["motivos_bloqueio"],
        )

    def test_equivalencia_empresa_filial_nao_e_tratada_como_correcao(self):
        plano = planejar_integracao_escrita_empresa_filial(
            self.auditoria(colisoes={"ESPERADA_EMPRESA_FILIAL": 3})
        )

        self.assertEqual(plano["dados_existentes"]["quantidade_correcoes_manuais"], 0)
        self.assertEqual(plano["integracao_operacional"]["motivos_bloqueio"], [])
        self.assertFalse(plano["integracao_operacional"]["persistencia_liberada"])

    def test_separa_validacao_local_de_persistencia_operacional(self):
        plano = planejar_integracao_escrita_empresa_filial(self.auditoria())

        self.assertTrue(plano["validacao_local"]["liberada"])
        self.assertEqual(len(plano["validacao_local"]["cenarios_obrigatorios"]), 6)
        self.assertFalse(plano["integracao_operacional"]["persistencia_liberada"])
        self.assertFalse(plano["integracao_operacional"]["constraints_liberadas"])
        self.assertEqual(
            plano["proximo_passo"],
            "VALIDAR_INTEGRACAO_LOCAL_NOS_FORMULARIOS_EMPRESA_FILIAL",
        )

    def test_rejeita_entrada_sem_contrato_de_auditoria(self):
        with self.assertRaisesMessage(ValueError, "AUDITORIA_OBRIGATORIA"):
            planejar_integracao_escrita_empresa_filial(None)
        with self.assertRaisesMessage(ValueError, "CONTRATO_AUDITORIA_NAO_SUPORTADO"):
            planejar_integracao_escrita_empresa_filial({"contrato": "outro"})

    def test_diagnostico_nao_carrega_identificadores_ou_libera_canais(self):
        plano = planejar_integracao_escrita_empresa_filial(self.auditoria())

        def chaves(objeto):
            if isinstance(objeto, dict):
                return set(objeto) | set().union(*(chaves(valor) for valor in objeto.values()))
            if isinstance(objeto, list):
                return set().union(*(chaves(valor) for valor in objeto)) if objeto else set()
            return set()

        self.assertTrue(
            {"valor", "valor_oculto", "impressao_digital", "identificador", "empresa_id"}
            .isdisjoint(chaves(plano))
        )
        self.assertFalse(plano["seguranca"]["expoe_identificadores"])
        self.assertFalse(plano["seguranca"]["libera_focus"])
        self.assertFalse(plano["seguranca"]["libera_sefaz_direta"])
        self.assertFalse(plano["seguranca"]["libera_emissao"])
