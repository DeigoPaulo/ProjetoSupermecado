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

from .cce_adapters import CONTRATO_CARTA_CORRECAO
from .models import (
    AmbienteFiscal,
    CartaCorrecaoFiscal,
    ConfiguracaoFiscal,
    DocumentoFiscal,
    StatusCartaCorrecao,
    StatusDocumentoFiscal,
    TipoDocumentoFiscal,
    TipoEvidenciaFiscal,
)
from .sefaz_direta.adapter import NFE_NS
from .sefaz_direta.cce import CONDICAO_USO_CCE, SefazDiretaCartaCorrecaoAdapter
from .services_cce import registrar_carta_correcao


CNPJ = "12345678000195"
CHAVE = "52260812345678000195550010000000011000000010"


@override_settings(
    SEFAZ_DIRETA_CCE_NETWORK_ENABLED=True,
    SEFAZ_DIRETA_CCE_ALLOW_PRODUCTION=False,
)
class SefazDiretaCartaCorrecaoAdapterTests(SimpleTestCase):
    def test_monta_assina_e_envia_evento_110110_para_goias(self):
        chamadas = []
        retorno = f'''<retEnvEvento xmlns="{NFE_NS}" versao="1.00">
          <cStat>128</cStat><xMotivo>Lote processado</xMotivo>
          <retEvento><infEvento><cStat>135</cStat><xMotivo>Evento registrado</xMotivo>
          <nProt>135260000000009</nProt></infEvento></retEvento>
        </retEnvEvento>'''

        def transport(**kwargs):
            chamadas.append(kwargs)
            return retorno

        configuracao = SimpleNamespace(ambiente=AmbienteFiscal.HOMOLOGACAO)
        filial = SimpleNamespace(
            uf="GO", cnpj=CNPJ, empresa=SimpleNamespace(cnpj=CNPJ),
            configuracao_fiscal=configuracao,
        )
        documento = SimpleNamespace(pk=7, chave_acesso=CHAVE, filial=filial)
        adaptador = SefazDiretaCartaCorrecaoAdapter(transport=transport)
        with patch(
            "apps.fiscal.sefaz_direta.cce.assinar_xml_elemento_fiscal",
            side_effect=lambda xml, *args, **kwargs: xml,
        ):
            resultado = adaptador.corrigir(
                documento=documento,
                sequencia=2,
                correcao="Corrigir a descrição complementar do produto para caixa com doze unidades.",
                idempotency_key="teste-7",
            )

        self.assertEqual(resultado["status"], "AUTORIZADA")
        self.assertEqual(resultado["codigo_status"], "135")
        self.assertEqual(
            chamadas[0]["endpoint"],
            "https://homolog.sefaz.go.gov.br/nfe/services/NFeRecepcaoEvento4",
        )
        envelope = etree.fromstring(chamadas[0]["envelope"])
        self.assertEqual(envelope.xpath("string(.//*[local-name()='cOrgao'])"), "52")
        self.assertEqual(envelope.xpath("string(.//*[local-name()='tpEvento'])"), "110110")
        self.assertEqual(envelope.xpath("string(.//*[local-name()='nSeqEvento'])"), "2")
        self.assertEqual(
            envelope.xpath("string(.//*[local-name()='xCondUso'])"),
            CONDICAO_USO_CCE,
        )
        identificador = envelope.xpath("string(.//*[local-name()='infEvento']/@Id)")
        self.assertEqual(identificador, f"ID110110{CHAVE}02")

    def test_producao_permanece_bloqueada(self):
        configuracao = SimpleNamespace(ambiente=AmbienteFiscal.PRODUCAO)
        filial = SimpleNamespace(
            uf="GO", cnpj=CNPJ, empresa=SimpleNamespace(cnpj=CNPJ),
            configuracao_fiscal=configuracao,
        )
        documento = SimpleNamespace(pk=8, chave_acesso=CHAVE, filial=filial)
        with self.assertRaisesMessage(Exception, "Produção"):
            SefazDiretaCartaCorrecaoAdapter().corrigir(
                documento=documento,
                sequencia=1,
                correcao="Corrigir a descrição complementar da mercadoria na observação.",
            )


class FakeCartaCorrecaoAdapter:
    chamadas = []

    def corrigir(self, **kwargs):
        type(self).chamadas.append(kwargs)
        return {
            "contrato": CONTRATO_CARTA_CORRECAO,
            "status": "AUTORIZADA",
            "codigo_status": "135",
            "protocolo": "135260000000009",
            "mensagem": "Evento registrado e vinculado à NF-e.",
            "xml_envio": "<envEvento/>",
            "xml_retorno": "<retEnvEvento/>",
        }

    def diagnosticar(self):
        return {"disponivel": True, "mensagem": "Teste controlado."}


