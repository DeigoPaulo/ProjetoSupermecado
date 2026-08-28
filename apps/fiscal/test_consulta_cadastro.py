from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase, override_settings
from lxml import etree

from apps.auditoria.models import LogAuditoria
from apps.empresas.models import Empresa, Filial

from .cadastro_adapters import (
    CONTRATO_CONSULTA_CADASTRO,
    normalizar_retorno_consulta_cadastro,
)
from .models import (
    AmbienteFiscal,
    ConfiguracaoFiscal,
    ConsultaCadastroContribuinte,
    StatusConsultaCadastro,
    TipoDocumentoConsultaCadastro,
)
from .sefaz_direta.adapter import NFE_NS
from .sefaz_direta.cadastro import SefazDiretaConsultaCadastroAdapter
from .services_cadastro import consultar_cadastro_contribuinte


CNPJ = "12345678000195"


@override_settings(
    SEFAZ_DIRETA_CADASTRO_NETWORK_ENABLED=True,
    SEFAZ_DIRETA_CADASTRO_ALLOW_PRODUCTION=False,
)
class SefazDiretaConsultaCadastroAdapterTests(SimpleTestCase):
    def filial(self, ambiente=AmbienteFiscal.HOMOLOGACAO):
        configuracao = SimpleNamespace(ambiente=ambiente)
        return SimpleNamespace(
            uf="GO",
            cnpj=CNPJ,
            empresa=SimpleNamespace(cnpj=CNPJ),
            configuracao_fiscal=configuracao,
        )

    def test_monta_consulta_e_normaliza_ocorrencia_de_goias(self):
        chamadas = []
        retorno = f"""<retConsCad xmlns="{NFE_NS}" versao="2.00">
          <infCons>
            <verAplic>GO4.00</verAplic>
            <cStat>111</cStat>
            <xMotivo>Consulta cadastro com uma ocorrência</xMotivo>
            <UF>GO</UF>
            <infCad>
              <IE>109876543</IE>
              <CNPJ>{CNPJ}</CNPJ>
              <UF>GO</UF>
              <cSit>1</cSit>
              <indCredNFe>1</indCredNFe>
              <indCredCTe>0</indCredCTe>
              <xNome>Mercado Cadastro Ltda</xNome>
              <xRegApur>Normal</xRegApur>
              <CNAE>4711302</CNAE>
              <ender>
                <xLgr>Rua de Homologação</xLgr>
                <nro>100</nro>
                <xBairro>Centro</xBairro>
                <cMun>5208707</cMun>
                <xMun>Goiânia</xMun>
                <CEP>74000000</CEP>
              </ender>
            </infCad>
          </infCons>
        </retConsCad>"""

        def transport(**kwargs):
            chamadas.append(kwargs)
            return retorno

        resultado = SefazDiretaConsultaCadastroAdapter(
            transport=transport
        ).consultar(
            filial=self.filial(),
            uf="go",
            tipo_documento="CNPJ",
            documento="12.345.678/0001-95",
        )

        self.assertEqual(resultado["contrato"], CONTRATO_CONSULTA_CADASTRO)
        self.assertEqual(resultado["status"], "SUCESSO")
        self.assertEqual(resultado["codigo_status"], "111")
        self.assertEqual(resultado["ocorrencias"][0]["ie"], "109876543")
        self.assertEqual(
            resultado["ocorrencias"][0]["endereco"]["municipio"], "Goiânia"
        )
        self.assertEqual(
            chamadas[0]["endpoint"],
            "https://homolog.sefaz.go.gov.br/nfe/services/CadConsultaCadastro4",
        )
        envelope = etree.fromstring(chamadas[0]["envelope"])
        self.assertEqual(
            envelope.xpath("string(.//*[local-name()='ConsCad']/@versao)"),
            "2.00",
        )
        self.assertEqual(
            envelope.xpath("string(.//*[local-name()='xServ'])"), "CONS-CAD"
        )
        self.assertEqual(
            envelope.xpath("string(.//*[local-name()='CNPJ'])"), CNPJ
        )

    def test_rede_e_producao_permanecem_bloqueadas_separadamente(self):
        with override_settings(SEFAZ_DIRETA_CADASTRO_NETWORK_ENABLED=False):
            with self.assertRaisesMessage(Exception, "Rede da consulta cadastral"):
                SefazDiretaConsultaCadastroAdapter().consultar(
                    filial=self.filial(),
                    uf="GO",
                    tipo_documento="IE",
                    documento="109876543",
                )

        with self.assertRaisesMessage(Exception, "Produção"):
            SefazDiretaConsultaCadastroAdapter().consultar(
                filial=self.filial(AmbienteFiscal.PRODUCAO),
                uf="GO",
                tipo_documento="IE",
                documento="109876543",
            )

    def test_rejeita_uf_e_documento_fora_do_contrato(self):
        adaptador = SefazDiretaConsultaCadastroAdapter()
        with self.assertRaisesMessage(ValidationError, "apenas para GO"):
            adaptador.consultar(
                filial=self.filial(),
                uf="SP",
                tipo_documento="CNPJ",
                documento=CNPJ,
            )
        with self.assertRaisesMessage(ValidationError, "CNPJ inválido"):
            adaptador.consultar(
                filial=self.filial(),
                uf="GO",
                tipo_documento="CNPJ",
                documento="123",
            )

    def test_normalizador_recusa_contrato_e_ocorrencias_invalidos(self):
        with self.assertRaisesMessage(ValidationError, "Contrato cadastral"):
            normalizar_retorno_consulta_cadastro(
                {"contrato": "outro", "status": "SUCESSO"}
            )
        with self.assertRaisesMessage(ValidationError, "ocorrências cadastrais"):
            normalizar_retorno_consulta_cadastro(
                {
                    "contrato": CONTRATO_CONSULTA_CADASTRO,
                    "status": "SUCESSO",
                    "ocorrencias": {"invalida": True},
                }
            )


