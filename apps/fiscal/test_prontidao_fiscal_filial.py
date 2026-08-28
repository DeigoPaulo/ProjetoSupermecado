import json
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.empresas.models import Empresa, Filial

from .models import ConfiguracaoFiscal, NaturezaOperacao, SerieFiscal, TipoDocumentoFiscal
from .readiness import diagnostico_prontidao_homologacao_goias


FOCUS_ADAPTER = "apps.fiscal.focus_sefaz_adapter.FocusNFeSefazAdapter"
TOKEN_OUTRA_FILIAL = "token-outra-filial-nao-exibir"
TOKEN_FILIAL = "token-filial-piloto-nao-exibir"


@override_settings(
    FISCAL_SEFAZ_ADAPTER=FOCUS_ADAPTER,
    FOCUS_NFE_FISCAL_BASE_URL="https://homologacao.focusnfe.com.br",
    FOCUS_NFE_FISCAL_TOKEN="",
    FOCUS_NFE_FISCAL_ALLOW_PRODUCTION=False,
)
class ProntidaoFiscalFilialTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(
            razao_social="Mercado Piloto",
            nome_fantasia="Mercado Piloto",
            cnpj="12345678000195",
        )
        self.filial = Filial.objects.create(
            empresa=self.empresa,
            nome="Filial Piloto",
            cnpj="12345678000195",
            uf="GO",
            codigo_municipio_ibge="5208707",
        )
        self.configuracao = ConfiguracaoFiscal.objects.create(
            filial=self.filial,
            inscricao_estadual="109876543",
            csc_id="1",
            csc_token="csc-protegido",
            certificado_nome="piloto.pfx",
            certificado_validade=timezone.localdate() + timedelta(days=365),
            certificado_a1_criptografado=b"certificado",
            certificado_senha_criptografada=b"senha",
        )
        SerieFiscal.objects.create(
            filial=self.filial,
            tipo_documento=TipoDocumentoFiscal.NFCE,
            serie=1,
        )
        NaturezaOperacao.objects.create(
            empresa=self.empresa,
            descricao="Venda ao consumidor",
            tipo_documento=TipoDocumentoFiscal.NFCE,
            ativo=True,
            padrao=True,
        )

    def item(self, diagnostico, titulo):
        return next(
            item for item in diagnostico["checklist"] if item["titulo"] == titulo
        )

    @patch("apps.fiscal.readiness.pendencias_endpoints_nfce", return_value=[])
    @override_settings(
        FOCUS_NFE_FISCAL_TOKENS={"12345678000195": TOKEN_FILIAL}
    )
    def test_ambiente_producao_nao_passa_no_preflight_de_homologacao(
        self, _endpoints
    ):
        self.configuracao.ambiente = "PRODUCAO"
        self.configuracao.save(update_fields=["ambiente"])

        diagnostico = diagnostico_prontidao_homologacao_goias(self.configuracao)

        self.assertFalse(self.item(diagnostico, "Ambiente de homologação")["pronto"])

    @patch("apps.fiscal.readiness.pendencias_endpoints_nfce", return_value=[])
    @override_settings(
        FOCUS_NFE_FISCAL_TOKENS={"99999999000199": TOKEN_OUTRA_FILIAL}
    )
    def test_token_de_outra_filial_nao_libera_filial_piloto(self, _endpoints):
        diagnostico = diagnostico_prontidao_homologacao_goias(self.configuracao)

        self.assertFalse(
            self.item(diagnostico, "Configuração do adaptador")["pronto"]
        )
        self.assertNotIn(TOKEN_OUTRA_FILIAL, json.dumps(diagnostico))

    @patch("apps.fiscal.readiness.pendencias_endpoints_nfce", return_value=[])
    @override_settings(
        FOCUS_NFE_FISCAL_TOKENS={"12345678000195": TOKEN_FILIAL}
    )
    def test_token_da_filial_libera_apenas_configuracao_operacional(
        self, _endpoints
    ):
        diagnostico = diagnostico_prontidao_homologacao_goias(self.configuracao)

        self.assertTrue(
            self.item(diagnostico, "Configuração do adaptador")["pronto"]
        )
        self.assertFalse(diagnostico["pronto"])
        self.assertEqual(diagnostico["filial"]["cnpj_final"], "0195")
        self.assertNotIn(TOKEN_FILIAL, json.dumps(diagnostico))

    @patch("apps.fiscal.readiness.pendencias_endpoints_nfce", return_value=[])
    @override_settings(
        FOCUS_NFE_FISCAL_TOKENS={"12345678000195": TOKEN_FILIAL}
    )
    def test_comando_estrito_exibe_pendencias_sem_segredos(self, _endpoints):
        saida = StringIO()

        with self.assertRaisesMessage(CommandError, "prontidão fiscal"):
            call_command(
                "verificar_prontidao_fiscal",
                "--filial-id",
                str(self.filial.pk),
                "--estrito",
                stdout=saida,
            )

        texto = saida.getvalue()
        resultado = json.loads(texto)
        self.assertFalse(resultado["pronto"])
        self.assertIn("Evidência de homologação", texto)
        self.assertNotIn(TOKEN_FILIAL, texto)
        self.assertNotIn("csc-protegido", texto)
