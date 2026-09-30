from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from .pagamentos import validar_tpag_leiaute, validar_tpag_venda_normal


class ValidacaoTPagTests(SimpleTestCase):
    def test_vazio_preserva_fallback_e_codigo_catalogado_e_aceito(self):
        self.assertEqual(validar_tpag_venda_normal("", ""), ("", ""))
        for codigo in ("01", "03", "04", "05", "10", "11", "17"):
            with self.subTest(codigo=codigo):
                self.assertEqual(validar_tpag_venda_normal(codigo, ""), (codigo, ""))

    def test_tpag_99_exige_xpag(self):
        self.assertEqual(
            validar_tpag_venda_normal("99", "Convenio"),
            ("99", "Convenio"),
        )
        with self.assertRaisesMessage(ValidationError, "Informe xPag"):
            validar_tpag_venda_normal("99", "")

    def test_tpag_diferente_de_99_proibe_xpag(self):
        with self.assertRaisesMessage(ValidationError, "xPag só pode"):
            validar_tpag_venda_normal("17", "PIX manual")

    def test_tpag_90_e_conhecido_mas_bloqueado_em_venda_normal(self):
        self.assertEqual(validar_tpag_leiaute("90", ""), ("90", ""))
        with self.assertRaisesMessage(ValidationError, "não é suportado no fluxo"):
            validar_tpag_venda_normal("90", "")

    def test_codigo_desconhecido_e_formatos_invalidos_sao_bloqueados(self):
        with self.assertRaisesMessage(ValidationError, "não é reconhecido"):
            validar_tpag_venda_normal("98", "")
        for codigo in ("1", "100", "A1"):
            with self.subTest(codigo=codigo), self.assertRaisesMessage(
                ValidationError, "2 dígitos"
            ):
                validar_tpag_venda_normal(codigo, "")
