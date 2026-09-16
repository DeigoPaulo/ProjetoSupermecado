from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext

from apps.empresas.models import Empresa, Filial, ModoImplantacao

from .adaptador_sombra_escrita_cnpj import (
    descrever_adaptador_sombra_escrita_cnpj,
    observar_escrita_empresa,
    observar_escrita_filial,
)
from .test_support_identidades_fiscais import obter_identidade_fiscal_teste


@override_settings(ENVIRONMENT="test")
class AdaptadorSombraEscritaCNPJTests(TestCase):
    def identidade(self, codigo, *, mascarado=False):
        return obter_identidade_fiscal_teste(
            codigo, finalidade="TESTE_UNITARIO", mascarado=mascarado
        )

    def dados_empresa(self, cnpj):
        return {
            "razao_social": "Empresa observada",
            "nome_fantasia": "Empresa observada",
            "cnpj": cnpj,
            "modo_implantacao": ModoImplantacao.LOCAL,
            "is_active": "on",
        }

    def dados_filial(self, empresa, cnpj, *, nome="Filial observada"):
        return {
            "empresa": empresa.pk,
            "nome": nome,
            "cnpj": cnpj,
            "is_active": "on",
        }

    def assertSomenteSelect(self, consultas):
        self.assertTrue(consultas)
        self.assertTrue(
            all(item["sql"].lstrip().upper().startswith("SELECT") for item in consultas)
        )

    def test_empresa_valida_concorda_sem_gravar(self):
        antes = Empresa.objects.count()
        with CaptureQueriesContext(connection) as consultas:
            resultado = observar_escrita_empresa(
                self.dados_empresa(self.identidade("EMPRESA_MATRIZ", mascarado=True))
            )
        self.assertEqual(resultado["classificacao"], "CONCORDAM_ESTRUTURALMENTE")
        self.assertEqual(Empresa.objects.count(), antes)
        self.assertSomenteSelect(consultas.captured_queries)

    def test_formulario_integrado_e_portao_recusam_dv_invalido(self):
        cnpj = self.identidade("EMPRESA_MATRIZ")
        invalido = cnpj[:-1] + ("0" if cnpj[-1] != "0" else "1")
        resultado = observar_escrita_empresa(self.dados_empresa(invalido))
        self.assertEqual(resultado["classificacao"], "AMBOS_RECUSAM")
        self.assertFalse(resultado["formulario_atual"]["valido"])
        self.assertEqual(resultado["proposta_canonica"]["status"], "PROPOSTA_INVALIDA")

    def test_empresa_detecta_colisao_ignorada_pela_unicidade_textual(self):
        Empresa.objects.create(
            razao_social="Existente",
            nome_fantasia="Existente",
            cnpj=self.identidade("EMPRESA_MATRIZ", mascarado=True),
        )
        resultado = observar_escrita_empresa(
            self.dados_empresa(self.identidade("EMPRESA_MATRIZ"))
        )
        self.assertEqual(resultado["classificacao"], "COLISAO_CANONICA_DETECTADA")
        self.assertFalse(resultado["formulario_atual"]["valido"])
        self.assertEqual(resultado["proposta_canonica"]["quantidade_colisoes"], 1)

    def test_filial_detecta_colisao_no_escopo_da_empresa(self):
        empresa = Empresa.objects.create(
            razao_social="Matriz",
            nome_fantasia="Matriz",
            cnpj=self.identidade("EMPRESA_MATRIZ"),
        )
        Filial.objects.create(
            empresa=empresa,
            nome="Existente",
            cnpj=self.identidade("FILIAL", mascarado=True),
        )
        resultado = observar_escrita_filial(
            self.dados_filial(empresa, self.identidade("FILIAL"))
        )
        self.assertEqual(resultado["classificacao"], "COLISAO_CANONICA_DETECTADA")
        self.assertFalse(resultado["formulario_atual"]["valido"])
        self.assertEqual(resultado["proposta_canonica"]["quantidade_colisoes"], 1)

    def test_atualizacao_equivalente_exclui_a_propria_identidade(self):
        empresa = Empresa.objects.create(
            razao_social="Atualizada",
            nome_fantasia="Atualizada",
            cnpj=self.identidade("EMPRESA_MATRIZ", mascarado=True),
        )
        resultado = observar_escrita_empresa(
            self.dados_empresa(self.identidade("EMPRESA_MATRIZ")), instance=empresa
        )
        self.assertEqual(resultado["classificacao"], "CONCORDAM_ESTRUTURALMENTE")
        self.assertEqual(resultado["proposta_canonica"]["status"], "SEM_ALTERACAO_CANONICA")
        self.assertEqual(empresa.cnpj, self.identidade("EMPRESA_MATRIZ", mascarado=True))
        empresa.refresh_from_db()
        self.assertEqual(empresa.cnpj, self.identidade("EMPRESA_MATRIZ", mascarado=True))

    def test_diagnostico_nao_expoe_cnpj_nem_identificador(self):
        cnpj = self.identidade("EMPRESA_MATRIZ")
        resultado = observar_escrita_empresa(self.dados_empresa(cnpj))
        representacao = repr(resultado)
        self.assertNotIn(cnpj, representacao)
        self.assertFalse(resultado["seguranca"]["cnpj_completo_exposto"])
        self.assertFalse(resultado["seguranca"]["chama_save"])

    def test_contrato_registra_integracao_e_pontos_reais(self):
        contrato = descrever_adaptador_sombra_escrita_cnpj()
        self.assertEqual(contrato["fronteiras"], ["EMPRESA", "FILIAL"])
        self.assertTrue(all(contrato["integracao_atual"].values()))
        self.assertEqual(len(contrato["pontos_integracao"]), 2)
