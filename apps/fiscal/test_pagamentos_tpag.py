from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from .pagamentos import validar_configuracao_tpag


class ValidacaoTPagTests(SimpleTestCase):
    def test_vazio_preserva_fallback_e_codigo_catalogado_e_aceito(self):
        self.assertEqual(validar_configuracao_tpag("", ""), ("", ""))
        self.assertEqual(validar_configuracao_tpag("17", ""), ("17", ""))

    def test_tpag_99_exige_xpag(self):
        self.assertEqual(
            validar_configuracao_tpag("99", "Convenio"),
            ("99", "Convenio"),
        )
        with self.assertRaisesMessage(ValidationError, "Informe xPag"):
            validar_configuracao_tpag("99", "")

    def test_tpag_diferente_de_99_proibe_xpag(self):
        with self.assertRaisesMessage(ValidationError, "xPag só pode"):
            validar_configuracao_tpag("17", "PIX manual")

    def test_codigo_desconhecido_e_formatos_invalidos_sao_bloqueados(self):
        with self.assertRaisesMessage(ValidationError, "não é reconhecido"):
            validar_configuracao_tpag("98", "")
        for codigo in ("1", "100", "A1"):
            with self.subTest(codigo=codigo), self.assertRaisesMessage(
                ValidationError, "2 dígitos"
            ):
                validar_configuracao_tpag(codigo, "")
