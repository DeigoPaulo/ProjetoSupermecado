from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from lxml import etree

from apps.accounts.models import PerfilUsuario, TipoPerfil
from apps.auditoria.models import LogAuditoria
from apps.empresas.models import Empresa, Filial

from .manifestacao_adapters import CONTRATO_MANIFESTACAO_DESTINATARIO
from .models import (
    AmbienteFiscal,
    ConfiguracaoFiscal,
    DocumentoDFeRecebido,
    ManifestacaoDestinatario,
    StatusManifestacaoDestinatario,
    TipoManifestacaoDestinatario,
)
from .services_manifestacao import registrar_manifestacao_destinatario
from .sefaz_direta import NFE_NS, SefazDiretaManifestacaoAdapter

CHAVE = "52260812345678000123550010000001231000001234"
CNPJ = "12345678000199"


@override_settings(
    SEFAZ_DIRETA_MANIFESTACAO_NETWORK_ENABLED=True,
    SEFAZ_DIRETA_MANIFESTACAO_ALLOW_PRODUCTION=False,
    SEFAZ_DIRETA_MANIFESTACAO_ENDPOINTS={},
)
class SefazDiretaManifestacaoAdapterTests(SimpleTestCase):
    def test_monta_assina_e_envia_evento_ao_ambiente_nacional(self):
        chamadas = []
        retorno = f'''<retEnvEvento xmlns="{NFE_NS}" versao="1.00">
          <cStat>128</cStat><xMotivo>Lote processado</xMotivo>
          <retEvento><infEvento><cStat>135</cStat><xMotivo>Evento registrado e vinculado a NF-e</xMotivo>
          <nProt>135260000000001</nProt></infEvento></retEvento>
        </retEnvEvento>'''

        def transport(**kwargs):
            chamadas.append(kwargs)
            return retorno

        configuracao = SimpleNamespace(
            ambiente=AmbienteFiscal.HOMOLOGACAO,
            filial=SimpleNamespace(cnpj=CNPJ, empresa=SimpleNamespace(cnpj=CNPJ)),
        )
        documento = SimpleNamespace(
            pk=7,
            chave_acesso=CHAVE,
            filial_destino=SimpleNamespace(configuracao_fiscal=configuracao),
        )
        adaptador = SefazDiretaManifestacaoAdapter(transport=transport)
        with patch(
            "apps.fiscal.sefaz_direta.manifestacao.assinar_xml_elemento_fiscal",
            side_effect=lambda xml, *args, **kwargs: xml,
        ):
            resultado = adaptador.manifestar(
                documento=documento,
                tipo=TipoManifestacaoDestinatario.OPERACAO_NAO_REALIZADA,
                justificativa="Mercadoria recusada no recebimento.",
                idempotency_key="teste-7",
            )

        self.assertEqual(resultado["status"], "AUTORIZADA")
        self.assertEqual(resultado["codigo_status"], "135")
        self.assertEqual(
            chamadas[0]["endpoint"],
            "https://hom1.nfe.fazenda.gov.br/NFeRecepcaoEvento4/NFeRecepcaoEvento4.asmx",
        )
        envelope = etree.fromstring(chamadas[0]["envelope"])
        self.assertEqual(envelope.xpath("string(.//*[local-name()='cOrgao'])"), "91")
        self.assertEqual(envelope.xpath("string(.//*[local-name()='tpEvento'])"), "210240")
        self.assertEqual(
            envelope.xpath("string(.//*[local-name()='xJust'])"),
            "Mercadoria recusada no recebimento.",
        )

    def test_producao_permanece_bloqueada(self):
        configuracao = SimpleNamespace(
            ambiente=AmbienteFiscal.PRODUCAO,
            filial=SimpleNamespace(cnpj=CNPJ, empresa=SimpleNamespace(cnpj=CNPJ)),
        )
        documento = SimpleNamespace(
            pk=8, chave_acesso=CHAVE,
            filial_destino=SimpleNamespace(configuracao_fiscal=configuracao),
        )
        with self.assertRaisesMessage(Exception, "Produção"):
            SefazDiretaManifestacaoAdapter().manifestar(
                documento=documento,
                tipo=TipoManifestacaoDestinatario.CIENCIA,
                idempotency_key="teste-8",
            )


class FakeManifestacaoAdapter:
    chamadas = []

    def manifestar(self, **kwargs):
        type(self).chamadas.append(kwargs)
        return {
            "contrato": CONTRATO_MANIFESTACAO_DESTINATARIO,
            "status": "AUTORIZADA",
            "codigo_status": "135",
            "protocolo": "135260000000001",
            "mensagem": "Evento registrado e vinculado à NF-e.",
            "xml_envio": "<envEvento/>",
            "xml_retorno": "<retEnvEvento/>",
        }

    def diagnosticar(self):
        return {"disponivel": True, "mensagem": "Teste controlado."}


