from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from apps.empresas.services_lookup import diagnostico_prontidao_consulta_cadastro


class ConsultaCadastroReadinessTests(TestCase):
    @override_settings(
        CADASTRO_CNPJ_PROVIDER_URL="",
        CADASTRO_CEP_PROVIDER_URL="",
    )
    def test_modo_estrito_bloqueia_quando_so_existe_fallback_local(self):
        diagnostico = diagnostico_prontidao_consulta_cadastro()
        self.assertEqual(diagnostico["prontidao"]["status"], "local_fallback_only")
        self.assertFalse(diagnostico["prontidao"]["pronto_homologacao"])
        with self.assertRaises(CommandError):
            call_command("verificar_prontidao_consulta_cadastro", "--estrito", stdout=StringIO())

    @override_settings(
        CADASTRO_CNPJ_PROVIDER_URL="http://interno.example/cnpj/{cnpj}",
        CADASTRO_CEP_PROVIDER_URL="https://cep.example/{cep}",
    )
    def test_url_http_nao_e_considerada_pronta(self):
        diagnostico = diagnostico_prontidao_consulta_cadastro()
        self.assertFalse(diagnostico["provedores"]["cnpj_https"])
        self.assertTrue(diagnostico["provedores"]["cep_https"])
        self.assertFalse(diagnostico["prontidao"]["pronto_homologacao"])

    @override_settings(
        CADASTRO_CNPJ_PROVIDER_URL="https://cadastro.example/cnpj/{cnpj}",
        CADASTRO_CEP_PROVIDER_URL="https://cep.example/{cep}",
        CADASTRO_LOOKUP_TIMEOUT_SEGUNDOS=3,
    )
    def test_modo_estrito_aceita_dois_provedores_https_sem_expor_urls(self):
        saida = StringIO()
        call_command("verificar_prontidao_consulta_cadastro", "--estrito", "--json", stdout=saida)
        conteudo = saida.getvalue()
        self.assertIn("cadastro_lookup_readiness_v1", conteudo)
        self.assertIn('"pronto_homologacao": true', conteudo)
        self.assertNotIn("cadastro.example", conteudo)
        self.assertNotIn("cep.example", conteudo)
