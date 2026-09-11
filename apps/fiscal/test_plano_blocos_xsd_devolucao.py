from copy import deepcopy
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from .compatibilidade_matriz_xsd import construir_compatibilidade_matriz_xsd
from .inventario_dados_devolucao import construir_inventario_dados_devolucao
from .matriz_atomica_devolucao import construir_matriz_atomica_devolucao
from .plano_blocos_xsd_devolucao import construir_plano_blocos_xsd, validar_plano_blocos_xsd


SHA_ZIP = "b8589490a58a09a993a80e6ac4d7ed10f20892061ecfc56719337098d4b95998"


class PlanoBlocosXSDDevolucaoTests(SimpleTestCase):
    def resultado(self):
        matriz = construir_matriz_atomica_devolucao(construir_inventario_dados_devolucao({}))
        compatibilidade = construir_compatibilidade_matriz_xsd(
            matriz=matriz,
            arquivo=Path(settings.BASE_DIR) / "docs/evidencias/nfe_2026_09_10/schemas_010f.zip",
            sha256_esperado=SHA_ZIP,
            versao="PL_010f_v1.04",
        )
        return construir_plano_blocos_xsd(matriz=matriz, compatibilidade=compatibilidade)

    def test_agrupa_105_campos_na_ordem_oficial_sem_xml(self):
        resultado = self.resultado()
        self.assertTrue(resultado["validacao"]["estrutura_valida"])
        self.assertEqual(resultado["validacao"]["quantidade_blocos"], 8)
        self.assertEqual(resultado["validacao"]["quantidade_campos"], 105)
        self.assertEqual(
            [(bloco["posicao"], bloco["bloco"], bloco["quantidade_campos"]) for bloco in resultado["conteudo"]["blocos"]],
            [(1, "ide", 5), (2, "emit", 11), (4, "dest", 11), (8, "det", 50),
             (9, "total", 15), (10, "transp", 10), (12, "pag", 2), (14, "infAdic", 1)],
        )
        self.assertFalse(resultado["conteudo"]["politica"]["contem_valores"])
        self.assertFalse(resultado["conteudo"]["politica"]["construir_arvore_xml"])
        self.assertFalse(resultado["validacao"]["permite_gerar_xml"])

    def test_todos_os_campos_e_blocos_permanecem_bloqueados(self):
        conteudo = self.resultado()["conteudo"]
        self.assertTrue(all(not bloco["pronto_para_construir"] for bloco in conteudo["blocos"]))
        self.assertTrue(all(
            not campo["pronto_para_serializar"] and "SERIALIZACAO_NAO_IMPLEMENTADA" in campo["bloqueios"]
            for bloco in conteudo["blocos"] for campo in bloco["campos"]
        ))
        self.assertEqual(len(conteudo["bloqueios_globais"]), 4)

    def test_rejeita_relatorio_com_divergencia(self):
        matriz = construir_matriz_atomica_devolucao(construir_inventario_dados_devolucao({}))
        compatibilidade = construir_compatibilidade_matriz_xsd(
            matriz=matriz,
            arquivo=Path(settings.BASE_DIR) / "docs/evidencias/nfe_2026_09_10/schemas_010f.zip",
            sha256_esperado=SHA_ZIP,
            versao="PL_010f_v1.04",
        )
        compatibilidade["conteudo"]["resumo"]["DIVERGENTE_DO_XSD_AUDITADO"] = 1
        with self.assertRaisesMessage(ValueError, "sem divergências"):
            construir_plano_blocos_xsd(matriz=matriz, compatibilidade=compatibilidade)

    def test_validador_rejeita_ordem_contagem_e_liberacao(self):
        conteudo = deepcopy(self.resultado()["conteudo"])
        conteudo["blocos"].reverse()
        conteudo["blocos"][0]["quantidade_campos"] += 1
        conteudo["blocos"][0]["pronto_para_construir"] = True
        conteudo["blocos"][0]["campos"][0]["pronto_para_serializar"] = True
        conteudo["quantidade_campos_confirmados"] = 104
        conteudo["politica"]["gerar_xml"] = True
        validacao = validar_plano_blocos_xsd(conteudo)
        self.assertFalse(validacao["estrutura_valida"])
        codigos = {erro["codigo"] for erro in validacao["erros"]}
        self.assertIn("ORDEM_DIVERGENTE", codigos)
        self.assertIn("CONTAGEM_DIVERGENTE", codigos)
        self.assertIn("BLOCO_LIBERADO_INDEVIDAMENTE", codigos)
        self.assertIn("CAMPO_LIBERADO_INDEVIDAMENTE", codigos)
        self.assertIn("TOTAL_DIVERGENTE", codigos)
        self.assertIn("POLITICA_INVALIDA", codigos)