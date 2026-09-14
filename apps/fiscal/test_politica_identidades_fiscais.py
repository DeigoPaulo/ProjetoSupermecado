from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import SimpleTestCase, TestCase, override_settings
from django.test.utils import CaptureQueriesContext

from apps.empresas.models import Empresa

from .politica_identidades_fiscais import (
    avaliar_comando_dados_ficticios,
    avaliar_uso_identidade_fiscal,
    construir_politica_identidades_fiscais,
)


class PoliticaIdentidadesFiscaisTests(SimpleTestCase):
    def test_dado_ficticio_so_tem_uso_local_nao_operacional(self):
        desenvolvimento = avaliar_uso_identidade_fiscal(
            "FICTICIO_DESENVOLVIMENTO",
            ambiente="development",
            finalidade="TESTE_INTEGRACAO_LOCAL",
        )
        producao = avaliar_uso_identidade_fiscal(
            "FICTICIO_DESENVOLVIMENTO",
            ambiente="production",
            finalidade="TESTE_INTEGRACAO_LOCAL",
        )
        self.assertTrue(desenvolvimento["uso_cadastral_permitido"])
        self.assertFalse(producao["uso_cadastral_permitido"])
        self.assertTrue(all(not valor for valor in producao["garantias"].values()))

    def test_exemplo_normativo_nao_prova_titularidade(self):
        resultado = avaliar_uso_identidade_fiscal(
            "EXEMPLO_NORMATIVO", ambiente="test", finalidade="TESTE_UNITARIO"
        )
        self.assertTrue(resultado["uso_cadastral_permitido"])
        self.assertEqual(resultado["motivo"], "EXEMPLO_SEM_PROVA_DE_TITULARIDADE")
        self.assertFalse(resultado["garantias"]["formato_valido_prova_titularidade"])
        self.assertFalse(resultado["garantias"]["exemplo_normativo_representa_empresa_do_cliente"])

    def test_identidade_real_pendente_permanece_bloqueada(self):
        resultado = avaliar_uso_identidade_fiscal(
            "REAL_PENDENTE", ambiente="production", finalidade="CADASTRO_OPERACIONAL"
        )
        self.assertFalse(resultado["uso_cadastral_permitido"])
        self.assertEqual(resultado["motivo"], "IDENTIDADE_REAL_AINDA_NAO_FORNECIDA_OU_VERIFICADA")

    def test_identidade_real_exige_titularidade_e_origem(self):
        incompleta = avaliar_uso_identidade_fiscal(
            "REAL_VERIFICADA", ambiente="production", finalidade="CADASTRO_OPERACIONAL",
            titularidade_verificada=True,
        )
        completa = avaliar_uso_identidade_fiscal(
            "REAL_VERIFICADA", ambiente="production", finalidade="CADASTRO_OPERACIONAL",
            titularidade_verificada=True, origem_documentada=True,
        )
        self.assertFalse(incompleta["uso_cadastral_permitido"])
        self.assertTrue(completa["uso_cadastral_permitido"])
        self.assertFalse(completa["garantias"]["politica_sozinha_libera_producao"])
        self.assertFalse(completa["garantias"]["dado_ficticio_pode_emitir"])

    def test_comandos_demo_sao_permitidos_apenas_em_desenvolvimento_e_teste(self):
        for comando in ("popular_demo", "criar_dados_iniciais"):
            with self.subTest(comando=comando):
                self.assertTrue(avaliar_comando_dados_ficticios(comando, "development")["permitido"])
                self.assertTrue(avaliar_comando_dados_ficticios(comando, "test")["permitido"])
                self.assertFalse(avaliar_comando_dados_ficticios(comando, "homologation")["permitido"])
                self.assertFalse(avaliar_comando_dados_ficticios(comando, "production")["permitido"])

    def test_contrato_registra_inventario_sem_liberar_canais(self):
        politica = construir_politica_identidades_fiscais()
        self.assertEqual(politica["inventario_2026_09_14"]["arquivos_teste_com_exemplos"], 48)
        self.assertEqual(politica["inventario_2026_09_14"]["arquivos_execucao_com_exemplos"], 3)
        self.assertEqual(politica["inventario_2026_09_14"]["arquivos_documentacao_com_exemplos"], 5)
        self.assertFalse(politica["estado"]["base_atual_alterada"])
        self.assertFalse(politica["estado"]["fixtures_existentes_reescritas"])
        self.assertFalse(politica["estado"]["cnpj_real_disponivel"])
        self.assertFalse(politica["estado"]["focus_ativado"])
        self.assertFalse(politica["estado"]["sefaz_direta_ativada"])
        self.assertFalse(politica["estado"]["emissao_liberada"])


class BloqueioComandosDadosFicticiosTests(TestCase):
    @override_settings(ENVIRONMENT="production")
    def test_producao_recusa_comandos_antes_de_qualquer_consulta_ou_escrita(self):
        for comando in ("popular_demo", "criar_dados_iniciais"):
            with self.subTest(comando=comando), CaptureQueriesContext(connection) as consultas:
                with self.assertRaises(CommandError):
                    call_command(comando)
            self.assertEqual(len(consultas), 0)
        self.assertEqual(Empresa.objects.count(), 0)

    @override_settings(ENVIRONMENT="homologation")
    def test_homologacao_tambem_recusa_dados_ficticios(self):
        with CaptureQueriesContext(connection) as consultas:
            with self.assertRaises(CommandError):
                call_command("popular_demo", "--simular")
        self.assertEqual(len(consultas), 0)
        self.assertEqual(Empresa.objects.count(), 0)
