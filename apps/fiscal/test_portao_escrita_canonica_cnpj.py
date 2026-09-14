from django.test import SimpleTestCase, override_settings

from .portao_escrita_canonica_cnpj import (
    descrever_portao_escrita_canonica_cnpj,
    preparar_escrita_canonica_cnpj,
)
from .test_support_identidades_fiscais import obter_identidade_fiscal_teste


@override_settings(ENVIRONMENT="test")
class PortaoEscritaCanonicaCNPJTests(SimpleTestCase):
    def identidade(self, codigo="FILIAL", *, mascarado=False):
        return obter_identidade_fiscal_teste(
            codigo, finalidade="TESTE_UNITARIO", mascarado=mascarado
        )

    def identidade_dv_invalido(self):
        valor = self.identidade()
        ultimo = "0" if valor[-1] != "0" else "1"
        return valor[:-1] + ultimo

    def test_criacao_prepara_canonico_sem_liberar_persistencia(self):
        mascarado = self.identidade(mascarado=True)
        resultado = preparar_escrita_canonica_cnpj(
            mascarado, fronteira="FILIAL", operacao="CRIACAO", empresa_id=7
        )
        self.assertEqual(resultado["status"], "CANONICO_PREPARADO")
        self.assertEqual(resultado["proposta"]["valor_canonico"], self.identidade())
        self.assertTrue(resultado["proposta"]["requer_consulta_colisao"])
        self.assertTrue(resultado["proposta"]["requer_verificacao_titularidade"])
        self.assertFalse(resultado["decisao"]["pode_persistir"])

    def test_normaliza_minusculas_sem_alterar_entrada(self):
        entrada = self.identidade(mascarado=True).lower()
        resultado = preparar_escrita_canonica_cnpj(
            entrada, fronteira="fornecedor_pj", operacao="criacao", empresa_id=7
        )
        self.assertEqual(resultado["status"], "CANONICO_PREPARADO")
        self.assertEqual(resultado["proposta"]["valor_canonico"], self.identidade())
        self.assertEqual(entrada, self.identidade(mascarado=True).lower())

    def test_recusa_fronteira_operacao_e_escopo_invalidos(self):
        valor = self.identidade()
        casos = (
            ({"fronteira": "OUTRA", "operacao": "CRIACAO"}, "FRONTEIRA_INVALIDA"),
            ({"fronteira": "EMPRESA", "operacao": "OUTRA"}, "OPERACAO_INVALIDA"),
            ({"fronteira": "FILIAL", "operacao": "CRIACAO"}, "ESCOPO_EMPRESA_OBRIGATORIO"),
        )
        for argumentos, status in casos:
            with self.subTest(status=status):
                resultado = preparar_escrita_canonica_cnpj(valor, **argumentos)
                self.assertEqual(resultado["status"], status)
                self.assertFalse(resultado["decisao"]["pode_persistir"])

    def test_recusa_formato_ou_dv_invalido(self):
        for valor in ("", "invalido", self.identidade_dv_invalido()):
            with self.subTest(valor=valor):
                resultado = preparar_escrita_canonica_cnpj(
                    valor, fronteira="EMPRESA", operacao="CRIACAO"
                )
                self.assertEqual(resultado["status"], "PROPOSTA_INVALIDA")

    def test_atualizacao_equivalente_nao_propoe_troca(self):
        resultado = preparar_escrita_canonica_cnpj(
            self.identidade(),
            fronteira="FILIAL", operacao="ATUALIZACAO", empresa_id=7,
            valor_atual=self.identidade(mascarado=True),
        )
        self.assertEqual(resultado["status"], "SEM_ALTERACAO_CANONICA")
        self.assertFalse(resultado["decisao"]["mudanca_identidade"])
        self.assertFalse(resultado["atual"]["valor_completo_exposto"])

    def test_atualizacao_exige_atual_valido_e_nao_corrige_legado(self):
        ausente = preparar_escrita_canonica_cnpj(
            self.identidade(), fronteira="FILIAL", operacao="ATUALIZACAO", empresa_id=7
        )
        invalido = preparar_escrita_canonica_cnpj(
            self.identidade(),
            fronteira="FILIAL", operacao="ATUALIZACAO", empresa_id=7,
            valor_atual=self.identidade_dv_invalido(),
        )
        self.assertEqual(ausente["status"], "VALOR_ATUAL_OBRIGATORIO")
        self.assertEqual(invalido["status"], "LEGADO_INVALIDO_REQUER_REVISAO")
        self.assertFalse(invalido["decisao"]["pode_corrigir_legado_automaticamente"])

    def test_troca_de_identidade_permanece_bloqueada(self):
        resultado = preparar_escrita_canonica_cnpj(
            self.identidade("FILIAL"),
            fronteira="FORNECEDOR_PJ", operacao="ATUALIZACAO", empresa_id=7,
            valor_atual=self.identidade("FORNECEDOR"),
        )
        self.assertEqual(resultado["status"], "TROCA_IDENTIDADE_REQUER_CONTROLES_EXTERNOS")
        self.assertTrue(resultado["decisao"]["mudanca_identidade"])
        self.assertFalse(resultado["decisao"]["pode_persistir"])

    def test_contrato_mantem_consumidores_e_canais_desligados(self):
        contrato = descrever_portao_escrita_canonica_cnpj()
        self.assertEqual(len(contrato["fronteiras"]), 4)
        self.assertTrue(contrato["estado"]["fase_4_estrutural_concluida"])
        self.assertTrue(contrato["regras"]["legado_invalido_nao_e_corrigido"])
        estados_bloqueados = {
            chave: valor
            for chave, valor in contrato["estado"].items()
            if chave != "fase_4_estrutural_concluida"
        }
        self.assertTrue(all(not valor for valor in estados_bloqueados.values()))
