from django.conf import settings
from django.test import SimpleTestCase

from .roteiros_homologacao_canais import (
    CONTRATO_ROTEIROS_HOMOLOGACAO,
    construir_roteiros_homologacao,
)


class RoteirosHomologacaoCanaisTests(SimpleTestCase):
    def resultado(self):
        return construir_roteiros_homologacao(settings.BASE_DIR)

    def test_cria_um_roteiro_para_cada_operacao_e_canal(self):
        resultado = self.resultado()

        self.assertEqual(resultado["contrato"], CONTRATO_ROTEIROS_HOMOLOGACAO)
        self.assertEqual(resultado["total"], 14)
        self.assertEqual(resultado["aguardam_dependencias_externas"], 13)
        self.assertEqual(resultado["bloqueados_por_lacuna_interna"], 1)
        self.assertEqual(len({item["codigo"] for item in resultado["roteiros"]}), 14)

    def test_eventos_focus_permanece_bloqueado_e_direto_aguarda_credenciais(self):
        por_codigo = {item["codigo"]: item for item in self.resultado()["roteiros"]}

        self.assertEqual(
            por_codigo["FOCUS_EVENTOS"]["estado_pre_homologacao"],
            "BLOQUEADO_LACUNA_INTERNA",
        )
        self.assertEqual(
            por_codigo["SEFAZ_DIRETA_EVENTOS"]["estado_pre_homologacao"],
            "AGUARDA_DEPENDENCIAS_EXTERNAS",
        )
        self.assertIn("CC-e", por_codigo["SEFAZ_DIRETA_EVENTOS"]["cenarios_obrigatorios"][0])

    def test_todos_os_roteiros_exigem_evidencia_e_falham_fechado(self):
        resultado = self.resultado()

        for roteiro in resultado["roteiros"]:
            self.assertTrue(roteiro["cenarios_obrigatorios"])
            self.assertTrue(roteiro["evidencias_obrigatorias"])
            self.assertTrue(roteiro["criterio_aprovacao"])
            self.assertTrue(roteiro["bloqueios"])
            self.assertFalse(roteiro["executavel_agora"])
            self.assertFalse(roteiro["rede_permitida"])
            self.assertFalse(roteiro["producao_permitida"])
            self.assertFalse(roteiro["aprovado"])

    def test_contrato_nao_inclui_segredos_nem_declara_homologacao(self):
        resultado = self.resultado()

        self.assertFalse(resultado["rede_executada"])
        self.assertFalse(resultado["segredos_incluidos"])
        self.assertFalse(resultado["homologacao_real_executada"])
        self.assertFalse(resultado["producao_liberada"])
