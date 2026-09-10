from django.test import SimpleTestCase

from .ajustes_comerciais_devolucao import (
    CONTRATO_AJUSTES_COMERCIAIS,
    validar_ajustes_comerciais_devolucao,
)


class AjustesComerciaisDevolucaoTests(SimpleTestCase):
    def contrato(self):
        return {
            "contrato": CONTRATO_AJUSTES_COMERCIAIS,
            "operacao": "DEVOLUCAO_COMPRA",
            "permite_emissao": False,
            "origem_aprovada": True,
            "rateio_id": 1, "rateio_sha256": "a" * 64,
            "reflexos_id": 2, "reflexos_sha256": "b" * 64,
            "memoria_id": 3, "memoria_sha256": "c" * 64,
            "revisao_memoria_sha256": "d" * 64,
            "itens": [{
                "nitem_novo": 1, "nitem_original": 1,
                "item_rascunho_id": 4, "item_memoria_id": 5,
                "valor_base": "10.00", "frete": "2.00", "seguro": "1.00",
                "outras_despesas": "0.50", "desconto": "0.50", "total_informado": "13.00",
            }],
            "totais": {
                "valor_base": "10.00", "frete": "2.00", "seguro": "1.00",
                "outras_despesas": "0.50", "desconto": "0.50", "total_informado": "13.00",
            },
        }

    def test_contrato_confere_somas_sem_reaplicar_ajustes(self):
        resultado = validar_ajustes_comerciais_devolucao(self.contrato())
        self.assertTrue(resultado["estrutura_valida"])
        self.assertTrue(resultado["origem_completa"])
        self.assertIn("NAO_REAPLICAR_A_BASES_TRIBUTARIAS", {item["codigo"] for item in resultado["bloqueios"]})
        self.assertFalse(resultado["permite_emissao"])

    def test_origem_pendente_aceita_campos_vazios_sem_inventar_valores(self):
        contrato = self.contrato()
        contrato.update({
            "origem_aprovada": False, "rateio_id": 0, "rateio_sha256": "",
            "reflexos_id": 0, "reflexos_sha256": "", "memoria_id": 0,
            "memoria_sha256": "", "revisao_memoria_sha256": "",
        })
        for item in contrato["itens"]:
            item["item_memoria_id"] = 0
            for campo in ("valor_base", "frete", "seguro", "outras_despesas", "desconto", "total_informado"):
                item[campo] = ""
        contrato["totais"] = {campo: "" for campo in contrato["totais"]}
        resultado = validar_ajustes_comerciais_devolucao(contrato)
        self.assertTrue(resultado["estrutura_valida"])
        self.assertFalse(resultado["origem_completa"])

    def test_rejeita_total_divergente_duplicidade_e_emissao(self):
        contrato = self.contrato()
        contrato["permite_emissao"] = True
        contrato["itens"][0]["total_informado"] = "12.99"
        contrato["itens"].append(dict(contrato["itens"][0]))
        resultado = validar_ajustes_comerciais_devolucao(contrato)
        self.assertFalse(resultado["estrutura_valida"])
        self.assertFalse(resultado["origem_completa"])
        self.assertIn("TOTAL_ITEM_NAO_CONFERE", {item["codigo"] for item in resultado["pendencias"]})
        self.assertFalse(resultado["permite_emissao"])