class FakeConsultaCadastroAdapter:
    falhar = False
    chamadas = []

    def consultar(self, **kwargs):
        type(self).chamadas.append(kwargs)
        if type(self).falhar:
            raise ConnectionError("SEFAZ cadastral indisponível para teste.")
        return {
            "contrato": CONTRATO_CONSULTA_CADASTRO,
            "status": "SUCESSO",
            "codigo_status": "111",
            "mensagem": "111 - Consulta cadastro com uma ocorrência",
            "ocorrencias": [
                {
                    "ie": "109876543",
                    "cnpj": CNPJ,
                    "uf": "GO",
                    "razao_social": "Mercado Cadastro Ltda",
                }
            ],
            "xml_envio": "<ConsCad/>",
            "xml_retorno": "<retConsCad/>",
        }


@override_settings(
    FISCAL_CONSULTA_CADASTRO_ADAPTER=(
        "apps.fiscal.test_consulta_cadastro.FakeConsultaCadastroAdapter"
    )
)
class ConsultaCadastroServiceTests(TestCase):
    def setUp(self):
        FakeConsultaCadastroAdapter.falhar = False
        FakeConsultaCadastroAdapter.chamadas = []
        self.usuario = get_user_model().objects.create_superuser(
            "fiscal-cadastro", "cadastro@example.com", "123"
        )
        self.empresa = Empresa.objects.create(
            razao_social="Mercado Cadastro",
            nome_fantasia="Mercado Cadastro",
            cnpj=CNPJ,
        )
        self.filial = Filial.objects.create(
            empresa=self.empresa,
            nome="Matriz",
            cnpj=CNPJ,
            uf="GO",
        )
        ConfiguracaoFiscal.objects.create(
            filial=self.filial,
            ambiente=AmbienteFiscal.HOMOLOGACAO,
        )

    def consultar(self):
        return consultar_cadastro_contribuinte(
            filial=self.filial,
            uf="GO",
            tipo_documento=TipoDocumentoConsultaCadastro.CNPJ,
            documento="12.345.678/0001-95",
            usuario=self.usuario,
            ip="127.0.0.1",
        )

    def test_persiste_resultado_normalizado_e_auditoria(self):
        consulta = self.consultar()

        self.assertEqual(consulta.status, StatusConsultaCadastro.SUCESSO)
        self.assertEqual(consulta.documento, CNPJ)
        self.assertEqual(consulta.codigo_status, "111")
        self.assertEqual(consulta.ocorrencias[0]["ie"], "109876543")
        self.assertEqual(consulta.xml_envio, "<ConsCad/>")
        self.assertIsNotNone(consulta.processado_em)
        self.assertEqual(FakeConsultaCadastroAdapter.chamadas[0]["uf"], "GO")
        self.assertTrue(
            LogAuditoria.objects.filter(
                acao="CONSULTA_CADASTRO",
                objeto_id=str(consulta.pk),
                ip="127.0.0.1",
            ).exists()
        )

    def test_preserva_falha_para_diagnostico_e_auditoria(self):
        FakeConsultaCadastroAdapter.falhar = True

        with self.assertRaisesMessage(
            ValidationError, "SEFAZ cadastral indisponível"
        ):
            self.consultar()

        consulta = ConsultaCadastroContribuinte.objects.get()
        self.assertEqual(consulta.status, StatusConsultaCadastro.ERRO)
        self.assertIn("indisponível", consulta.mensagem)
        self.assertIsNotNone(consulta.processado_em)
        self.assertTrue(
            LogAuditoria.objects.filter(
                acao="CONSULTA_CADASTRO_ERRO",
                objeto_id=str(consulta.pk),
            ).exists()
        )

    @override_settings(FISCAL_CONSULTA_CADASTRO_ADAPTER="")
    def test_sem_adaptador_nao_cria_historico_falso(self):
        with self.assertRaisesMessage(ValidationError, "não possui adaptador"):
            self.consultar()
        self.assertFalse(ConsultaCadastroContribuinte.objects.exists())
