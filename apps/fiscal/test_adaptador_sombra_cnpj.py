import json

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from apps.empresas.models import Empresa, Filial

from .adaptador_sombra_cnpj import (
    ensaiar_adaptador_sombra_empresa_filial,
    observar_busca_empresa_ativa_por_cnpj,
    observar_busca_filial_da_empresa_por_cnpj,
)


class AdaptadorSombraCNPJTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(
            razao_social="Empresa Sombra",
            nome_fantasia="Empresa Sombra",
            cnpj="04.252.011/0001-10",
        )
        self.outra_empresa = Empresa.objects.create(
            razao_social="Empresa Alfa",
            nome_fantasia="Empresa Alfa",
            cnpj="12.ABC.345/01DE-35",
        )
        self.filial = Filial.objects.create(
            empresa=self.empresa,
            nome="Matriz",
            cnpj="04.252.011/0001-10",
        )

    def test_observa_forma_canonica_sem_substituir_busca_exata(self):
        resultado = observar_busca_empresa_ativa_por_cnpj("04252011000110")
        self.assertEqual(resultado["classificacao"], "CANONICO_ENCONTRA_LEGADO_NAO")
        self.assertFalse(resultado["legado_encontrou"])
        self.assertTrue(resultado["portao_encontrou"])
        self.assertFalse(resultado["seguranca"]["substitui_busca_atual"])
        self.assertFalse(resultado["seguranca"]["resultado_operacional_alterado"])

    def test_recusa_ambiguidade_canonica_sem_expor_ids(self):
        duplicada = Empresa.objects.create(
            razao_social="Duplicada",
            nome_fantasia="Duplicada",
            cnpj="04252011000110",
        )
        resultado = observar_busca_empresa_ativa_por_cnpj("04252011000110")
        self.assertEqual(resultado["classificacao"], "AMBIGUIDADE_CANONICA")
        self.assertTrue(resultado["legado_encontrou"])
        self.assertFalse(resultado["portao_encontrou"])
        self.assertNotIn("identificador", resultado)
        self.assertNotIn("empresa_id", resultado)
        self.assertFalse(resultado["seguranca"]["identificador_interno_exposto"])

    def test_registra_quando_legado_aceita_dv_invalido(self):
        Empresa.objects.create(
            razao_social="Desenvolvimento",
            nome_fantasia="Desenvolvimento",
            cnpj="11.111.111/0001-11",
        )
        resultado = observar_busca_empresa_ativa_por_cnpj("11.111.111/0001-11")
        self.assertEqual(resultado["classificacao"], "LEGADO_SELECIONA_PORTAO_RECUSA")
        self.assertEqual(resultado["portao_status"], "CONSULTA_INVALIDA")

    def test_filial_respeita_escopo_da_empresa(self):
        Filial.objects.create(
            empresa=self.outra_empresa,
            nome="Outra Matriz",
            cnpj="04252011000110",
        )
        resultado = observar_busca_filial_da_empresa_por_cnpj(
            "04252011000110", empresa_id=self.empresa.pk
        )
        self.assertEqual(resultado["classificacao"], "CANONICO_ENCONTRA_LEGADO_NAO")
        self.assertTrue(resultado["portao_encontrou"])

    def test_filial_recusa_escopo_ausente_sem_consultar_banco(self):
        with CaptureQueriesContext(connection) as consultas:
            resultado = observar_busca_filial_da_empresa_por_cnpj(
                "04.252.011/0001-10", empresa_id=None
            )
        self.assertEqual(len(consultas), 0)
        self.assertEqual(resultado["portao_status"], "ESCOPO_EMPRESA_OBRIGATORIO")
        self.assertFalse(resultado["portao_encontrou"])

    def test_observadores_executam_exclusivamente_select(self):
        cnpj_antes = Empresa.objects.get(pk=self.empresa.pk).cnpj
        with CaptureQueriesContext(connection) as consultas:
            observar_busca_empresa_ativa_por_cnpj("04.252.011/0001-10")
            observar_busca_filial_da_empresa_por_cnpj(
                "04.252.011/0001-10", empresa_id=self.empresa.pk
            )
        self.assertTrue(consultas)
        self.assertTrue(all(item["sql"].lstrip().upper().startswith("SELECT") for item in consultas))
        self.assertEqual(Empresa.objects.get(pk=self.empresa.pk).cnpj, cnpj_antes)

    def test_ensaio_agrega_sem_expor_detalhes_ou_documentos(self):
        with CaptureQueriesContext(connection) as consultas:
            resultado = ensaiar_adaptador_sombra_empresa_filial()
        self.assertEqual(resultado["base"], "ENSAIO_LOCAL_NAO_ACEITE_PRODUCAO")
        self.assertEqual(resultado["resumo"]["total_observacoes"], 3)
        self.assertNotIn(self.empresa.cnpj, json.dumps(resultado))
        self.assertTrue(all(item["sql"].lstrip().upper().startswith("SELECT") for item in consultas))
        self.assertFalse(resultado["seguranca"]["detalhes_individuais_expostos"])
        self.assertFalse(resultado["seguranca"]["aceite_producao"])
        self.assertFalse(resultado["seguranca"]["libera_licenca"])
        self.assertFalse(resultado["seguranca"]["libera_emissao"])

    def test_empresa_inativa_nao_participa_das_duas_leituras(self):
        self.empresa.is_active = False
        self.empresa.save(update_fields=["is_active"])
        resultado = observar_busca_empresa_ativa_por_cnpj("04.252.011/0001-10")
        self.assertEqual(resultado["classificacao"], "AMBOS_NAO_SELECIONAM")
        self.assertFalse(resultado["legado_encontrou"])
        self.assertFalse(resultado["portao_encontrou"])
