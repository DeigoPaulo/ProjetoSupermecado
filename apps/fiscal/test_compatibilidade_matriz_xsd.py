import io
import json
from copy import deepcopy
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import SimpleTestCase

from .compatibilidade_matriz_xsd import (
    construir_compatibilidade_matriz_xsd,
    validar_compatibilidade_matriz_xsd,
)
from .inventario_dados_devolucao import construir_inventario_dados_devolucao
from .matriz_atomica_devolucao import construir_matriz_atomica_devolucao


SHA_ZIP = "b8589490a58a09a993a80e6ac4d7ed10f20892061ecfc56719337098d4b95998"


class CompatibilidadeMatrizXSDTests(SimpleTestCase):
    def resultado(self):
        inventario = construir_inventario_dados_devolucao({})
        matriz = construir_matriz_atomica_devolucao(inventario)
        return construir_compatibilidade_matriz_xsd(
            matriz=matriz,
            arquivo=Path(settings.BASE_DIR) / "docs/evidencias/nfe_2026_09_10/schemas_010f.zip",
            sha256_esperado=SHA_ZIP,
            versao="PL_010f_v1.04",
        )

    def test_confirma_destinos_sem_liberar_serializacao(self):
        resultado = self.resultado()
        self.assertTrue(resultado["validacao"]["estrutura_valida"])
        self.assertEqual(resultado["validacao"]["quantidade_itens"], 115)
        self.assertEqual(resultado["conteudo"]["resumo"], {
            "CONFIRMADO_NO_XSD_AUDITADO": 105,
            "DIVERGENTE_DO_XSD_AUDITADO": 0,
            "PENDENTE_DE_LEIAUTE_APROVADO": 8,
            "SEM_TAG_TOTAL_DOCUMENTADA": 2,
        })
        self.assertTrue(resultado["conteudo"]["compativel_sem_divergencias"])
        self.assertTrue(all(not item["serializacao_liberada"] for item in resultado["conteudo"]["itens"]))
        self.assertFalse(resultado["validacao"]["permite_gerar_xml"])
        self.assertFalse(resultado["validacao"]["permite_focus"])
        self.assertFalse(resultado["validacao"]["permite_sefaz_direta"])

    def test_exige_todas_as_alternativas_documentadas(self):
        itens = {(item["grupo"], item["campo"]): item for item in self.resultado()["conteudo"]["itens"]}
        self.assertEqual(
            itens[("tributos_itens", "itens[].grupos.pis.variante_candidata")]["alternativas_exigidas"],
            4,
        )
        self.assertEqual(
            itens[("icms_st_fcp", "itens[].destino_fiscal.grupo_fcp")]["alternativas_exigidas"],
            6,
        )
        self.assertEqual(
            itens[("rtc", "itens[].destino_fiscal.grupo_ibs")]["alternativas_exigidas"],
            0,
        )

    def test_comando_reproduz_relatorio_sem_escrever(self):
        saida = io.StringIO()
        call_command(
            "confrontar_matriz_xsd_devolucao",
            arquivo=str(Path(settings.BASE_DIR) / "docs/evidencias/nfe_2026_09_10/schemas_010f.zip"),
            sha256=SHA_ZIP,
            versao="PL_010f_v1.04",
            stdout=saida,
        )
        resultado = json.loads(saida.getvalue())
        self.assertEqual(resultado["conteudo"]["resumo"]["CONFIRMADO_NO_XSD_AUDITADO"], 105)
        self.assertFalse(resultado["conteudo"]["politica"]["promover_schema"])

    def test_validador_rejeita_resumo_estado_e_politica_adulterados(self):
        conteudo = deepcopy(self.resultado()["conteudo"])
        conteudo["itens"][0]["serializacao_liberada"] = True
        conteudo["itens"][1]["destino_xml_futuro"] = "NFe/infNFe/ide/inventado"
        conteudo["itens"][-1]["estado"] = "CONFIRMADO_NO_XSD_AUDITADO"
        conteudo["resumo"]["CONFIRMADO_NO_XSD_AUDITADO"] -= 1
        conteudo["compativel_sem_divergencias"] = False
        conteudo["politica"]["gerar_xml"] = True
        validacao = validar_compatibilidade_matriz_xsd(conteudo)
        self.assertFalse(validacao["estrutura_valida"])
        codigos = {erro["codigo"] for erro in validacao["erros"]}
        self.assertIn("ESTADO_INVALIDO", codigos)
        self.assertIn("DESTINO_DIVERGENTE", codigos)
        self.assertIn("CLASSIFICACAO_DIVERGENTE", codigos)
        self.assertIn("RESUMO_DIVERGENTE", codigos)
        self.assertIn("COMPATIBILIDADE_DIVERGENTE", codigos)
        self.assertIn("POLITICA_INVALIDA", codigos)

    def test_recusa_matriz_adulterada_antes_de_ler_xsd(self):
        inventario = construir_inventario_dados_devolucao({})
        matriz = construir_matriz_atomica_devolucao(inventario)
        matriz["conteudo"]["itens"][0]["destino_xml_futuro"] = "NFe/infNFe/ide/inventado"
        with self.assertRaisesMessage(ValueError, "matriz atômica deve estar íntegra"):
            construir_compatibilidade_matriz_xsd(
                matriz=matriz,
                arquivo=Path(settings.BASE_DIR) / "docs/evidencias/nfe_2026_09_10/schemas_010f.zip",
                sha256_esperado=SHA_ZIP,
                versao="PL_010f_v1.04",
            )