@override_settings(
    FISCAL_CCE_ADAPTER="apps.fiscal.test_carta_correcao.FakeCartaCorrecaoAdapter"
)
class CartaCorrecaoServiceTests(TestCase):
    def setUp(self):
        FakeCartaCorrecaoAdapter.chamadas = []
        self.usuario = get_user_model().objects.create_superuser(
            "fiscal-cce", "cce@example.com", "123"
        )
        self.empresa = Empresa.objects.create(
            razao_social="Mercado CC-e", nome_fantasia="Mercado CC-e", cnpj=CNPJ
        )
        self.filial = Filial.objects.create(
            empresa=self.empresa, nome="Matriz", cnpj=CNPJ, uf="GO"
        )
        ConfiguracaoFiscal.objects.create(
            filial=self.filial, ambiente=AmbienteFiscal.HOMOLOGACAO
        )
        self.documento = DocumentoFiscal.objects.create(
            filial=self.filial,
            tipo_documento=TipoDocumentoFiscal.NFE,
            ambiente=AmbienteFiscal.HOMOLOGACAO,
            serie=1,
            numero=1,
            chave_acesso=CHAVE,
            protocolo="135260000000001",
            status=StatusDocumentoFiscal.EMITIDO,
            usuario=self.usuario,
        )

    def registrar(self, texto="Corrigir a descrição complementar para embalagem com doze unidades."):
        return registrar_carta_correcao(
            self.documento,
            correcao=texto,
            confirmou_limites=True,
            usuario=self.usuario,
        )

    def test_registra_sequencias_e_auditoria(self):
        primeira = self.registrar()
        segunda = self.registrar("Corrigir a descrição complementar consolidada para caixa com doze unidades.")
        self.assertEqual(primeira.sequencia, 1)
        self.assertEqual(segunda.sequencia, 2)
        self.assertEqual(segunda.status, StatusCartaCorrecao.AUTORIZADA)
        self.assertEqual(LogAuditoria.objects.filter(acao="CARTA_CORRECAO").count(), 2)
        self.assertEqual(FakeCartaCorrecaoAdapter.chamadas[-1]["sequencia"], 2)
        self.assertEqual(
            list(self.documento.evidencias_fiscais.values_list("tipo", flat=True)),
            [
                TipoEvidenciaFiscal.EVENTO_CCE_ENVIO,
                TipoEvidenciaFiscal.EVENTO_CCE_RETORNO,
                TipoEvidenciaFiscal.EVENTO_CCE_ENVIO,
                TipoEvidenciaFiscal.EVENTO_CCE_RETORNO,
            ],
        )
        self.assertEqual(self.documento.evidencias_fiscais.get(sequencia=1).conteudo, "<envEvento/>")
        self.assertEqual(self.documento.evidencias_fiscais.get(sequencia=4).conteudo, "<retEnvEvento/>")

    def test_exige_confirmacao_e_texto_valido(self):
        with self.assertRaisesMessage(ValidationError, "15 e 1.000"):
            registrar_carta_correcao(
                self.documento, correcao="Curta", confirmou_limites=True,
                usuario=self.usuario,
            )
        with self.assertRaisesMessage(ValidationError, "Confirme"):
            registrar_carta_correcao(
                self.documento, correcao="Corrigir somente a informação complementar.",
                usuario=self.usuario,
            )

    def test_rejeita_nfce_e_documento_nao_autorizado(self):
        self.documento.tipo_documento = TipoDocumentoFiscal.NFCE
        self.documento.save(update_fields=["tipo_documento"])
        with self.assertRaisesMessage(ValidationError, "modelo 55"):
            self.registrar()
        self.documento.tipo_documento = TipoDocumentoFiscal.NFE
        self.documento.status = StatusDocumentoFiscal.CANCELADO
        self.documento.save(update_fields=["tipo_documento", "status"])
        with self.assertRaisesMessage(ValidationError, "autorizada"):
            self.registrar()

    def test_bloqueia_depois_de_720_horas(self):
        DocumentoFiscal.objects.filter(pk=self.documento.pk).update(
            criado_em=timezone.now() - timedelta(hours=721)
        )
        self.documento.refresh_from_db()
        with self.assertRaisesMessage(ValidationError, "720 horas"):
            self.registrar()

    def test_tela_download_e_isolamento_por_empresa(self):
        carta = self.registrar()
        self.client.force_login(self.usuario)
        tela = self.client.get(reverse("fiscal:detalhe", args=[self.documento.pk]))
        self.assertEqual(tela.status_code, 200)
        self.assertContains(tela, "Carta de Correção Eletrônica")
        download = self.client.get(
            reverse("fiscal:baixar_xml_cce", args=[carta.pk, "retorno"])
        )
        self.assertEqual(download.status_code, 200)
        self.assertIn(b"retEnvEvento", download.content)

        outra_empresa = Empresa.objects.create(
            razao_social="Outro Mercado", nome_fantasia="Outro Mercado",
            cnpj="98765432000188",
        )
        outra_filial = Filial.objects.create(
            empresa=outra_empresa, nome="Outra Matriz", cnpj="98765432000188", uf="GO"
        )
        externo = get_user_model().objects.create_user("cce-externo", password="123")
        PerfilUsuario.objects.create(
            usuario=externo, filial=outra_filial, tipo=TipoPerfil.ADMINISTRADOR
        )
        self.client.force_login(externo)
        self.assertEqual(
            self.client.get(reverse("fiscal:detalhe", args=[self.documento.pk])).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                reverse("fiscal:baixar_xml_cce", args=[carta.pk, "retorno"])
            ).status_code,
            404,
        )
