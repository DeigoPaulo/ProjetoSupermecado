from django.test import SimpleTestCase

from .transporte_contrato_devolucao import CONTRATO_TRANSPORTE, validar_transporte_devolucao


class TransporteContratoDevolucaoTests(SimpleTestCase):
    def contrato(self):
        return {
            "contrato": CONTRATO_TRANSPORTE, "operacao": "DEVOLUCAO_COMPRA",
            "permite_emissao": False, "origem_atual": True,
            "ficha_id": 1, "ficha_sha256": "a" * 64,
            "memoria_id": 2, "memoria_sha256": "b" * 64,
            "revisao_memoria_sha256": "c" * 64,
            "dados": {
                "modalidade": "9", "nome": "", "documento": "", "inscricao_estadual": "",
                "endereco": "", "municipio": "", "uf": "", "quantidade_volumes": 0,
                "especie": "", "marca": "", "numeracao": "", "peso_liquido": "0.000",
                "peso_bruto": "0.000", "observacao": "",
            },
        }

    def test_sem_transporte_valido_continua_nao_emissivo(self):
        resultado = validar_transporte_devolucao(self.contrato())
        self.assertTrue(resultado["estrutura_valida"])
        self.assertTrue(resultado["origem_completa"])
        self.assertFalse(resultado["permite_gerar_xml"])
        self.assertFalse(resultado["permite_emissao"])

    def test_ficha_ausente_fica_pendente_sem_defaults(self):
        contrato = self.contrato()
        contrato.update({"origem_atual": False, "ficha_id": 0, "ficha_sha256": "", "memoria_id": 0, "memoria_sha256": "", "revisao_memoria_sha256": ""})
        contrato["dados"].update({"modalidade": "", "quantidade_volumes": None, "peso_liquido": "", "peso_bruto": ""})
        resultado = validar_transporte_devolucao(contrato)
        self.assertTrue(resultado["estrutura_valida"])
        self.assertFalse(resultado["origem_completa"])

    def test_rejeita_combinacoes_condicionais_e_emissao(self):
        contrato = self.contrato()
        contrato["permite_emissao"] = True
        contrato["dados"].update({"nome": "Transportadora indevida", "quantidade_volumes": 0, "especie": "Caixas", "peso_liquido": "2.000", "peso_bruto": "1.000"})
        resultado = validar_transporte_devolucao(contrato)
        self.assertFalse(resultado["estrutura_valida"])
        codigos = {item["codigo"] for item in resultado["pendencias"]}
        self.assertIn("SEM_TRANSPORTE_NAO_PERMITE_TRANSPORTADOR", codigos)
        self.assertIn("PESO_BRUTO_INFERIOR_AO_LIQUIDO", codigos)
        self.assertFalse(resultado["permite_emissao"])
