from django.test import SimpleTestCase

from .produtos_devolucao import CONTRATO_PRODUTOS, validar_produtos_devolucao


class ProdutosDevolucaoTests(SimpleTestCase):
    def contrato(self):
        return {
            "contrato": CONTRATO_PRODUTOS, "operacao": "DEVOLUCAO_COMPRA",
            "permite_emissao": False,
            "itens": [{
                "nitem_novo": 1, "nitem_original": 2, "item_rascunho_id": 3, "produto_id": 4,
                "xml_origem_sha256": "a" * 64, "parametrizacao_id": 5,
                "parametrizacao_sha256": "b" * 64, "memoria_id": 6,
                "memoria_sha256": "c" * 64, "memoria_aprovada": True,
                "codigo_produto": "ABC1", "ean": "SEM GTIN", "ean_tributavel": "SEM GTIN",
                "descricao": "Produto devolvido", "ncm": "10063021", "cest": "",
                "cfop": "5202", "unidade_comercial": "UN", "quantidade_comercial": "2.000",
                "valor_unitario_comercial": "10.00", "valor_produtos": "20.00",
                "unidade_tributavel": "UN", "quantidade_tributavel": "2.000",
                "valor_unitario_tributavel": "10.00", "tipo_codigo_icms": "CST",
                "origem_icms": "0", "codigo_icms": "00", "codigo_ipi": "NA",
                "codigo_pis": "01", "codigo_cofins": "01", "codigo_cbenef": "NA",
                "inclui_total_candidato": "", "inclui_total_fonte": "DECISAO_FISCAL_PENDENTE",
                "inclui_total_confirmado": False,
            }],
        }

    def test_contrato_completo_somente_confere_sem_emitir(self):
        resultado = validar_produtos_devolucao(self.contrato())
        self.assertTrue(resultado["estrutura_valida"])
        self.assertTrue(resultado["origem_completa"])
        self.assertFalse(resultado["dados_completos"])
        self.assertIn("INDTOT_CANDIDATO_PENDENTE", {item["codigo"] for item in resultado["pendencias"]})
        self.assertFalse(resultado["permite_aplicar_indtot"])
        self.assertFalse(resultado["permite_gerar_xml"])
        self.assertFalse(resultado["permite_emissao"])

    def test_indtot_valido_continua_nao_confirmado_e_nao_afeta_total(self):
        contrato = self.contrato()
        contrato["itens"][0]["inclui_total_candidato"] = "1"
        resultado = validar_produtos_devolucao(contrato)
        self.assertTrue(resultado["estrutura_valida"])
        self.assertIn("INDTOT_NAO_CONFIRMADO", {item["codigo"] for item in resultado["pendencias"]})
        self.assertEqual(contrato["itens"][0]["valor_produtos"], "20.00")
        self.assertFalse(resultado["permite_aplicar_indtot"])

    def test_rejeita_fonte_ou_confirmacao_direta_do_indtot(self):
        contrato = self.contrato()
        contrato["itens"][0].update({
            "inclui_total_candidato": "1", "inclui_total_fonte": "XML_ORIGINAL",
            "inclui_total_confirmado": True,
        })
        resultado = validar_produtos_devolucao(contrato)
        self.assertFalse(resultado["estrutura_valida"])
        codigos = {item["codigo"] for item in resultado["erros"]}
        self.assertIn("INDTOT_FONTE_INVALIDA", codigos)
        self.assertIn("INDTOT_CONFIRMACAO_DIRETA_PROIBIDA", codigos)

    def test_memoria_nao_aprovada_e_dados_ausentes_ficam_pendentes(self):
        contrato = self.contrato()
        contrato["itens"][0].update({
            "memoria_aprovada": False, "unidade_tributavel": "",
            "quantidade_tributavel": "", "valor_unitario_tributavel": "",
        })
        resultado = validar_produtos_devolucao(contrato)
        self.assertTrue(resultado["estrutura_valida"])
        self.assertFalse(resultado["dados_completos"])
        codigos = {item["codigo"] for item in resultado["pendencias"]}
        self.assertIn("MEMORIA_APROVADA_PENDENTE", codigos)
        self.assertIn("UNIDADE_TRIBUTAVEL_PENDENTE", codigos)

    def test_rejeita_total_divergente_duplicidade_e_emissao(self):
        contrato = self.contrato()
        contrato["permite_emissao"] = True
        contrato["itens"][0]["valor_produtos"] = "19.99"
        contrato["itens"].append(dict(contrato["itens"][0]))
        resultado = validar_produtos_devolucao(contrato)
        self.assertFalse(resultado["estrutura_valida"])
        self.assertFalse(resultado["dados_completos"])
        codigos = {item["codigo"] for item in resultado["pendencias"]}
        self.assertIn("VALOR_NAO_CONFERE_COM_QUANTIDADE_E_UNITARIO", codigos)
        self.assertFalse(resultado["permite_emissao"])
