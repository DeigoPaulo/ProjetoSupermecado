from django.conf import settings
from django.test import SimpleTestCase

from .auditoria_fase5_cnpj import (
    CONTRATO_AUDITORIA_FASE5_CNPJ,
    auditar_fase5_cnpj,
)
from .estrategia_normalizacao_cnpj import (
    calcular_dv_chave_acesso,
    validar_chave_acesso,
)


class AuditoriaFase5CNPJTests(SimpleTestCase):
    def resultado(self):
        return auditar_fase5_cnpj(settings.BASE_DIR)

    def test_confirma_todos_os_achados_sem_alterar_consumidores(self):
        resultado = self.resultado()

        self.assertEqual(resultado["contrato"], CONTRATO_AUDITORIA_FASE5_CNPJ)
        self.assertTrue(resultado["resumo"]["todos_achados_confirmados"])
        self.assertFalse(resultado["resumo"]["altera_codigo_operacional"])
        self.assertTrue(
            all(not item["alteracao_executada"] for item in resultado["resultados"])
        )

    def test_classifica_chave_xml_qrcode_e_danfe(self):
        resultado = self.resultado()
        por_codigo = {item["codigo"]: item for item in resultado["resultados"]}

        for codigo in (
            "CHAVE_FORMACAO_EMITENTE",
            "CHAVE_DIGITO_VERIFICADOR",
            "XML_NFCE_CNPJ_EMITENTE",
            "XML_NFE_CNPJ_EMITENTE",
            "XML_IDENTIFICADOR_INF_NFE",
            "VALIDACAO_CHAVE_XML",
            "VALIDACAO_RETORNO_ADAPTADORES",
            "FLUXOS_POS_GERACAO",
            "QR_CODE_NFCE",
            "DANFE_CHAVE_TEXTO",
            "DANFE_CODIGO_BARRAS_HIBRIDO",
            "CNPJ_EMITENTE_DV",
            "NFE_DESTINATARIO_CNPJ",
            "MARKETPLACE_DOCUMENTO_DESTINATARIO",
            "CONTINGENCIA_NFCE_CHAVE",
            "PDV_DESKTOP_CHAVE_TEXTO",
        ):
            self.assertEqual(por_codigo[codigo]["estado"], "COMPATIVEL_OFFLINE")
        self.assertEqual(por_codigo["PDV_DESKTOP_CODE128"]["estado"], "AUSENTE")
        self.assertEqual(resultado["resumo"]["pontos_fase5"], 17)
        self.assertEqual(resultado["resumo"]["compativeis_offline_fase5"], 16)
        self.assertEqual(resultado["resumo"]["ausentes_fase5"], 1)

    def test_separa_canais_da_fase6(self):
        resultado = self.resultado()
        fase6 = [
            item for item in resultado["resultados"] if item["escopo"] == "FASE_6"
        ]

        self.assertEqual(len(fase6), 3)
        self.assertEqual(resultado["resumo"]["pontos_fase6_inventariados"], 3)
        self.assertTrue(all(item["ordem_correcao"] == 6 for item in fase6))
        self.assertTrue(all(item["estado"] == "COMPATIVEL_OFFLINE" for item in fase6))

    def test_nucleo_isolado_ja_calcula_chave_alfanumerica_oficial(self):
        base = "52260912ABC34501DE3555001000000001112345678"
        chave = base + calcular_dv_chave_acesso(base)

        self.assertEqual(len(chave), 44)
        self.assertTrue(validar_chave_acesso(chave))
        self.assertTrue(any(caractere.isalpha() for caractere in chave))
        self.assertEqual(
            self.resultado()["proximo_passo"],
            "HOMOLOGAR_FOCUS_E_SEFAZ_DIRETA_SEPARADAMENTE",
        )