@override_settings(
    FISCAL_MANIFESTACAO_ADAPTER=(
        "apps.fiscal.test_manifestacao_destinatario.FakeManifestacaoAdapter"
    )
)
class ManifestacaoDestinatarioServiceTests(TestCase):
    def setUp(self):
        FakeManifestacaoAdapter.chamadas = []
        self.usuario = get_user_model().objects.create_superuser(
            "manifestador", "manifestador@example.com", "123"
        )
        self.empresa = Empresa.objects.create(
            razao_social="Mercado Manifestação",
            nome_fantasia="Mercado Manifestação",
            cnpj=CNPJ,
        )
        self.filial = Filial.objects.create(
            empresa=self.empresa, nome="Matriz", cnpj=CNPJ, uf="GO"
        )
        ConfiguracaoFiscal.objects.create(
            filial=self.filial, ambiente=AmbienteFiscal.HOMOLOGACAO
        )
        self.documento = DocumentoDFeRecebido.objects.create(
            empresa=self.empresa,
            filial_destino=self.filial,
            chave_acesso=CHAVE,
            data_emissao=timezone.localdate(),
            origem="DISTRIBUICAO",
        )

    def test_ciencia_e_depois_manifestacao_conclusiva(self):
        ciencia = registrar_manifestacao_destinatario(
            self.documento,
            tipo=TipoManifestacaoDestinatario.CIENCIA,
            usuario=self.usuario,
        )
        conclusiva = registrar_manifestacao_destinatario(
            self.documento,
            tipo=TipoManifestacaoDestinatario.CONFIRMACAO,
            usuario=self.usuario,
        )
        self.assertEqual(ciencia.status, StatusManifestacaoDestinatario.AUTORIZADA)
        self.assertEqual(conclusiva.status, StatusManifestacaoDestinatario.AUTORIZADA)
        self.assertEqual(ManifestacaoDestinatario.objects.count(), 2)
        self.assertEqual(LogAuditoria.objects.filter(acao="MANIFESTACAO_DESTINATARIO").count(), 2)
        with self.assertRaisesMessage(ValidationError, "já possui manifestação conclusiva"):
            registrar_manifestacao_destinatario(
                self.documento,
                tipo=TipoManifestacaoDestinatario.DESCONHECIMENTO,
                usuario=self.usuario,
            )

    def test_operacao_nao_realizada_exige_justificativa(self):
        with self.assertRaisesMessage(ValidationError, "15 e 255"):
            registrar_manifestacao_destinatario(
                self.documento,
                tipo=TipoManifestacaoDestinatario.OPERACAO_NAO_REALIZADA,
                justificativa="Curta",
                usuario=self.usuario,
            )

    def test_prazo_conclusivo_de_noventa_dias(self):
        self.documento.data_emissao = timezone.localdate() - timedelta(days=91)
        self.documento.save(update_fields=["data_emissao"])
        with self.assertRaisesMessage(ValidationError, "90 dias"):
            registrar_manifestacao_destinatario(
                self.documento,
                tipo=TipoManifestacaoDestinatario.CONFIRMACAO,
                usuario=self.usuario,
            )

    def test_tela_e_xml_respeitam_escopo_da_empresa(self):
        manifestacao = registrar_manifestacao_destinatario(
            self.documento,
            tipo=TipoManifestacaoDestinatario.CIENCIA,
            usuario=self.usuario,
        )
        self.client.force_login(self.usuario)
        tela = self.client.get(reverse("fiscal:dfe_detalhe", args=[self.documento.pk]))
        self.assertEqual(tela.status_code, 200)
        self.assertContains(tela, "Manifestação do Destinatário")
        download = self.client.get(
            reverse(
                "fiscal:dfe_manifestacao_baixar_xml",
                args=[manifestacao.pk, "retorno"],
            )
        )
        self.assertEqual(download.status_code, 200)
        self.assertIn(b"retEnvEvento", download.content)

    def test_sem_configuracao_fiscal_ativa_falha_com_mensagem_controlada(self):
        ConfiguracaoFiscal.objects.filter(filial=self.filial).delete()
        with self.assertRaisesMessage(ValidationError, "configuração fiscal ativa"):
            registrar_manifestacao_destinatario(
                self.documento,
                tipo=TipoManifestacaoDestinatario.CIENCIA,
                usuario=self.usuario,
            )

    def test_administrador_de_outra_empresa_nao_acessa_documento_nem_xml(self):
        manifestacao = registrar_manifestacao_destinatario(
            self.documento,
            tipo=TipoManifestacaoDestinatario.CIENCIA,
            usuario=self.usuario,
        )
        outra_empresa = Empresa.objects.create(
            razao_social="Outro Mercado",
            nome_fantasia="Outro Mercado",
            cnpj="98765432000188",
        )
        outra_filial = Filial.objects.create(
            empresa=outra_empresa,
            nome="Outra Matriz",
            cnpj="98765432000188",
            uf="GO",
        )
        administrador = get_user_model().objects.create_user(
            "admin-externo", "externo@example.com", "123"
        )
        PerfilUsuario.objects.create(
            usuario=administrador,
            filial=outra_filial,
            tipo=TipoPerfil.ADMINISTRADOR,
        )
        self.client.force_login(administrador)

        detalhe = self.client.get(
            reverse("fiscal:dfe_detalhe", args=[self.documento.pk])
        )
        xml = self.client.get(
            reverse(
                "fiscal:dfe_manifestacao_baixar_xml",
                args=[manifestacao.pk, "retorno"],
            )
        )

        self.assertEqual(detalhe.status_code, 404)
        self.assertEqual(xml.status_code, 404)