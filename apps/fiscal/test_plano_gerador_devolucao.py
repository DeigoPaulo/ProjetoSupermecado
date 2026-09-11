from copy import deepcopy

from django.test import SimpleTestCase

from .inventario_dados_devolucao import construir_inventario_dados_devolucao
from .matriz_atomica_devolucao import construir_matriz_atomica_devolucao
from .plano_gerador_devolucao import (
    ESTADO_ORDEM_XSD,
    ORDEM_ESTRUTURAL_XSD,
    construir_plano_gerador_offline,
    validar_plano_gerador_offline,
)


class PlanoGeradorDevolucaoTests(SimpleTestCase):
    def resultado(self):
        inventario = construir_inventario_dados_devolucao({})
        matriz = construir_matriz_atomica_devolucao(inventario)
        return {"matriz_atomica": matriz}

    def test_recusa_entrada_e_documenta_ordem_sem_produzir_xml(self):
        resultado = construir_plano_gerador_offline(self.resultado())
        self.assertTrue(resultado["validacao"]["estrutura_valida"])
        self.assertEqual(
            resultado["validacao"]["quantidade_etapas"],
            len(ORDEM_ESTRUTURAL_XSD),
        )
        self.assertFalse(resultado["conteudo"]["entrada_aceita"])
        self.assertTrue(resultado["conteudo"]["politica"]["ordem_confirmada_na_evidencia"])
        self.assertFalse(resultado["conteudo"]["politica"]["ordem_aprovada_para_gerador"])
        self.assertFalse(resultado["conteudo"]["politica"]["produzir_xml"])
        self.assertFalse(resultado["validacao"]["permite_focus"])
        self.assertFalse(resultado["validacao"]["permite_sefaz_direta"])
        codigos = {item["codigo"] for item in resultado["conteudo"]["bloqueios"]}
        self.assertIn("CAMPO_NAO_DISPONIVEL_PARA_GERADOR", codigos)
        self.assertIn("XSD_APLICAVEL_NAO_INSTALADO", codigos)
        self.assertIn("XSD_APLICAVEL_NAO_APROVADO", codigos)
        self.assertIn("ORDEM_NAO_APROVADA_PARA_GERADOR", codigos)
        self.assertIn("SERIALIZADOR_OFFLINE_NAO_IMPLEMENTADO", codigos)

    def test_ordem_reproduz_os_21_blocos_e_cardinalidades_do_xsd(self):
        conteudo = construir_plano_gerador_offline(self.resultado())["conteudo"]
        self.assertEqual(
            [item["elemento"] for item in conteudo["ordem_estrutural"]],
            [
                "ide", "emit", "avulsa", "dest", "retirada", "entrega",
                "autXML", "det", "total", "transp", "cobr", "pag",
                "infIntermed", "infAdic", "exporta", "compra", "cana",
                "infRespTec", "infSolicNFF", "agropecuario", "infPAA",
            ],
        )
        self.assertEqual(
            (conteudo["ordem_estrutural"][7]["min_ocorrencias"],
             conteudo["ordem_estrutural"][7]["max_ocorrencias"]),
            ("1", "990"),
        )
        self.assertTrue(all(
            item["estado"] == ESTADO_ORDEM_XSD
            for item in conteudo["ordem_estrutural"]
        ))
        evidencia = conteudo["evidencia_xsd"]
        self.assertTrue(evidencia["evidencia_arquivada"])
        self.assertTrue(evidencia["hash_reproduzivel"])
        self.assertFalse(evidencia["instalado_em_fiscal_schemas"])
        self.assertFalse(evidencia["pacote_aprovado"])

    def test_rejeita_liberacao_ou_remocao_de_bloqueio_estrutural(self):
        conteudo = deepcopy(construir_plano_gerador_offline(self.resultado())["conteudo"])
        conteudo["entrada_aceita"] = True
        conteudo["politica"]["produzir_xml"] = True
        conteudo["ordem_estrutural"].reverse()
        conteudo["bloqueios"] = [
            item for item in conteudo["bloqueios"]
            if item["codigo"] != "XSD_APLICAVEL_NAO_INSTALADO"
        ]
        validacao = validar_plano_gerador_offline(conteudo)
        self.assertFalse(validacao["estrutura_valida"])
        codigos = {item["codigo"] for item in validacao["erros"]}
        self.assertIn("ENTRADA_NAO_PODE_SER_LIBERADA", codigos)
        self.assertIn("POLITICA_DE_BLOQUEIO_INVALIDA", codigos)
        self.assertIn("ORDEM_DIVERGENTE", codigos)
        self.assertIn("BLOQUEIO_ESTRUTURAL_REMOVIDO", codigos)