import base64

from barcode.codex import code128
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from .barcode_chave import (
    CONTRATO_BARCODE_CHAVE_FISCAL,
    codigos_code128_chave,
    gerar_codigo_barras_chave_data_uri,
)
from .chave_acesso import construir_chave_acesso
from .test_support_identidades_fiscais import obter_identidade_fiscal_teste


class BarcodeChaveFiscalTests(SimpleTestCase):
    def chave(self, cnpj):
        return construir_chave_acesso(
            codigo_uf="52",
            aamm="2609",
            cnpj_emitente=cnpj,
            modelo="65",
            serie="001",
            numero="000000123",
            tipo_emissao="1",
            codigo_numerico="12345678",
        )

    def test_chave_alfanumerica_alterna_somente_entre_code128_c_e_a(self):
        chave = self.chave(obter_identidade_fiscal_teste(
            "FILIAL",
            finalidade="TESTE_UNITARIO",
        ))

        codigos = codigos_code128_chave(chave)

        self.assertEqual(CONTRATO_BARCODE_CHAVE_FISCAL, "fiscal_access_key_code128_ca_v1")
        self.assertIn(code128.START_CODES["C"], codigos)
        self.assertIn(code128.C["TO_A"], codigos)
        self.assertIn(code128.A["TO_C"], codigos)
        self.assertNotIn(code128.C["TO_B"], codigos)

    def test_chave_numerica_permanece_compacta_no_conjunto_c(self):
        codigos = codigos_code128_chave(self.chave("04252011000110"))

        self.assertEqual(codigos[0], code128.START_CODES["C"])
        self.assertNotIn(code128.C["TO_A"], codigos)
        self.assertNotIn(code128.C["TO_B"], codigos)

    def test_gera_svg_local_e_recusa_chave_invalida(self):
        uri = gerar_codigo_barras_chave_data_uri(self.chave("04252011000110"))
        svg = base64.b64decode(uri.split(",", 1)[1]).decode("utf-8")

        self.assertTrue(uri.startswith("data:image/svg+xml;base64,"))
        self.assertIn("<svg", svg)
        with self.assertRaises(ValidationError):
            gerar_codigo_barras_chave_data_uri("0" * 43)
