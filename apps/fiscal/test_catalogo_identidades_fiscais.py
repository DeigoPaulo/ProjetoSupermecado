from django.test import SimpleTestCase, override_settings

from .estrategia_normalizacao_cnpj import canonicalizar_cnpj, validar_dv_cnpj
from .test_support_identidades_fiscais import (
    UsoIdentidadeTesteNegado,
    descrever_catalogo_identidades_teste,
    obter_identidade_fiscal_teste,
)


@override_settings(ENVIRONMENT="test")
class CatalogoIdentidadesFiscaisTesteTests(SimpleTestCase):
    def test_catalogo_e_deterministico_valido_e_separa_papeis(self):
        valores = {
            obter_identidade_fiscal_teste(
                codigo, finalidade="TESTE_UNITARIO"
            )
            for codigo in ("EMPRESA_MATRIZ", "FILIAL", "FORNECEDOR", "CLIENTE_PJ")
        }
        self.assertEqual(len(valores), 4)
        self.assertTrue(all(validar_dv_cnpj(valor) for valor in valores))
        self.assertTrue(all(valor.startswith("TST") for valor in valores))

    @override_settings(ENVIRONMENT="development")
    def test_forma_mascarada_preserva_a_identidade_canonica(self):
        pura = obter_identidade_fiscal_teste(
            "EMPRESA_MATRIZ", finalidade="TESTE_INTEGRACAO_LOCAL"
        )
        mascarada = obter_identidade_fiscal_teste(
            "EMPRESA_MATRIZ", finalidade="TESTE_INTEGRACAO_LOCAL", mascarado=True,
        )
        self.assertEqual(canonicalizar_cnpj(mascarada), pura)

    def test_homologacao_e_producao_sao_recusadas(self):
        for ambiente in ("homologation", "production"):
            with self.subTest(ambiente=ambiente), override_settings(ENVIRONMENT=ambiente):
                with self.assertRaises(UsoIdentidadeTesteNegado):
                    obter_identidade_fiscal_teste("EMPRESA_MATRIZ", finalidade="TESTE_UNITARIO")

    @override_settings(ENVIRONMENT="development")
    def test_finalidade_operacional_e_recusada_mesmo_em_desenvolvimento(self):
        with self.assertRaisesMessage(
            UsoIdentidadeTesteNegado, "FINALIDADE_FORA_DO_CATALOGO_DE_TESTES"
        ):
            obter_identidade_fiscal_teste(
                "EMPRESA_MATRIZ", finalidade="CADASTRO_OPERACIONAL"
            )

    def test_codigo_desconhecido_e_recusado(self):
        with self.assertRaisesMessage(UsoIdentidadeTesteNegado, "IDENTIDADE_TESTE_DESCONHECIDA"):
            obter_identidade_fiscal_teste(
                "OUTRO", finalidade="TESTE_UNITARIO"
            )

    def test_descricao_nao_expoe_documentos_e_nao_libera_canais(self):
        descricao = descrever_catalogo_identidades_teste()
        self.assertEqual(descricao["quantidade"], 5)
        self.assertFalse(descricao["valores_expostos"])
        self.assertFalse(descricao["distribuicao_producao"])
        self.assertTrue(all(not valor for valor in descricao["garantias"].values()))
