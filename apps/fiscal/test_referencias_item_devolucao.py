from copy import deepcopy

from django.test import SimpleTestCase

from .referencias_item_devolucao import (
    CONTRATO_REFERENCIAS_ITEM,
    POLITICA_REFERENCIAS_ITEM,
    validar_referencias_item_devolucao,
)


def _chave_sintetica(base="5" * 43):
    pesos = (2, 3, 4, 5, 6, 7, 8, 9) * 6
    soma = sum(int(digito) * peso for digito, peso in zip(reversed(base), pesos))
    resto = soma % 11
    return base + str(0 if resto in (0, 1) else 11 - resto)


class ReferenciasItemDevolucaoTests(SimpleTestCase):
    def setUp(self):
        self.chave = _chave_sintetica()
        self.conteudo = {
            "contrato": CONTRATO_REFERENCIAS_ITEM,
            "politica": POLITICA_REFERENCIAS_ITEM,
            "modelo": "55",
            "operacao": "DEVOLUCAO_COMPRA",
            "possui_nfref_cabecalho": False,
            "permite_emissao": False,
            "itens": [{"nitem_novo": 1, "chave_acesso": self.chave, "nitem_original": 7}],
        }

    def test_referencia_valida_permanece_nao_emissiva(self):
        antes = deepcopy(self.conteudo)
        resultado = validar_referencias_item_devolucao(self.conteudo)
        self.assertTrue(resultado["estrutura_valida"])
        self.assertTrue(resultado["escopo_suportado"])
        self.assertFalse(resultado["permite_gerar_xml"])
        self.assertFalse(resultado["permite_emissao"])
        self.assertEqual(self.conteudo, antes)

    def test_mesma_chave_com_itens_originais_distintos_e_valida(self):
        self.conteudo["itens"].append({"nitem_novo": 2, "chave_acesso": self.chave, "nitem_original": 8})
        self.assertTrue(validar_referencias_item_devolucao(self.conteudo)["estrutura_valida"])

    def test_par_chave_e_item_original_duplicado_e_rejeitado(self):
        self.conteudo["itens"].append({"nitem_novo": 2, "chave_acesso": self.chave, "nitem_original": 7})
        resultado = validar_referencias_item_devolucao(self.conteudo)
        self.assertFalse(resultado["estrutura_valida"])
        self.assertFalse(resultado["escopo_suportado"])
        self.assertIn("DFE_ITEM_REFERENCIADO_EM_DUPLICIDADE", [e["codigo"] for e in resultado["erros"]])

    def test_nitem_novo_duplicado_e_rejeitado(self):
        self.conteudo["itens"].append({"nitem_novo": 1, "chave_acesso": self.chave, "nitem_original": 8})
        self.assertFalse(validar_referencias_item_devolucao(self.conteudo)["estrutura_valida"])

    def test_chaves_invalidas_sao_rejeitadas(self):
        invalidas = ("", "1" * 43, "A" * 44, self.chave[:-1] + str((int(self.chave[-1]) + 1) % 10))
        for chave in invalidas:
            with self.subTest(chave=chave):
                conteudo = deepcopy(self.conteudo)
                conteudo["itens"][0]["chave_acesso"] = chave
                self.assertFalse(validar_referencias_item_devolucao(conteudo)["estrutura_valida"])

    def test_nitem_original_invalido_e_rejeitado(self):
        for valor in (None, True, 0, 1000, "7"):
            with self.subTest(valor=valor):
                conteudo = deepcopy(self.conteudo)
                conteudo["itens"][0]["nitem_original"] = valor
                self.assertFalse(validar_referencias_item_devolucao(conteudo)["estrutura_valida"])

    def test_nfref_modelo_e_operacao_incorretos_bloqueiam(self):
        for campo, valor in (("possui_nfref_cabecalho", True), ("modelo", "65"), ("operacao", "VENDA")):
            with self.subTest(campo=campo):
                self.assertFalse(validar_referencias_item_devolucao({**self.conteudo, campo: valor})["estrutura_valida"])

    def test_politica_emissao_lista_e_campos_extras_invalidos_bloqueiam(self):
        casos = (
            {**self.conteudo, "politica": "DATA_AUTOMATICA"},
            {**self.conteudo, "permite_emissao": True},
            {**self.conteudo, "itens": []},
            {**self.conteudo, "token": "nao_expor"},
        )
        for conteudo in casos:
            resultado = validar_referencias_item_devolucao(conteudo)
            self.assertFalse(resultado["estrutura_valida"])
            self.assertNotIn("nao_expor", str(resultado))

    def test_multiplas_origens_ficam_fora_do_produto_inicial(self):
        outra = _chave_sintetica("4" * 43)
        self.conteudo["itens"].append({"nitem_novo": 2, "chave_acesso": outra, "nitem_original": 1})
        resultado = validar_referencias_item_devolucao(self.conteudo)
        self.assertTrue(resultado["estrutura_valida"])
        self.assertFalse(resultado["escopo_suportado"])
        self.assertIn("MULTIPLAS_ORIGENS_FORA_ESCOPO_INICIAL", [b["codigo"] for b in resultado["bloqueios"]])

    def test_entradas_malformadas_nao_geram_excecao(self):
        for conteudo in (None, [], "", 1, {**self.conteudo, "itens": [None]}):
            self.assertFalse(validar_referencias_item_devolucao(conteudo)["estrutura_valida"])
