from copy import deepcopy

from django.test import SimpleTestCase

from .icms_st_fcp_contrato import construir_icms_st_fcp, validar_icms_st_fcp
from .tributos_itens_devolucao import CONTRATO_TRIBUTOS_ITENS


class IcmsStFcpContratoTests(SimpleTestCase):
    def tributos(self):
        grupo = lambda: {"estado": "HIPOTESE_NAO_CONFIRMADA", "codigo": "00", "base": "0.00", "aliquota": "0.0000", "valor": "0.00"}
        return {
            "conteudo": {
                "contrato": CONTRATO_TRIBUTOS_ITENS,
                "itens": [{
                    "nitem_novo": 1, "nitem_original": 2, "item_rascunho_id": 3,
                    "memoria_id": 4, "memoria_sha256": "a" * 64,
                    "revisao_sha256": "b" * 64,
                    "grupos": {"icms_st": grupo(), "fcp": grupo()},
                }],
            },
            "validacao": {"origem_completa": True},
        }

    def test_preserva_referencia_sem_definir_hipotese(self):
        resultado = construir_icms_st_fcp(self.tributos())
        self.assertTrue(resultado["validacao"]["estrutura_valida"])
        self.assertTrue(resultado["validacao"]["origem_completa"])
        self.assertEqual(resultado["conteudo"]["itens"][0]["hipotese"]["estado"], "NAO_DEFINIDA")
        self.assertEqual(resultado["conteudo"]["itens"][0]["destino_fiscal"]["grupo_icms_st"], "")
        self.assertEqual(resultado["conteudo"]["totais"]["fcp"], "")
        self.assertFalse(resultado["validacao"]["permite_emissao"])

    def test_rejeita_ativacao_de_hipotese_grupo_ou_total(self):
        conteudo = deepcopy(construir_icms_st_fcp(self.tributos())["conteudo"])
        conteudo["itens"][0]["hipotese"].update({"codigo": "DEVOLUCAO_ST", "estado": "APROVADA"})
        conteudo["itens"][0]["destino_fiscal"]["grupo_icms_st"] = "ICMS60"
        conteudo["totais"]["icms_st"] = "1.00"
        resultado = validar_icms_st_fcp(conteudo)
        self.assertFalse(resultado["estrutura_valida"])
        codigos = {item["codigo"] for item in resultado["erros"]}
        self.assertIn("HIPOTESE_NAO_APROVADA", codigos)
        self.assertIn("GRUPO_FISCAL_NAO_APROVADO", codigos)
        self.assertIn("TOTAL_NAO_APROVADO", codigos)

    def test_rejeita_inferencia_automatica_e_generalizacao(self):
        conteudo = construir_icms_st_fcp(self.tributos())["conteudo"]
        for campo in ("copiar_valores_memoria", "inferir_por_codigo_icms", "inferir_por_regime", "generalizar_orientacao_go"):
            conteudo["politica"][campo] = True
        resultado = validar_icms_st_fcp(conteudo)
        self.assertFalse(resultado["estrutura_valida"])
        self.assertIn("INFERENCIA_AUTOMATICA_PROIBIDA", {item["codigo"] for item in resultado["erros"]})
