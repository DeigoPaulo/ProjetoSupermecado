from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from .forms import SerieFiscalForm
from .models import (
    AmbienteFiscal,
    DocumentoFiscal,
    SerieFiscal,
    StatusDocumentoFiscal,
    TipoDocumentoFiscal,
)
from .sefaz_direta.adapter import SERVICOS_GO, SefazDiretaAdapter, SefazDiretaError
from .services import (
    gerar_xml_nfce,
    gerar_xml_nfe_pedido_online,
    preparar_documento_pedido_online,
    preparar_documento_venda,
)
from .test_concorrencia_preparacao import FiscalOriginFixtureMixin
from .validacoes import validar_xml_pre_transmissao


class SerieFiscalAmbienteTests(FiscalOriginFixtureMixin, TestCase):
    def _documento_nfe_ambiente(self, ambiente):
        if ambiente == AmbienteFiscal.PRODUCAO:
            SerieFiscal.objects.create(
                filial=self.filial,
                tipo_documento=TipoDocumentoFiscal.NFE,
                ambiente=AmbienteFiscal.PRODUCAO,
                serie=55,
                proximo_numero=600,
            )
            self._configurar_producao()
        return preparar_documento_pedido_online(self.pedido, self.usuario)

    def _configurar_producao(self):
        configuracao = self.filial.configuracao_fiscal
        configuracao.ambiente = AmbienteFiscal.PRODUCAO
        configuracao.url_qrcode_nfce = (
            "https://nfeweb.sefaz.go.gov.br/nfeweb/sites/nfce/danfeNFCe"
        )
        configuracao.url_consulta_nfce = (
            "https://nfeweb.sefaz.go.gov.br/nfeweb/sites/nfce/danfeNFCe"
        )
        configuracao.save(
            update_fields=["ambiente", "url_qrcode_nfce", "url_consulta_nfce"]
        )
        return configuracao

    def test_mesma_serie_pode_existir_nos_dois_ambientes(self):
        producao = SerieFiscal.objects.create(
            filial=self.filial,
            tipo_documento=TipoDocumentoFiscal.NFCE,
            ambiente=AmbienteFiscal.PRODUCAO,
            serie=1,
            proximo_numero=500,
        )

        self.assertEqual(producao.serie, 1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            SerieFiscal.objects.create(
                filial=self.filial,
                tipo_documento=TipoDocumentoFiscal.NFCE,
                ambiente=AmbienteFiscal.PRODUCAO,
                serie=1,
            )

    def test_mesmo_numero_fiscal_pode_existir_nos_dois_ambientes(self):
        campos = {
            "filial": self.filial,
            "venda": self.venda,
            "tipo_documento": TipoDocumentoFiscal.NFCE,
            "serie": 7,
            "numero": 77,
            "status": StatusDocumentoFiscal.CANCELADO,
            "valor_total": Decimal("30.00"),
            "usuario": self.usuario,
        }
        DocumentoFiscal.objects.create(
            ambiente=AmbienteFiscal.HOMOLOGACAO,
            **campos,
        )
        producao = DocumentoFiscal.objects.create(
            ambiente=AmbienteFiscal.PRODUCAO,
            **campos,
        )

        self.assertEqual(producao.numero, 77)

    def test_preparacao_venda_usa_somente_serie_do_ambiente_configurado(self):
        SerieFiscal.objects.create(
            filial=self.filial,
            tipo_documento=TipoDocumentoFiscal.NFCE,
            ambiente=AmbienteFiscal.PRODUCAO,
            serie=1,
            proximo_numero=500,
        )
        self._configurar_producao()

        documento = preparar_documento_venda(self.venda, self.usuario)

        self.assertEqual(documento.ambiente, AmbienteFiscal.PRODUCAO)
        self.assertEqual(documento.numero, 500)
        self.assertEqual(
            SerieFiscal.objects.get(
                filial=self.filial,
                tipo_documento=TipoDocumentoFiscal.NFCE,
                ambiente=AmbienteFiscal.HOMOLOGACAO,
            ).proximo_numero,
            100,
        )
        self.assertEqual(
            SerieFiscal.objects.get(
                filial=self.filial,
                tipo_documento=TipoDocumentoFiscal.NFCE,
                ambiente=AmbienteFiscal.PRODUCAO,
            ).proximo_numero,
            501,
        )

    def test_preparacao_pedido_usa_somente_serie_do_ambiente_configurado(self):
        SerieFiscal.objects.create(
            filial=self.filial,
            tipo_documento=TipoDocumentoFiscal.NFE,
            ambiente=AmbienteFiscal.PRODUCAO,
            serie=55,
            proximo_numero=600,
        )
        self._configurar_producao()

        documento = preparar_documento_pedido_online(self.pedido, self.usuario)

        self.assertEqual(documento.ambiente, AmbienteFiscal.PRODUCAO)
        self.assertEqual(documento.numero, 600)
        self.assertEqual(
            SerieFiscal.objects.get(
                filial=self.filial,
                tipo_documento=TipoDocumentoFiscal.NFE,
                ambiente=AmbienteFiscal.HOMOLOGACAO,
            ).proximo_numero,
            200,
        )

    def _conferir_nfe_55_pre_envio(self, ambiente):
        adapter = SimpleNamespace(assina_xml=True, valida_schema=True)
        documento = self._documento_nfe_ambiente(ambiente)
        tp_amb = "2" if ambiente == AmbienteFiscal.HOMOLOGACAO else "1"
        oposto = "1" if tp_amb == "2" else "2"
        original = documento.xml_conteudo
        self.assertIn(f"<tpAmb>{tp_amb}</tpAmb>", original)
        validar_xml_pre_transmissao(documento, adapter)
        documento.xml_conteudo = original.replace(
            f"<tpAmb>{tp_amb}</tpAmb>", f"<tpAmb>{oposto}</tpAmb>", 1
        )
        with self.assertRaisesMessage(ValidationError, "tpAmb"):
            validar_xml_pre_transmissao(documento, adapter)

    def test_nfe_55_pre_envio_homologacao(self):
        self._conferir_nfe_55_pre_envio(AmbienteFiscal.HOMOLOGACAO)

    def test_nfe_55_pre_envio_producao(self):
        self._conferir_nfe_55_pre_envio(AmbienteFiscal.PRODUCAO)

    def _conferir_nfe_55_endpoint(self, ambiente, oposto):
        documento = self._documento_nfe_ambiente(ambiente)
        with self.settings(SEFAZ_DIRETA_ALLOW_PRODUCTION=True):
            adapter = SefazDiretaAdapter()
            self.assertEqual(
                adapter._endpoint(documento, documento.ambiente, "autorizacao"),
                SERVICOS_GO[ambiente]["autorizacao"],
            )
        with self.settings(
            SEFAZ_DIRETA_ALLOW_PRODUCTION=True,
            SEFAZ_DIRETA_ENDPOINTS={"GO": {ambiente: {
                "autorizacao": SERVICOS_GO[oposto]["autorizacao"],
            }}},
        ):
            with self.assertRaisesMessage(SefazDiretaError, "diverge do ambiente"):
                SefazDiretaAdapter()._endpoint(documento, ambiente, "autorizacao")

    def test_nfe_55_endpoint_homologacao(self):
        self._conferir_nfe_55_endpoint(AmbienteFiscal.HOMOLOGACAO, AmbienteFiscal.PRODUCAO)

    def test_nfe_55_endpoint_producao(self):
        self._conferir_nfe_55_endpoint(AmbienteFiscal.PRODUCAO, AmbienteFiscal.HOMOLOGACAO)

    def _conferir_regeneracao_historica(self, ambiente, grupo_presente):
        data_historica = timezone.make_aware(datetime(2026, 7, 20, 12))
        if ambiente == AmbienteFiscal.PRODUCAO:
            for tipo, serie, proximo_numero in (
                (TipoDocumentoFiscal.NFCE, 1, 500),
                (TipoDocumentoFiscal.NFE, 55, 600),
            ):
                SerieFiscal.objects.create(
                    filial=self.filial,
                    tipo_documento=tipo,
                    ambiente=AmbienteFiscal.PRODUCAO,
                    serie=serie,
                    proximo_numero=proximo_numero,
                )
            self._configurar_producao()
        documentos = (
            (preparar_documento_venda(self.venda, self.usuario), gerar_xml_nfce),
            (preparar_documento_pedido_online(self.pedido, self.usuario), gerar_xml_nfe_pedido_online),
        )
        configuracao = self.filial.configuracao_fiscal
        configuracao.ambiente = (
            AmbienteFiscal.PRODUCAO
            if ambiente == AmbienteFiscal.HOMOLOGACAO
            else AmbienteFiscal.HOMOLOGACAO
        )
        configuracao.save(update_fields=["ambiente"])
        for documento, gerar_xml in documentos:
            with self.subTest(modelo=documento.tipo_documento):
                self.assertEqual(documento.ambiente, ambiente)
                DocumentoFiscal.objects.filter(pk=documento.pk).update(criado_em=data_historica)
                documento.refresh_from_db()
                xml = gerar_xml(documento)
                self.assertIn(
                    f"<tpAmb>{'2' if ambiente == AmbienteFiscal.HOMOLOGACAO else '1'}</tpAmb>",
                    xml,
                )
                self.assertEqual("<IBSCBS>" in xml, grupo_presente)

    def test_regeneracao_homologacao_preserva_ibs_cbs(self):
        self._conferir_regeneracao_historica(AmbienteFiscal.HOMOLOGACAO, True)

    def test_regeneracao_producao_preserva_ibs_cbs(self):
        self._conferir_regeneracao_historica(AmbienteFiscal.PRODUCAO, False)

    def test_preparacao_recusa_quando_serie_existe_apenas_em_outro_ambiente(self):
        self._configurar_producao()

        with self.assertRaisesMessage(ValidationError, "Producao"):
            preparar_documento_venda(self.venda, self.usuario)

        self.assertFalse(DocumentoFiscal.objects.filter(venda=self.venda).exists())

    def test_formulario_expoe_ambiente_da_serie(self):
        form = SerieFiscalForm(user=self.usuario)

        self.assertIn("ambiente", form.fields)
