from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from .transporte_devolucao import TransporteDevolucaoForm, validar_transporte_proprio


class DocumentosTransporteTests(SimpleTestCase):
    def test_documentos_validos_e_invalidos(self):
        for documento, valido in [("52998224725", True), ("11222333000181", True), ("52998224724", False), ("11222333000182", False), ("11111111111", False), ("00000000000000", False), ("", True)]:
            with self.subTest(documento=documento):
                form = TransporteDevolucaoForm({"modalidade": "2", "nome": "Transportador", "documento": documento, "quantidade_volumes": "0", "peso_liquido": "0", "peso_bruto": "0"})
                self.assertEqual(form.is_valid(), valido)

    def test_transporte_proprio_compara_raiz_cnpj(self):
        validar_transporte_proprio({"modalidade": "3", "documento": "11222333000181"}, remetente="11222333000181", destinatario="52998224725")
        validar_transporte_proprio({"modalidade": "4", "documento": "52998224725"}, remetente="11222333000181", destinatario="52998224725")
        with self.assertRaises(ValidationError):
            validar_transporte_proprio({"modalidade": "3", "documento": "52998224725"}, remetente="11222333000181", destinatario="52998224725")
        with self.assertRaises(ValidationError):
            validar_transporte_proprio({"modalidade": "4", "documento": "11222333000181"}, remetente="11222333000181", destinatario="52998224725")

    def test_sem_documento_nao_exige_identidade_e_referencia_invalida_bloqueia(self):
        validar_transporte_proprio({"modalidade": "3", "documento": ""}, remetente="", destinatario="")
        with self.assertRaisesMessage(ValidationError, "referência"):
            validar_transporte_proprio({"modalidade": "3", "documento": "11222333000181"}, remetente="11111111111111", destinatario="")
