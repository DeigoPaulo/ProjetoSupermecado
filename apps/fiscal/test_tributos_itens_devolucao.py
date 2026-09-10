from django.test import SimpleTestCase

from .tributos_itens_devolucao import (
    CONTRATO_TRIBUTOS_ITENS,
    ESTADOS_GRUPOS,
    validar_tributos_itens_devolucao,
)


class TributosItensDevolucaoTests(SimpleTestCase):
    def contrato(self):
        grupos = {
            nome: {
                "estado": estado,
                "codigo": "00" if nome == "icms" else "01",
                "base": "10.00", "aliquota": "1.0000", "valor": "0.10",
            }
            for nome, estado in ESTADOS_GRUPOS.items()
        }
        return {
            "contrato": CONTRATO_TRIBUTOS_ITENS,
            "operacao": "DEVOLUCAO_COMPRA",
            "permite_emissao": False,
            "itens": [{
                "nitem_novo": 1, "nitem_original": 1, "item_rascunho_id": 1,
                "memoria_id": 2, "memoria_sha256": "a" * 64,
                "revisao_sha256": "b" * 64, "origem_aprovada": True,
                "grupos": grupos,
            }],
        }

    def test_valores_informados_validos_nao_liberam_escopo_fiscal(self):
        resultado = validar_tributos_itens_devolucao(self.contrato())
        self.assertTrue(resultado["estrutura_valida"])
        self.assertTrue(resultado["origem_completa"])
        self.assertFalse(resultado["escopo_fiscal_suportado"])
        self.assertFalse(resultado["permite_emissao"])

    def test_memoria_pendente_nao_exige_numeros_inventados(self):
        contrato = self.contrato()
        item = contrato["itens"][0]
        item.update({"memoria_id": 0, "memoria_sha256": "", "revisao_sha256": "", "origem_aprovada": False})
        for grupo in item["grupos"].values():
            grupo.update({"codigo": "", "base": "", "aliquota": "", "valor": ""})
        resultado = validar_tributos_itens_devolucao(contrato)
        self.assertTrue(resultado["estrutura_valida"])
        self.assertFalse(resultado["origem_completa"])
        self.assertIn("MEMORIA_REVISADA_APROVADA_PENDENTE", {item["codigo"] for item in resultado["pendencias"]})

    def test_rejeita_estado_grupo_formato_e_emissao(self):
        contrato = self.contrato()
        contrato["permite_emissao"] = True
        contrato["itens"][0]["grupos"]["ipi_memoria"]["estado"] = "IPI_DEVOLVIDO"
        contrato["itens"][0]["grupos"]["icms"]["base"] = "-1.00"
        resultado = validar_tributos_itens_devolucao(contrato)
        self.assertFalse(resultado["estrutura_valida"])
        self.assertFalse(resultado["origem_completa"])
        self.assertFalse(resultado["permite_emissao"])
