from django.test import SimpleTestCase, override_settings

from .portao_leitura_dupla_cnpj import (
    descrever_portao_leitura_dupla_cnpj,
    resolver_cnpj_por_leitura_dupla,
)
from .test_support_identidades_fiscais import obter_identidade_fiscal_teste


class PortaoLeituraDuplaCNPJTests(SimpleTestCase):
    def registro(self, identificador, valor, *, fronteira="FILIAL", empresa_id=1):
        return {
            "origem": fronteira.title(),
            "identificador": identificador,
            "empresa_id": empresa_id,
            "fronteira": fronteira,
            "valor": valor,
        }

    def test_encontra_forma_legada_por_canonico_sem_alterar_entrada(self):
        registros = [self.registro(7, "04.252.011/0001-10")]
        resultado = resolver_cnpj_por_leitura_dupla(
            "04252011000110", registros, fronteira="FILIAL", empresa_id=1
        )
        self.assertEqual(resultado["status"], "ENCONTRADO_UNICO")
        self.assertEqual(resultado["identificador"], "7")
        self.assertFalse(resultado["diagnostico"]["match_textual_exato"])
        self.assertTrue(resultado["diagnostico"]["cadastro_diverge_do_canonico"])
        self.assertEqual(registros[0]["valor"], "04.252.011/0001-10")

    @override_settings(ENVIRONMENT="test")
    def test_novo_caso_usa_catalogo_sem_expor_ou_persistir_identidade(self):
        cnpj_puro = obter_identidade_fiscal_teste(
            "FILIAL", finalidade="TESTE_UNITARIO"
        )
        cnpj_mascarado = obter_identidade_fiscal_teste(
            "FILIAL", finalidade="TESTE_UNITARIO", mascarado=True
        )
        registros = [self.registro("catalogo-filial", cnpj_mascarado)]

        resultado = resolver_cnpj_por_leitura_dupla(
            cnpj_puro, registros, fronteira="FILIAL", empresa_id=1
        )

        self.assertEqual(resultado["status"], "ENCONTRADO_UNICO")
        self.assertEqual(resultado["identificador"], "catalogo-filial")
        self.assertTrue(resultado["diagnostico"]["cadastro_diverge_do_canonico"])
        self.assertNotIn(cnpj_puro, str(resultado))
        self.assertNotIn(cnpj_mascarado, str(resultado))
        self.assertEqual(registros[0]["valor"], cnpj_mascarado)

    def test_recusa_ambiguidade_mesmo_com_um_match_textual_exato(self):
        registros = [
            self.registro(7, "04.252.011/0001-10"),
            self.registro(8, "04252011000110"),
        ]
        resultado = resolver_cnpj_por_leitura_dupla(
            "04252011000110", registros, fronteira="FILIAL", empresa_id=1
        )
        self.assertEqual(resultado["status"], "AMBIGUO")
        self.assertFalse(resultado["encontrou"])
        self.assertEqual(resultado["identificador"], "")
        self.assertEqual(resultado["diagnostico"]["quantidade_matches_textuais"], 1)
        self.assertEqual(resultado["diagnostico"]["quantidade_matches_canonicos"], 2)

    def test_isola_fronteira_e_empresa_antes_de_comparar(self):
        registros = [
            self.registro(1, "04.252.011/0001-10", fronteira="EMPRESA", empresa_id=""),
            self.registro(2, "04.252.011/0001-10", empresa_id=1),
            self.registro(3, "04.252.011/0001-10", empresa_id=2),
        ]
        resultado = resolver_cnpj_por_leitura_dupla(
            "04.252.011/0001-10", registros, fronteira="FILIAL", empresa_id=2
        )
        self.assertEqual(resultado["status"], "ENCONTRADO_UNICO")
        self.assertEqual(resultado["identificador"], "3")
        self.assertEqual(resultado["empresa_id"], "2")

    def test_exige_escopo_quando_a_fronteira_possui_empresa(self):
        resultado = resolver_cnpj_por_leitura_dupla(
            "04.252.011/0001-10", [self.registro(1, "04252011000110")],
            fronteira="FILIAL",
        )
        self.assertEqual(resultado["status"], "ESCOPO_EMPRESA_OBRIGATORIO")
        self.assertFalse(resultado["encontrou"])

    def test_recusa_consulta_formato_ou_dv_invalido(self):
        registros = [self.registro(1, "04.252.011/0001-10")]
        for consulta in ("invalido", "04.252.011/0001-11", ""):
            with self.subTest(consulta=consulta):
                resultado = resolver_cnpj_por_leitura_dupla(
                    consulta, registros, fronteira="FILIAL", empresa_id=1
                )
                self.assertEqual(resultado["status"], "CONSULTA_INVALIDA")
                self.assertEqual(resultado["identificador"], "")

    def test_ignora_cadastro_invalido_sem_corrigir_silenciosamente(self):
        registros = [
            self.registro(1, "04.252.011/0001-11"),
            self.registro(2, "04.252.011/0001-10"),
        ]
        resultado = resolver_cnpj_por_leitura_dupla(
            "04252011000110", registros, fronteira="FILIAL", empresa_id=1
        )
        self.assertEqual(resultado["status"], "ENCONTRADO_UNICO")
        self.assertEqual(resultado["identificador"], "2")
        self.assertEqual(resultado["diagnostico"]["quantidade_cadastros_invalidos_ignorados"], 1)

    def test_recusa_candidato_malformado_ou_sem_identidade(self):
        sem_identificador = self.registro("", "04.252.011/0001-10")
        registros = ["entrada-invalida", sem_identificador, self.registro(2, "04252011000110")]
        resultado = resolver_cnpj_por_leitura_dupla(
            "04.252.011/0001-10", registros, fronteira="FILIAL", empresa_id=1
        )
        self.assertEqual(resultado["status"], "ENCONTRADO_UNICO")
        self.assertEqual(resultado["identificador"], "2")
        self.assertEqual(resultado["diagnostico"]["quantidade_cadastros_invalidos_ignorados"], 2)

    def test_nao_expoe_cnpj_e_nao_consulta_ou_altera_banco(self):
        cnpj = "12.ABC.345/01DE-35"
        resultado = resolver_cnpj_por_leitura_dupla(
            cnpj, [self.registro(1, cnpj, fronteira="CREDENCIAL")],
            fronteira="CREDENCIAL", empresa_id=1,
        )
        self.assertNotIn(cnpj, str(resultado))
        self.assertTrue(resultado["encontrou"])
        self.assertTrue(all(not valor for valor in resultado["seguranca"].values()))

    def test_contrato_mantem_integracoes_e_consumidores_desligados(self):
        contrato = descrever_portao_leitura_dupla_cnpj()
        self.assertEqual(len(contrato["fronteiras"]), 4)
        self.assertTrue(contrato["regras"]["match_textual_nao_desambigua"])
        self.assertTrue(contrato["estado"]["funcao_pura_isolada"])
        self.assertFalse(contrato["estado"]["consumidor_operacional_alterado"])
        self.assertFalse(contrato["estado"]["focus_ativado"])
        self.assertFalse(contrato["estado"]["sefaz_direta_ativada"])
        self.assertFalse(contrato["estado"]["emissao_liberada"])

    def test_recusa_fronteira_desconhecida_e_conjunto_invalido(self):
        resultado = resolver_cnpj_por_leitura_dupla(
            "04.252.011/0001-10", [], fronteira="QUALQUER"
        )
        self.assertEqual(resultado["status"], "FRONTEIRA_INVALIDA")
        resultado = resolver_cnpj_por_leitura_dupla(
            "04.252.011/0001-10", None, fronteira="EMPRESA"
        )
        self.assertEqual(resultado["status"], "CONJUNTO_INVALIDO")
