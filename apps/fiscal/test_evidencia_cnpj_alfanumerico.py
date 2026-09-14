from copy import deepcopy
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from .compatibilidade_matriz_xsd import construir_compatibilidade_matriz_xsd
from .especificacao_emit_devolucao import construir_especificacao_emit_devolucao
from .evidencia_cnpj_alfanumerico import (
    construir_evidencia_cnpj_alfanumerico,
    validar_evidencia_cnpj_alfanumerico,
)
from .inventario_dados_devolucao import construir_inventario_dados_devolucao
from .matriz_atomica_devolucao import construir_matriz_atomica_devolucao
from .plano_blocos_xsd_devolucao import construir_plano_blocos_xsd
from .plano_compatibilidade_emitente_xsd import construir_plano_compatibilidade_emitente_xsd


SHA_ZIP = "b8589490a58a09a993a80e6ac4d7ed10f20892061ecfc56719337098d4b95998"


class EvidenciaCNPJAlfanumericoTests(SimpleTestCase):
    def plano(self):
        matriz = construir_matriz_atomica_devolucao(construir_inventario_dados_devolucao({}))
        compatibilidade = construir_compatibilidade_matriz_xsd(
            matriz=matriz,
            arquivo=Path(settings.BASE_DIR) / "docs/evidencias/nfe_2026_09_10/schemas_010f.zip",
            sha256_esperado=SHA_ZIP,
            versao="PL_010f_v1.04",
        )
        plano_blocos = construir_plano_blocos_xsd(matriz=matriz, compatibilidade=compatibilidade)
        especificacao = construir_especificacao_emit_devolucao(
            matriz=matriz, plano_blocos=plano_blocos
        )
        return construir_plano_compatibilidade_emitente_xsd(especificacao)

    def resultado(self):
        return construir_evidencia_cnpj_alfanumerico(self.plano(), settings.BASE_DIR)

    def test_confirma_formato_dv_coexistencia_e_vigencia(self):
        resultado = self.resultado()
        self.assertTrue(resultado["validacao"]["estrutura_valida"])
        self.assertEqual(resultado["validacao"]["quantidade_fontes"], 5)
        self.assertEqual(resultado["validacao"]["quantidade_impactos"], 7)
        conteudo = resultado["conteudo"]
        self.assertEqual(conteudo["regras_cnpj"]["expressao_regular"], r"[A-Z0-9]{12}[0-9]{2}")
        self.assertTrue(conteudo["regras_cnpj"]["formatos_coexistem"])
        self.assertEqual(conteudo["vigencia"]["nfce_nfe_producao"], "2026-07-01")

    def test_confirma_chave_alfanumerica_de_44_posicoes_e_ascii_menos_48(self):
        chave = self.resultado()["conteudo"]["regras_chave_acesso"]
        self.assertEqual(chave["tamanho"], 44)
        self.assertEqual(chave["expressao_regular"], r"[0-9]{6}[A-Z0-9]{12}[0-9]{26}")
        self.assertEqual(chave["valor_caractere_para_dv"], "ASCII_MENOS_48")
        self.assertEqual(chave["codigo_barras"], "CODE_128_HIBRIDO_C_E_A_QUANDO_HOUVER_LETRAS")

    def test_conclui_somente_etapa_normativa_sem_liberar_operacao(self):
        resultado = self.resultado()
        conteudo = resultado["conteudo"]
        self.assertTrue(conteudo["conclusao"]["etapa_normativa_concluida"])
        self.assertFalse(conteudo["conclusao"]["compatibilidade_semantica_atual"])
        self.assertEqual(
            conteudo["proximo_passo"], "DEFINIR_NORMALIZACAO_CANONICA_E_RETROCOMPATIBILIDADE"
        )
        self.assertTrue(all(not item["alteracao_liberada"] for item in conteudo["impactos"]))
        self.assertTrue(all(valor is False for valor in conteudo["politica"].values()))
        self.assertFalse(resultado["validacao"]["permite_emissao"])

    def test_recusa_plano_adulterado_e_fonte_ausente(self):
        plano = self.plano()
        plano["conteudo"]["portoes"]["regra_oficial_cnpj_confirmada"] = True
        with self.assertRaisesMessage(ValueError, "plano de compatibilidade deve estar integro"):
            construir_evidencia_cnpj_alfanumerico(plano, settings.BASE_DIR)
        with self.assertRaisesMessage(ValueError, "Evidencia oficial ausente ou adulterada"):
            construir_evidencia_cnpj_alfanumerico(self.plano(), Path(settings.BASE_DIR) / "inexistente")

    def test_validador_rejeita_regra_fonte_impacto_conclusao_e_politica_adulterados(self):
        conteudo = deepcopy(self.resultado()["conteudo"])
        conteudo["fontes"][0]["sha256"] = "0" * 64
        conteudo["regras_cnpj"]["expressao_regular"] = r"[0-9]{14}"
        conteudo["regras_chave_acesso"]["tamanho"] = 43
        conteudo["vigencia"]["nfce_nfe_producao"] = "2026-01-01"
        conteudo["impactos"][0]["alteracao_liberada"] = True
        conteudo["conclusao"]["compatibilidade_semantica_atual"] = True
        conteudo["politica"]["emitir"] = True
        validacao = validar_evidencia_cnpj_alfanumerico(conteudo)
        self.assertFalse(validacao["estrutura_valida"])
        codigos = {item["codigo"] for item in validacao["erros"]}
        self.assertTrue({
            "FONTES_DIVERGENTES", "REGRA_CNPJ_DIVERGENTE", "REGRA_CHAVE_DIVERGENTE",
            "VIGENCIA_DIVERGENTE", "IMPACTOS_DIVERGENTES_OU_LIBERADOS",
            "CONCLUSAO_DIVERGENTE", "POLITICA_INVALIDA",
        }.issubset(codigos))
