from copy import deepcopy

from django.test import SimpleTestCase

from .ajustes_comerciais_devolucao import CONTRATO_AJUSTES_COMERCIAIS
from .produtos_devolucao import CONTRATO_PRODUTOS
from .totalizacao_diagnostica_devolucao import construir_totalizacao_diagnostica
from .tributos_itens_devolucao import CONTRATO_TRIBUTOS_ITENS, ESTADOS_GRUPOS


class TotalizacaoDiagnosticaDevolucaoTests(SimpleTestCase):
    def origens(self):
        grupos = {
            nome: {"estado": estado, "codigo": "", "base": "10.00" if nome in {"icms", "pis", "cofins"} else "0.00", "aliquota": "0.0000", "valor": "1.00" if nome == "icms" else "0.00"}
            for nome, estado in ESTADOS_GRUPOS.items()
        }
        produtos = {"conteudo": {"contrato": CONTRATO_PRODUTOS, "itens": [{"memoria_id": 7, "memoria_sha256": "a" * 64, "valor_produtos": "10.00"}]}, "validacao": {"dados_completos": True}}
        tributos = {"conteudo": {"contrato": CONTRATO_TRIBUTOS_ITENS, "itens": [{"memoria_id": 7, "memoria_sha256": "a" * 64, "revisao_sha256": "b" * 64, "grupos": grupos}]}, "validacao": {"origem_completa": True}}
        ajustes = {"conteudo": {"contrato": CONTRATO_AJUSTES_COMERCIAIS, "memoria_id": 7, "memoria_sha256": "a" * 64, "revisao_memoria_sha256": "b" * 64, "totais": {"valor_base": "10.00", "frete": "2.00", "seguro": "1.00", "outras_despesas": "0.50", "desconto": "0.50", "total_informado": "13.00"}}, "validacao": {"origem_completa": True}}
        return produtos, tributos, ajustes

    def test_confere_totais_informados_sem_formar_vnf(self):
        resultado = construir_totalizacao_diagnostica(*self.origens())
        self.assertTrue(resultado["validacao"]["estrutura_valida"])
        self.assertTrue(resultado["validacao"]["origem_completa"])
        self.assertEqual(resultado["conteudo"]["totais_comerciais"]["total_informado"], "13.00")
        self.assertEqual(resultado["conteudo"]["totais_tributarios_informados"]["icms"]["valor"], "1.00")
        self.assertEqual(resultado["conteudo"]["totais_fiscais_nao_definidos"]["valor_nota"], "")
        self.assertFalse(resultado["validacao"]["permite_emissao"])

    def test_origem_incompleta_nao_reaproveita_valores(self):
        produtos, tributos, ajustes = self.origens()
        tributos["validacao"]["origem_completa"] = False
        resultado = construir_totalizacao_diagnostica(produtos, tributos, ajustes)
        self.assertFalse(resultado["validacao"]["origem_completa"])
        self.assertEqual(resultado["conteudo"]["totais_tributarios_informados"]["icms"]["valor"], "")
        self.assertIn("ORIGEM_TOTALIZACAO_PENDENTE", {item["codigo"] for item in resultado["validacao"]["pendencias"]})

    def test_memorias_divergentes_e_total_fiscal_preenchido_bloqueiam(self):
        produtos, tributos, ajustes = self.origens()
        tributos = deepcopy(tributos)
        tributos["conteudo"]["itens"][0]["memoria_id"] = 8
        resultado = construir_totalizacao_diagnostica(produtos, tributos, ajustes)
        self.assertFalse(resultado["validacao"]["origem_completa"])
        resultado["conteudo"]["totais_fiscais_nao_definidos"]["valor_nota"] = "13.00"
        from .totalizacao_diagnostica_devolucao import validar_totalizacao_diagnostica
        validacao = validar_totalizacao_diagnostica(resultado["conteudo"])
        self.assertFalse(validacao["estrutura_valida"])
        self.assertFalse(validacao["permite_gerar_xml"])
