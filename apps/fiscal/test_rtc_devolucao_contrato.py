from copy import deepcopy

from django.test import SimpleTestCase

from .rtc_devolucao_contrato import construir_rtc_devolucao, validar_rtc_devolucao
from .tributos_itens_devolucao import CONTRATO_TRIBUTOS_ITENS


class RtcDevolucaoContratoTests(SimpleTestCase):
    def tributos(self):
        grupo = lambda: {"estado": "VIGENCIA_E_LEIAUTE_PENDENTES", "codigo": "", "base": "0.00", "aliquota": "0.0000", "valor": "0.00"}
        return {
            "conteudo": {
                "contrato": CONTRATO_TRIBUTOS_ITENS,
                "itens": [{
                    "nitem_novo": 1, "nitem_original": 2, "item_rascunho_id": 3,
                    "memoria_id": 4, "memoria_sha256": "a" * 64,
                    "revisao_sha256": "b" * 64,
                    "grupos": {"ibs": grupo(), "cbs": grupo()},
                }],
            },
            "validacao": {"origem_completa": True},
        }

    def test_datas_documentais_nao_ativam_rtc(self):
        resultado = construir_rtc_devolucao(self.tributos())
        self.assertTrue(resultado["validacao"]["estrutura_valida"])
        self.assertTrue(resultado["validacao"]["origem_completa"])
        self.assertEqual(resultado["conteudo"]["evidencia_normativa"]["producao_documental"], "2026-11-03")
        self.assertFalse(resultado["conteudo"]["politica"]["ativar_por_data"])
        self.assertFalse(resultado["validacao"]["vigencia_confirmada"])
        self.assertFalse(resultado["validacao"]["permite_emissao"])

    def test_rejeita_classificacao_grupos_ou_totais_antecipados(self):
        conteudo = deepcopy(construir_rtc_devolucao(self.tributos())["conteudo"])
        conteudo["itens"][0]["classificacao_rtc"].update({"codigo": "000001", "estado": "CONFIRMADA"})
        conteudo["itens"][0]["destino_fiscal"]["grupo_ibs"] = "IBSCBS"
        conteudo["totais"]["rtc"] = "1.00"
        resultado = validar_rtc_devolucao(conteudo)
        self.assertFalse(resultado["estrutura_valida"])
        codigos = {item["codigo"] for item in resultado["erros"]}
        self.assertIn("CLASSIFICACAO_NAO_CONFIRMADA", codigos)
        self.assertIn("GRUPO_RTC_NAO_APROVADO", codigos)
        self.assertIn("TOTAL_RTC_NAO_APROVADO", codigos)

    def test_rejeita_ativacao_por_data_ou_schema_isolado(self):
        conteudo = construir_rtc_devolucao(self.tributos())["conteudo"]
        conteudo["politica"].update({"ativar_por_data": True, "usar_schema_sem_homologacao": True})
        resultado = validar_rtc_devolucao(conteudo)
        self.assertFalse(resultado["estrutura_valida"])
        self.assertIn("ATIVACAO_AUTOMATICA_PROIBIDA", {item["codigo"] for item in resultado["erros"]})
