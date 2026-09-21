from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from .forms import SerieFiscalForm
from .models import (
    AmbienteFiscal,
    DocumentoFiscal,
    SerieFiscal,
    StatusDocumentoFiscal,
    TipoDocumentoFiscal,
)
from .services import preparar_documento_pedido_online, preparar_documento_venda
from .test_concorrencia_preparacao import FiscalOriginFixtureMixin


class SerieFiscalAmbienteTests(FiscalOriginFixtureMixin, TestCase):
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

    def test_preparacao_recusa_quando_serie_existe_apenas_em_outro_ambiente(self):
        self._configurar_producao()

        with self.assertRaisesMessage(ValidationError, "Producao"):
            preparar_documento_venda(self.venda, self.usuario)

        self.assertFalse(DocumentoFiscal.objects.filter(venda=self.venda).exists())

    def test_formulario_expoe_ambiente_da_serie(self):
        form = SerieFiscalForm(user=self.usuario)

        self.assertIn("ambiente", form.fields)
