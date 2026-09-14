from copy import deepcopy
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from .compatibilidade_matriz_xsd import construir_compatibilidade_matriz_xsd
from .especificacao_ide_devolucao import (
    construir_especificacao_ide_devolucao,
    validar_especificacao_ide_devolucao,
)
from .inventario_dados_devolucao import construir_inventario_dados_devolucao
from .matriz_atomica_devolucao import construir_matriz_atomica_devolucao
from .plano_blocos_xsd_devolucao import construir_plano_blocos_xsd


SHA_ZIP = "b8589490a58a09a993a80e6ac4d7ed10f20892061ecfc56719337098d4b95998"


class EspecificacaoIdeDevolucaoTests(SimpleTestCase):
    def cadeia(self):
        matriz = construir_matriz_atomica_devolucao(construir_inventario_dados_devolucao({}))
        compatibilidade = construir_compatibilidade_matriz_xsd(
            matriz=matriz,
            arquivo=Path(settings.BASE_DIR) / "docs/evidencias/nfe_2026_09_10/schemas_010f.zip",
            sha256_esperado=SHA_ZIP,
            versao="PL_010f_v1.04",
        )
        plano = construir_plano_blocos_xsd(matriz=matriz, compatibilidade=compatibilidade)
        return matriz, plano

    def resultado(self):
        matriz, plano = self.cadeia()
        return construir_especificacao_ide_devolucao(matriz=matriz, plano_blocos=plano)

    def test_especifica_cinco_campos_na_ordem_exata_do_ide(self):
        resultado = self.resultado()
        self.assertTrue(resultado["validacao"]["estrutura_valida"])
        self.assertEqual(
            [(item["ordem_ide"], item["destino_xml_futuro"].rsplit("/", 1)[-1])
             for item in resultado["conteudo"]["campos"]],
            [(3, "natOp"), (11, "idDest"), (12, "cMunFG"), (21, "indFinal"), (22, "indPres")],
        )
        self.assertTrue(all(
            item["cardinalidade_xsd"] == {"minimo": 1, "maximo": 1}
            for item in resultado["conteudo"]["campos"]
        ))

    def test_registra_formatos_fontes_e_bloqueios_sem_valores(self):
        campos = {item["campo"]: item for item in self.resultado()["conteudo"]["campos"]}
        self.assertEqual(campos["identificacao.natureza_operacao"]["formato_xsd"]["maximo_caracteres"], 60)
        self.assertEqual(campos["identificacao.codigo_municipio_fato_gerador"]["formato_xsd"]["padrao"], "[0-9]{7}")
        self.assertEqual(campos["identificacao.destino_operacao"]["formato_xsd"]["enumeracoes"], ["1", "2", "3"])
        self.assertEqual(campos["identificacao.consumidor_final"]["fonte_primaria"], "DECISAO_FISCAL")
        self.assertIn("DECISAO_PRESENCA_COMPRADOR_PENDENTE",
                      campos["identificacao.presenca_comprador"]["bloqueios_contextuais"])
        self.assertTrue(all(
            not item["valor_incluido"] and not item["elemento_xml_criado"]
            and not item["pronto_para_serializar"] for item in campos.values()
        ))

    def test_recusa_matriz_ou_plano_adulterado(self):
        matriz, plano = self.cadeia()
        matriz_ruim = deepcopy(matriz)
        matriz_ruim["conteudo"]["itens"][0]["fonte_primaria"] = "FONTE_INVENTADA"
        with self.assertRaisesMessage(ValueError, "matriz atômica deve estar íntegra"):
            construir_especificacao_ide_devolucao(matriz=matriz_ruim, plano_blocos=plano)
        plano_ruim = deepcopy(plano)
        plano_ruim["conteudo"]["blocos"][0]["campos"][0]["pronto_para_serializar"] = True
        with self.assertRaisesMessage(ValueError, "plano por blocos deve estar íntegro"):
            construir_especificacao_ide_devolucao(matriz=matriz, plano_blocos=plano_ruim)

    def test_validador_rejeita_formato_cardinalidade_bloqueio_e_liberacao(self):
        conteudo = deepcopy(self.resultado()["conteudo"])
        conteudo["campos"][0]["formato_xsd"]["maximo_caracteres"] = 120
        conteudo["campos"][1]["cardinalidade_xsd"]["minimo"] = 0
        conteudo["campos"][2]["bloqueios_contextuais"] = []
        conteudo["campos"][3]["valor_incluido"] = True
        conteudo["quantidade_campos"] = 4
        conteudo["politica"]["gerar_xml"] = True
        validacao = validar_especificacao_ide_devolucao(conteudo)
        self.assertFalse(validacao["estrutura_valida"])
        codigos = {erro["codigo"] for erro in validacao["erros"]}
        self.assertIn("DEFINICAO_XSD_DIVERGENTE", codigos)
        self.assertIn("CARDINALIDADE_DIVERGENTE", codigos)
        self.assertIn("BLOQUEIO_CONTEXTUAL_AUSENTE", codigos)
        self.assertIn("CAMPO_LIBERADO_INDEVIDAMENTE", codigos)
        self.assertIn("TOTAL_DIVERGENTE", codigos)
        self.assertIn("POLITICA_INVALIDA", codigos)
