from copy import deepcopy

from django.test import SimpleTestCase

from .observacoes_fiscais_devolucao import (
    CONTRATO_OBSERVACOES,
    validar_observacoes_fiscais_devolucao,
)


class ObservacoesFiscaisDevolucaoTests(SimpleTestCase):
    def contrato(self):
        return {
            "contrato": CONTRATO_OBSERVACOES,
            "operacao": "DEVOLUCAO_COMPRA",
            "permite_emissao": False,
            "origem_aprovada": True,
            "fontes": {
                "parecer_id": 1, "parecer_sha256": "a" * 64,
                "parametrizacao_id": 2, "parametrizacao_sha256": "b" * 64,
                "memoria_id": 3, "memoria_sha256": "c" * 64,
                "revisao_memoria_sha256": "d" * 64,
            },
            "inventario_interno": {
                "motivo_operacional_presente": True,
                "fundamentacao_parecer_presente": True,
                "observacoes_parametros": 1,
                "observacoes_memoria": 1,
                "observacao_transporte_presente": False,
            },
            "textos_fiscais": {
                "infadic": "",
                "itens": [{"nitem_novo": 1, "nitem_original": 1, "item_rascunho_id": 4, "infadprod": ""}],
            },
            "politica": {
                "classificacao_interna_obrigatoria": True,
                "exportacao_automatica": False,
                "exige_texto_fiscal_aprovado": True,
            },
        }

    def test_inventario_interno_nao_vira_texto_fiscal(self):
        resultado = validar_observacoes_fiscais_devolucao(self.contrato())
        self.assertTrue(resultado["estrutura_valida"])
        self.assertTrue(resultado["origem_completa"])
        self.assertFalse(resultado["textos_fiscais_definidos"])
        self.assertFalse(resultado["permite_emissao"])

    def test_rejeita_injecao_em_infadic_ou_infadprod(self):
        for caminho in ("infadic", "infadprod"):
            with self.subTest(caminho=caminho):
                conteudo = deepcopy(self.contrato())
                if caminho == "infadic":
                    conteudo["textos_fiscais"]["infadic"] = "Copiar motivo interno"
                else:
                    conteudo["textos_fiscais"]["itens"][0]["infadprod"] = "Copiar observação interna"
                resultado = validar_observacoes_fiscais_devolucao(conteudo)
                self.assertFalse(resultado["estrutura_valida"])
                self.assertIn("TEXTO_FISCAL_NAO_APROVADO", {item["codigo"] for item in resultado["erros"]})

    def test_rejeita_exportacao_automatica(self):
        conteudo = self.contrato()
        conteudo["politica"]["exportacao_automatica"] = True
        resultado = validar_observacoes_fiscais_devolucao(conteudo)
        self.assertFalse(resultado["estrutura_valida"])
        self.assertIn("EXPORTACAO_AUTOMATICA_PROIBIDA", {item["codigo"] for item in resultado["erros"]})
