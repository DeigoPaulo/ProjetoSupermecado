from pathlib import Path
from tempfile import TemporaryDirectory

from django.conf import settings
from django.test import SimpleTestCase

from .qualificacao_canais_fiscais import (
    CONTRATO_MATRIZ_QUALIFICACAO_CANAIS,
    OPERACOES_OBRIGATORIAS,
    construir_matriz_qualificacao_canais,
)


class MatrizQualificacaoCanaisFiscaisTests(SimpleTestCase):
    def test_matriz_cobre_os_dois_canais_e_todas_as_operacoes(self):
        matriz = construir_matriz_qualificacao_canais(settings.BASE_DIR)

        self.assertEqual(matriz["contrato"], CONTRATO_MATRIZ_QUALIFICACAO_CANAIS)
        self.assertEqual(set(matriz["canais"]), {"FOCUS", "SEFAZ_DIRETA_GO"})
        for canal in matriz["canais"]:
            operacoes = {item["operacao"] for item in matriz["resultados"] if item["canal"] == canal}
            self.assertEqual(operacoes, set(OPERACOES_OBRIGATORIAS))

    def test_evidencias_atuais_confirmam_treze_operacoes_e_expoem_lacuna_focus(self):
        matriz = construir_matriz_qualificacao_canais(settings.BASE_DIR)

        self.assertTrue(all(item["achado_confirmado"] for item in matriz["resultados"]))
        self.assertEqual(matriz["canais"]["FOCUS"]["compativeis_offline"], 6)
        self.assertEqual(matriz["canais"]["FOCUS"]["lacunas_internas"], ["EVENTOS"])
        self.assertEqual(matriz["canais"]["SEFAZ_DIRETA_GO"]["compativeis_offline"], 7)
        self.assertEqual(matriz["canais"]["SEFAZ_DIRETA_GO"]["lacunas_internas"], [])

    def test_matriz_falha_fechado_sem_evidencias_locais(self):
        with TemporaryDirectory() as diretorio:
            matriz = construir_matriz_qualificacao_canais(Path(diretorio))

        self.assertTrue(any(not item["achado_confirmado"] for item in matriz["resultados"]))
        self.assertEqual(matriz["canais"]["FOCUS"]["compativeis_offline"], 0)
        self.assertEqual(matriz["canais"]["SEFAZ_DIRETA_GO"]["compativeis_offline"], 0)

    def test_evidencia_offline_nunca_equivale_a_homologacao_ou_producao(self):
        matriz = construir_matriz_qualificacao_canais(settings.BASE_DIR)

        self.assertFalse(matriz["rede_acessada"])
        self.assertFalse(matriz["credenciais_lidas"])
        self.assertFalse(matriz["homologacao_real_executada"])
        self.assertFalse(matriz["pode_encerrar_homologacao"])
        self.assertFalse(matriz["producao_liberada"])
        self.assertTrue(all(not item["homologacao_real_executada"] for item in matriz["resultados"]))
        self.assertTrue(all(not item["producao_liberada"] for item in matriz["resultados"]))
        self.assertTrue(all(item["dependencias_externas"] for item in matriz["resultados"]))
