from types import SimpleNamespace

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from apps.vendas.models import TipoDocumentoConsumidor

from .chave_acesso import construir_chave_acesso
from .models import StatusDocumentoFiscal, TipoDocumentoFiscal
from .services import (
    _documento_destinatario_pedido,
    documento_em_contingencia_offline,
)


def _chave(cnpj, tipo_emissao):
    return construir_chave_acesso(
        codigo_uf="52",
        aamm="2609",
        cnpj_emitente=cnpj,
        modelo="65",
        serie="001",
        numero="000000123",
        tipo_emissao=tipo_emissao,
        codigo_numerico="12345678",
    )


class DestinatarioNFeTests(SimpleTestCase):
    def pedido(self, tipo, documento, cliente_documento=""):
        cliente = (
            SimpleNamespace(cpf_cnpj=cliente_documento)
            if cliente_documento
            else None
        )
        return SimpleNamespace(
            documento_cliente_tipo=tipo,
            documento_cliente=documento,
            cliente=cliente,
        )

    def test_preserva_cpf_e_cnpj_numerico(self):
        self.assertEqual(
            _documento_destinatario_pedido(
                self.pedido(TipoDocumentoConsumidor.CPF, "123.456.789-09")
            ),
            ("CPF", "12345678909"),
        )
        self.assertEqual(
            _documento_destinatario_pedido(
                self.pedido(TipoDocumentoConsumidor.CNPJ, "04.252.011/0001-10")
            ),
            ("CNPJ", "04252011000110"),
        )

    def test_canonicaliza_cnpj_alfa_mascarado_e_lowercase(self):
        pedido = self.pedido(
            TipoDocumentoConsumidor.CNPJ,
            "12.abc.345/01de-35",
        )
        self.assertEqual(
            _documento_destinatario_pedido(pedido),
            ("CNPJ", "12ABC34501DE35"),
        )

    def test_inferencia_do_cliente_so_ocorre_para_identidade_valida(self):
        valido = self.pedido(
            TipoDocumentoConsumidor.NAO_IDENTIFICADO,
            "",
            "12.abc.345/01de-35",
        )
        invalido = self.pedido(
            TipoDocumentoConsumidor.NAO_IDENTIFICADO,
            "",
            "12ABC34501DE36",
        )
        self.assertEqual(
            _documento_destinatario_pedido(valido),
            ("CNPJ", "12ABC34501DE35"),
        )
        with self.assertRaises(ValidationError):
            _documento_destinatario_pedido(invalido)

    def test_tipo_explicito_nao_e_reclassificado_quando_invalido(self):
        with self.assertRaisesMessage(ValidationError, "CNPJ válido"):
            _documento_destinatario_pedido(
                self.pedido(TipoDocumentoConsumidor.CNPJ, "12ABC34501DE36")
            )


class ContingenciaChaveAlfanumericaTests(SimpleTestCase):
    def documento(self, chave, *, status=StatusDocumentoFiscal.PRONTO):
        return SimpleNamespace(
            tipo_documento=TipoDocumentoFiscal.NFCE,
            status=status,
            contingencia_iniciada_em=object(),
            contingencia_justificativa="Falha temporária do autorizador.",
            chave_acesso=chave,
        )

    def test_reconhece_tpemis_9_em_chave_numerica_e_alfanumerica(self):
        for cnpj in ("04252011000110", "12ABC34501DE35"):
            with self.subTest(cnpj=cnpj):
                self.assertTrue(
                    documento_em_contingencia_offline(
                        self.documento(_chave(cnpj, "9").lower())
                    )
                )

    def test_nao_confunde_tpemis_1_nem_aceita_chave_invalida(self):
        normal = _chave("12ABC34501DE35", "1")
        invalida = normal[:-1] + ("0" if normal[-1] != "0" else "1")
        self.assertFalse(documento_em_contingencia_offline(self.documento(normal)))
        self.assertFalse(documento_em_contingencia_offline(self.documento(invalida)))

    def test_status_contingencia_funciona_antes_da_chave(self):
        self.assertTrue(
            documento_em_contingencia_offline(
                self.documento("", status=StatusDocumentoFiscal.CONTINGENCIA)
            )
        )
