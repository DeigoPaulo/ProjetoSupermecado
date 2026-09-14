from copy import deepcopy
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from .compatibilidade_matriz_xsd import construir_compatibilidade_matriz_xsd
from .especificacao_emit_devolucao import construir_especificacao_emit_devolucao
from .inventario_dados_devolucao import construir_inventario_dados_devolucao
from .matriz_atomica_devolucao import construir_matriz_atomica_devolucao
from .plano_blocos_xsd_devolucao import construir_plano_blocos_xsd
from .plano_compatibilidade_emitente_xsd import (
    construir_plano_compatibilidade_emitente_xsd,
    validar_plano_compatibilidade_emitente_xsd,
)


SHA_ZIP = "b8589490a58a09a993a80e6ac4d7ed10f20892061ecfc56719337098d4b95998"


class PlanoCompatibilidadeEmitenteXSDTests(SimpleTestCase):
    def especificacao(self):
        matriz = construir_matriz_atomica_devolucao(construir_inventario_dados_devolucao({}))
        compatibilidade = construir_compatibilidade_matriz_xsd(
            matriz=matriz,
            arquivo=Path(settings.BASE_DIR) / "docs/evidencias/nfe_2026_09_10/schemas_010f.zip",
            sha256_esperado=SHA_ZIP,
            versao="PL_010f_v1.04",
        )
        plano = construir_plano_blocos_xsd(matriz=matriz, compatibilidade=compatibilidade)
        return construir_especificacao_emit_devolucao(matriz=matriz, plano_blocos=plano)

    def resultado(self):
        return construir_plano_compatibilidade_emitente_xsd(self.especificacao())

    def test_organiza_cinco_frentes_seis_acoplamentos_e_seis_etapas(self):
        resultado = self.resultado()
        self.assertTrue(resultado["validacao"]["estrutura_valida"])
        self.assertEqual(resultado["validacao"]["quantidade_frentes"], 5)
        self.assertEqual(resultado["validacao"]["quantidade_pontos_acoplamento"], 6)
        self.assertEqual(resultado["validacao"]["quantidade_etapas"], 6)
        self.assertEqual(
            [item["ordem"] for item in resultado["conteudo"]["etapas"]],
            [1, 2, 3, 4, 5, 6],
        )

    def test_expoe_riscos_sem_liberar_migracao_gerador_ou_canal(self):
        conteudo = self.resultado()["conteudo"]
        frentes = {item["codigo"]: item for item in conteudo["frentes"]}
        self.assertEqual(frentes["CNPJ_ALFANUMERICO"]["migracao_banco"], "NAO_DEFINIDA")
        self.assertEqual(
            frentes["ENDEREMIT_GERADORES_EXISTENTES"]["estado_atual"],
            "AUSENTE_NOS_GERADORES_NFCE_E_NFE_PEDIDO_ONLINE",
        )
        self.assertTrue(all(not item["mudanca_liberada"] for item in conteudo["frentes"]))
        self.assertTrue(all(not item["alteracao_liberada"] for item in conteudo["pontos_acoplamento"]))
        self.assertTrue(all(not item["execucao_liberada"] for item in conteudo["etapas"]))
        self.assertTrue(all(valor is False for valor in conteudo["portoes"].values()))
        self.assertFalse(conteudo["politica"]["alterar_geradores"])
        self.assertFalse(conteudo["politica"]["contem_dados_reais"])

    def test_recusa_especificacao_emit_adulterada(self):
        especificacao = self.especificacao()
        especificacao["conteudo"]["campos"][0]["pronto_para_serializar"] = True
        with self.assertRaisesMessage(ValueError, "especificação de emit deve estar íntegra"):
            construir_plano_compatibilidade_emitente_xsd(especificacao)

    def test_validador_rejeita_frente_etapa_portao_e_politica_liberados(self):
        conteudo = deepcopy(self.resultado()["conteudo"])
        conteudo["frentes"][0]["mudanca_liberada"] = True
        conteudo["pontos_acoplamento"][0]["alteracao_liberada"] = True
        conteudo["etapas"][0]["execucao_liberada"] = True
        conteudo["portoes"]["regra_oficial_cnpj_confirmada"] = True
        conteudo["politica"]["criar_migracao"] = True
        validacao = validar_plano_compatibilidade_emitente_xsd(conteudo)
        self.assertFalse(validacao["estrutura_valida"])
        codigos = {erro["codigo"] for erro in validacao["erros"]}
        self.assertIn("FRENTE_DIVERGENTE_OU_LIBERADA", codigos)
        self.assertIn("ACOPLAMENTO_DIVERGENTE_OU_LIBERADO", codigos)
        self.assertIn("ETAPAS_DIVERGENTES_OU_LIBERADAS", codigos)
        self.assertIn("PORTOES_LIBERADOS_OU_INVALIDOS", codigos)
        self.assertIn("POLITICA_INVALIDA", codigos)
