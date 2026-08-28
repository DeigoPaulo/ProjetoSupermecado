import json
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings


FOCUS_ADAPTER = "apps.fiscal.focus_sefaz_adapter.FocusNFeSefazAdapter"
TOKEN_TESTE = "token-super-secreto-nao-exibir"


class ProntidaoFocusCommandTests(SimpleTestCase):
    @override_settings(
        FISCAL_SEFAZ_ADAPTER=FOCUS_ADAPTER,
        FOCUS_NFE_FISCAL_BASE_URL="https://homologacao.focusnfe.com.br",
        FOCUS_NFE_FISCAL_TOKEN="",
        FOCUS_NFE_FISCAL_TOKENS={},
        FOCUS_NFE_FISCAL_ALLOW_PRODUCTION=False,
    )
    def test_exigencia_operacional_bloqueia_focus_sem_token(self):
        saida = StringIO()

        call_command(
            "validar_adaptador_sefaz",
            "--exigir-eventos",
            "--exigir-configuracao",
            stdout=saida,
        )

        resultado = json.loads(saida.getvalue())
        operacional = resultado["configuracao_operacional"]
        self.assertFalse(resultado["pronto"])
        self.assertTrue(operacional["diagnostico_disponivel"])
        self.assertFalse(operacional["credenciais_configuradas"])
        self.assertFalse(operacional["pronto"])
        self.assertIn("Credenciais", " ".join(resultado["pendencias"]))

    @override_settings(
        FISCAL_SEFAZ_ADAPTER=FOCUS_ADAPTER,
        FOCUS_NFE_FISCAL_BASE_URL="https://homologacao.focusnfe.com.br",
        FOCUS_NFE_FISCAL_TOKEN=TOKEN_TESTE,
        FOCUS_NFE_FISCAL_TOKENS={},
        FOCUS_NFE_FISCAL_ALLOW_PRODUCTION=False,
    )
    def test_token_sandbox_libera_prontidao_local_sem_expor_segredo(self):
        saida = StringIO()

        call_command(
            "validar_adaptador_sefaz",
            "--exigir-eventos",
            "--exigir-configuracao",
            "--estrito",
            stdout=saida,
        )

        texto = saida.getvalue()
        resultado = json.loads(texto)
        operacional = resultado["configuracao_operacional"]
        self.assertTrue(resultado["pronto"])
        self.assertTrue(operacional["credenciais_configuradas"])
        self.assertTrue(operacional["pronto"])
        self.assertEqual(operacional["ambiente"], "homologacao")
        self.assertFalse(operacional["producao_habilitada"])
        self.assertNotIn(TOKEN_TESTE, texto)

    @override_settings(
        FISCAL_SEFAZ_ADAPTER="apps.fiscal.tests.FakeSefazAdapter",
    )
    def test_modo_estrito_recusa_adaptador_sem_diagnostico_operacional(self):
        with self.assertRaisesMessage(CommandError, "diagnóstico operacional"):
            call_command(
                "validar_adaptador_sefaz",
                "--exigir-configuracao",
                "--estrito",
                stdout=StringIO(),
            )
