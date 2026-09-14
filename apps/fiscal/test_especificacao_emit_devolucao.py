from copy import deepcopy
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from .compatibilidade_matriz_xsd import construir_compatibilidade_matriz_xsd
from .especificacao_emit_devolucao import (
    UFS_EMITENTE,
    construir_especificacao_emit_devolucao,
    validar_especificacao_emit_devolucao,
)
from .inventario_dados_devolucao import construir_inventario_dados_devolucao
from .matriz_atomica_devolucao import construir_matriz_atomica_devolucao
from .plano_blocos_xsd_devolucao import construir_plano_blocos_xsd


SHA_ZIP = "b8589490a58a09a993a80e6ac4d7ed10f20892061ecfc56719337098d4b95998"


class EspecificacaoEmitDevolucaoTests(SimpleTestCase):
    def cadeia(self):
        matriz = construir_matriz_atomica_devolucao(construir_inventario_dados_devolucao({}))
        compatibilidade = construir_compatibilidade_matriz_xsd(
            matriz=matriz,
            arquivo=Path(settings.BASE_DIR) / "docs/evidencias/nfe_2026_09_10/schemas_010f.zip",
            sha256_esperado=SHA_ZIP,
            versao="PL_010f_v1.04",
        )
        return matriz, construir_plano_blocos_xsd(matriz=matriz, compatibilidade=compatibilidade)

    def resultado(self):
        matriz, plano = self.cadeia()
        return construir_especificacao_emit_devolucao(matriz=matriz, plano_blocos=plano)

    def test_especifica_onze_campos_e_ordem_dos_subgrupos(self):
        resultado = self.resultado()
        self.assertTrue(resultado["validacao"]["estrutura_valida"])
        campos = {item["campo"]: item for item in resultado["conteudo"]["campos"]}
        self.assertEqual(resultado["conteudo"]["quantidade_campos"], 11)
        self.assertEqual(campos["emitente.cnpj"]["ordem_emit"], 1)
        self.assertEqual(campos["emitente.cnpj"]["cardinalidade_xsd"]["contexto"], "ESCOLHA_CNPJ_OU_CPF")
        self.assertEqual(campos["emitente.logradouro"]["ordem_emit"], 4)
        self.assertEqual(campos["emitente.logradouro"]["ordem_ender_emit"], 1)
        self.assertEqual(campos["emitente.cep"]["ordem_ender_emit"], 8)
        self.assertEqual(campos["emitente.crt"]["ordem_emit"], 8)

    def test_registra_formatos_e_lacunas_sem_alterar_cadastro(self):
        conteudo = self.resultado()["conteudo"]
        campos = {item["campo"]: item for item in conteudo["campos"]}
        self.assertEqual(campos["emitente.cnpj"]["formato_xsd"]["padrao"], "[0-9A-Z]{12}[0-9]{2}")
        self.assertIn("CNPJ_ALFANUMERICO_NAO_SUPORTADO", campos["emitente.cnpj"]["bloqueios_contextuais"])
        self.assertEqual(campos["emitente.inscricao_estadual"]["cardinalidade_xsd"]["minimo"], 0)
        self.assertEqual(campos["emitente.inscricao_estadual"]["formato_xsd"]["padrao"], "[0-9]{2,14}|ISENTO")
        self.assertEqual(campos["emitente.uf"]["formato_xsd"]["enumeracoes"], UFS_EMITENTE)
        self.assertEqual(campos["emitente.crt"]["formato_xsd"]["enumeracoes"], ["1", "2", "3", "4"])
        self.assertFalse(conteudo["politica"]["alterar_cadastro"])
        self.assertTrue(all(not item["valor_incluido"] and not item["elemento_xml_criado"]
                            and not item["pronto_para_serializar"] for item in campos.values()))

    def test_recusa_matriz_ou_plano_adulterado(self):
        matriz, plano = self.cadeia()
        matriz_ruim = deepcopy(matriz)
        matriz_ruim["conteudo"]["itens"][5]["destino_xml_futuro"] = "NFe/infNFe/emit/inventado"
        with self.assertRaisesMessage(ValueError, "matriz atômica deve estar íntegra"):
            construir_especificacao_emit_devolucao(matriz=matriz_ruim, plano_blocos=plano)
        plano_ruim = deepcopy(plano)
        plano_ruim["conteudo"]["blocos"][1]["pronto_para_construir"] = True
        with self.assertRaisesMessage(ValueError, "plano por blocos deve estar íntegro"):
            construir_especificacao_emit_devolucao(matriz=matriz, plano_blocos=plano_ruim)

    def test_validador_rejeita_definicao_lacuna_bloqueio_e_liberacao(self):
        conteudo = deepcopy(self.resultado()["conteudo"])
        conteudo["campos"][0]["formato_xsd"]["padrao"] = "[0-9]{14}"
        conteudo["campos"][1]["bloqueios_contextuais"] = []
        conteudo["campos"][2]["elemento_xml_criado"] = True
        conteudo["quantidade_campos"] = 10
        conteudo["lacunas_compatibilidade"] = []
        conteudo["politica"]["alterar_cadastro"] = True
        validacao = validar_especificacao_emit_devolucao(conteudo)
        self.assertFalse(validacao["estrutura_valida"])
        codigos = {erro["codigo"] for erro in validacao["erros"]}
        self.assertIn("DEFINICAO_XSD_DIVERGENTE", codigos)
        self.assertIn("BLOQUEIO_CONTEXTUAL_AUSENTE", codigos)
        self.assertIn("CAMPO_LIBERADO_INDEVIDAMENTE", codigos)
        self.assertIn("TOTAL_DIVERGENTE", codigos)
        self.assertIn("LACUNAS_INVALIDAS", codigos)
        self.assertIn("POLITICA_INVALIDA", codigos)
