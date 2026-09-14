from copy import deepcopy
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from .compatibilidade_matriz_xsd import construir_compatibilidade_matriz_xsd
from .especificacao_emit_devolucao import construir_especificacao_emit_devolucao
from .evidencia_cnpj_alfanumerico import construir_evidencia_cnpj_alfanumerico
from .estrategia_normalizacao_cnpj import (
    analisar_identidades_cnpj,
    calcular_dv_chave_acesso,
    calcular_dv_cnpj,
    canonicalizar_cnpj,
    construir_estrategia_normalizacao_cnpj,
    validar_chave_acesso,
    validar_dv_cnpj,
    validar_estrategia_normalizacao_cnpj,
)
from .inventario_dados_devolucao import construir_inventario_dados_devolucao
from .matriz_atomica_devolucao import construir_matriz_atomica_devolucao
from .plano_blocos_xsd_devolucao import construir_plano_blocos_xsd
from .plano_compatibilidade_emitente_xsd import construir_plano_compatibilidade_emitente_xsd


SHA_ZIP = "b8589490a58a09a993a80e6ac4d7ed10f20892061ecfc56719337098d4b95998"


class EstrategiaNormalizacaoCNPJTests(SimpleTestCase):
    def evidencia(self):
        matriz = construir_matriz_atomica_devolucao(construir_inventario_dados_devolucao({}))
        compatibilidade = construir_compatibilidade_matriz_xsd(
            matriz=matriz,
            arquivo=Path(settings.BASE_DIR) / "docs/evidencias/nfe_2026_09_10/schemas_010f.zip",
            sha256_esperado=SHA_ZIP,
            versao="PL_010f_v1.04",
        )
        plano_blocos = construir_plano_blocos_xsd(matriz=matriz, compatibilidade=compatibilidade)
        especificacao = construir_especificacao_emit_devolucao(matriz=matriz, plano_blocos=plano_blocos)
        plano = construir_plano_compatibilidade_emitente_xsd(especificacao)
        return construir_evidencia_cnpj_alfanumerico(plano, settings.BASE_DIR)

    def resultado(self):
        return construir_estrategia_normalizacao_cnpj(self.evidencia())

    def test_canonicaliza_formato_numerico_e_alfanumerico_sem_perder_zeros(self):
        self.assertEqual(canonicalizar_cnpj("04.252.011/0001-10"), "04252011000110")
        self.assertEqual(canonicalizar_cnpj(" 12.abc.345/01de-35 "), "12ABC34501DE35")
        self.assertEqual(canonicalizar_cnpj("00ABC000000001"), "00ABC000000001")

    def test_recusa_mascara_livre_unicode_e_dv_alfanumerico(self):
        for valor in ("12-ABC-345-01DE-35", "12.ABC.345/01DE/35", "12ÁBC34501DE35", "12ABC34501DEFG"):
            with self.subTest(valor=valor), self.assertRaises(ValueError):
                canonicalizar_cnpj(valor)
        self.assertEqual(calcular_dv_cnpj("12ABC34501DE"), "35")
        self.assertTrue(validar_dv_cnpj("12.ABC.345/01DE-35"))
        self.assertFalse(validar_dv_cnpj("12.ABC.345/01DE-36"))

    def test_calcula_e_valida_chave_alfanumerica_de_44_posicoes(self):
        base = "52260912ABC34501DE3555001000000001112345678"
        self.assertEqual(len(base), 43)
        chave = base + calcular_dv_chave_acesso(base)
        self.assertEqual(len(chave), 44)
        self.assertTrue(validar_chave_acesso(chave.lower()))
        self.assertFalse(validar_chave_acesso(chave[:-1] + str((int(chave[-1]) + 1) % 10)))

    def test_previa_detecta_colisoes_invalidos_e_vazios_sem_alterar(self):
        registros = [
            {"origem": "Empresa", "identificador": 1, "cnpj": "04.252.011/0001-10"},
            {"origem": "Filial", "identificador": 2, "cnpj": "04252011000110"},
            {"origem": "Fornecedor", "identificador": 3, "cnpj": "12.abc.345/01de-35"},
            {"origem": "Fornecedor", "identificador": 4, "cnpj": "12ABC34501DE35"},
            {"origem": "Fornecedor", "identificador": 5, "cnpj": "invalido"},
            {"origem": "Cliente", "identificador": 6, "cnpj": ""},
        ]
        previa = analisar_identidades_cnpj(registros)
        self.assertEqual(len(previa["colisoes"]), 2)
        self.assertEqual(len(previa["invalidos"]), 1)
        self.assertEqual(len(previa["vazios"]), 1)
        self.assertFalse(previa["altera_dados"])
        self.assertEqual(registros[2]["cnpj"], "12.abc.345/01de-35")

    def test_mapeia_consumidores_e_fases_sem_liberar_troca(self):
        resultado = self.resultado()
        self.assertTrue(resultado["validacao"]["estrutura_valida"])
        self.assertEqual(resultado["validacao"]["quantidade_consumidores"], 23)
        self.assertEqual(resultado["validacao"]["quantidade_fases"], 6)
        conteudo = resultado["conteudo"]
        self.assertTrue(conteudo["conclusao"]["estrategia_definida"])
        self.assertFalse(conteudo["conclusao"]["consumidor_operacional_alterado"])
        self.assertTrue(all(not item["alteracao_liberada"] for item in conteudo["consumidores"]))
        self.assertTrue(all(not item["execucao_operacional_liberada"] for item in conteudo["fases"]))
        self.assertTrue(all(valor is False for valor in conteudo["politica"].values()))

    def test_recusa_evidencia_e_contrato_adulterados(self):
        evidencia = self.evidencia()
        evidencia["conteudo"]["vigencia"]["nfce_nfe_producao"] = "2026-01-01"
        with self.assertRaisesMessage(ValueError, "evidencia normativa deve estar integra"):
            construir_estrategia_normalizacao_cnpj(evidencia)

        conteudo = deepcopy(self.resultado()["conteudo"])
        conteudo["representacao"]["remove_somente"].append("_")
        conteudo["compatibilidade"]["fallback_para_normalizador_antigo"] = True
        conteudo["consumidores"][0]["alteracao_liberada"] = True
        conteudo["fases"][1]["execucao_operacional_liberada"] = True
        conteudo["politica"]["normalizar_dados"] = True
        validacao = validar_estrategia_normalizacao_cnpj(conteudo)
        self.assertFalse(validacao["estrutura_valida"])
        codigos = {item["codigo"] for item in validacao["erros"]}
        self.assertTrue({
            "REPRESENTACAO_DIVERGENTE", "COMPATIBILIDADE_DIVERGENTE",
            "CONSUMIDORES_DIVERGENTES_OU_LIBERADOS", "FASES_DIVERGENTES_OU_LIBERADAS",
            "POLITICA_INVALIDA",
        }.issubset(codigos))
