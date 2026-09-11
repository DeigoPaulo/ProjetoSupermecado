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
        grupos["icms"].update({
            "modalidade_base_candidata": "",
            "modalidade_base_fonte": "DECISAO_CONTADOR_PENDENTE",
            "modalidade_base_confirmada": False,
            "reducao_base_candidata": "",
            "reducao_base_fonte": "DECISAO_CONTADOR_PENDENTE",
            "reducao_base_confirmada": False,
        })
        for nome, grupo_xml in (("pis", "PIS"), ("cofins", "COFINS")):
            grupos[nome].update({
                "variante_candidata": "",
                "modalidade_calculo_candidata": "",
                "variante_fonte": "DECISAO_CONTADOR_PENDENTE",
                "estado_variante": "NAO_DEFINIDA",
                "grupo_opcional_xsd": True,
                "depende_decisao_contador": True,
                "destino_xml_futuro": f"NFe/infNFe/det/imposto/{grupo_xml}/*",
                "variante_confirmada": False,
            })
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
        self.assertFalse(resultado["dados_completos"])
        self.assertIn("MODBC_CANDIDATA_PENDENTE", {item["codigo"] for item in resultado["pendencias"]})
        self.assertFalse(resultado["permite_aplicar_modalidade_base_icms"])
        self.assertIn("PREDBC_CANDIDATA_PENDENTE", {item["codigo"] for item in resultado["pendencias"]})
        self.assertFalse(resultado["permite_aplicar_reducao_base_icms"])
        self.assertIn("VARIANTE_PIS_PENDENTE", {item["codigo"] for item in resultado["pendencias"]})
        self.assertIn("VARIANTE_COFINS_PENDENTE", {item["codigo"] for item in resultado["pendencias"]})
        self.assertFalse(resultado["permite_aplicar_variantes_pis_cofins"])
        self.assertFalse(resultado["escopo_fiscal_suportado"])
        self.assertFalse(resultado["permite_emissao"])

    def test_modbc_valida_continua_nao_confirmada_e_nao_altera_base(self):
        contrato = self.contrato()
        icms = contrato["itens"][0]["grupos"]["icms"]
        icms["modalidade_base_candidata"] = "3"
        resultado = validar_tributos_itens_devolucao(contrato)
        self.assertTrue(resultado["estrutura_valida"])
        self.assertTrue(resultado["origem_completa"])
        self.assertIn("MODBC_NAO_CONFIRMADA", {item["codigo"] for item in resultado["pendencias"]})
        self.assertEqual(icms["base"], "10.00")
        self.assertFalse(resultado["permite_aplicar_modalidade_base_icms"])

    def test_rejeita_codigo_fonte_ou_confirmacao_direta_de_modbc(self):
        contrato = self.contrato()
        icms = contrato["itens"][0]["grupos"]["icms"]
        icms.update({
            "modalidade_base_candidata": "4", "modalidade_base_fonte": "EMISSOR_ANTIGO",
            "modalidade_base_confirmada": True,
        })
        resultado = validar_tributos_itens_devolucao(contrato)
        self.assertFalse(resultado["estrutura_valida"])
        codigos = {item["codigo"] for item in resultado["erros"]}
        self.assertIn("MODBC_CANDIDATA_INVALIDA", codigos)
        self.assertIn("MODBC_FONTE_INVALIDA", codigos)
        self.assertIn("MODBC_CONFIRMACAO_DIRETA_PROIBIDA", codigos)

    def test_predbc_valida_continua_nao_confirmada_e_nao_altera_base(self):
        contrato = self.contrato()
        icms = contrato["itens"][0]["grupos"]["icms"]
        icms["reducao_base_candidata"] = "10.0000"
        resultado = validar_tributos_itens_devolucao(contrato)
        self.assertTrue(resultado["estrutura_valida"])
        self.assertTrue(resultado["origem_completa"])
        self.assertIn("PREDBC_NAO_CONFIRMADA", {item["codigo"] for item in resultado["pendencias"]})
        self.assertEqual(icms["base"], "10.00")
        self.assertFalse(resultado["permite_aplicar_reducao_base_icms"])

    def test_rejeita_percentual_fonte_ou_confirmacao_direta_de_predbc(self):
        contrato = self.contrato()
        icms = contrato["itens"][0]["grupos"]["icms"]
        icms.update({
            "reducao_base_candidata": "100.0001", "reducao_base_fonte": "CADASTRO_PRODUTO",
            "reducao_base_confirmada": True,
        })
        resultado = validar_tributos_itens_devolucao(contrato)
        self.assertFalse(resultado["estrutura_valida"])
        codigos = {item["codigo"] for item in resultado["erros"]}
        self.assertIn("PREDBC_CANDIDATA_INVALIDA", codigos)
        self.assertIn("PREDBC_FONTE_INVALIDA", codigos)
        self.assertIn("PREDBC_CONFIRMACAO_DIRETA_PROIBIDA", codigos)

    def test_variantes_percentuais_validas_continuam_nao_confirmadas_e_sem_efeito(self):
        contrato = self.contrato()
        pis = contrato["itens"][0]["grupos"]["pis"]
        cofins = contrato["itens"][0]["grupos"]["cofins"]
        pis.update({
            "variante_candidata": "PISAliq",
            "modalidade_calculo_candidata": "PERCENTUAL",
            "estado_variante": "CANDIDATA_NAO_CONFIRMADA",
        })
        cofins.update({
            "variante_candidata": "COFINSAliq",
            "modalidade_calculo_candidata": "PERCENTUAL",
            "estado_variante": "CANDIDATA_NAO_CONFIRMADA",
        })
        resultado = validar_tributos_itens_devolucao(contrato)
        self.assertTrue(resultado["estrutura_valida"])
        self.assertTrue(resultado["origem_completa"])
        self.assertIn("VARIANTE_PIS_NAO_CONFIRMADA", {item["codigo"] for item in resultado["pendencias"]})
        self.assertIn("VARIANTE_COFINS_NAO_CONFIRMADA", {item["codigo"] for item in resultado["pendencias"]})
        self.assertEqual((pis["base"], pis["aliquota"], pis["valor"]), ("10.00", "1.0000", "0.10"))
        self.assertEqual((cofins["base"], cofins["aliquota"], cofins["valor"]), ("10.00", "1.0000", "0.10"))
        self.assertFalse(resultado["permite_aplicar_variantes_pis_cofins"])

    def test_outras_operacoes_exigem_escolha_explicita_entre_percentual_e_quantidade(self):
        contrato = self.contrato()
        pis = contrato["itens"][0]["grupos"]["pis"]
        pis.update({
            "codigo": "99", "variante_candidata": "PISOutr",
            "modalidade_calculo_candidata": "", "estado_variante": "CANDIDATA_NAO_CONFIRMADA",
        })
        resultado = validar_tributos_itens_devolucao(contrato)
        self.assertFalse(resultado["estrutura_valida"])
        self.assertIn("MODALIDADE_PIS_INCOMPATIVEL", {item["codigo"] for item in resultado["erros"]})
        pis["modalidade_calculo_candidata"] = "QUANTIDADE"
        resultado = validar_tributos_itens_devolucao(contrato)
        self.assertTrue(resultado["estrutura_valida"])
        self.assertFalse(resultado["permite_aplicar_variantes_pis_cofins"])

    def test_rejeita_inferencia_incompatibilidade_ou_confirmacao_das_variantes(self):
        base = self.contrato()
        casos = (
            ("pis", {"variante_candidata": "PISNT", "modalidade_calculo_candidata": "SEM_CALCULO", "estado_variante": "CANDIDATA_NAO_CONFIRMADA"}, "CST_PIS_INCOMPATIVEL_COM_VARIANTE"),
            ("pis", {"variante_fonte": "CST_INFERIDO"}, "FONTE_VARIANTE_PIS_INVALIDA"),
            ("cofins", {"variante_confirmada": True}, "CONFIRMACAO_VARIANTE_COFINS_ANTECIPADA"),
            ("cofins", {"variante_candidata": "COFINSDesconhecido", "estado_variante": "CANDIDATA_NAO_CONFIRMADA"}, "VARIANTE_COFINS_INVALIDA"),
        )
        for grupo, alteracoes, codigo in casos:
            with self.subTest(grupo=grupo, codigo=codigo):
                contrato = self.contrato()
                contrato["itens"][0]["grupos"][grupo].update(alteracoes)
                resultado = validar_tributos_itens_devolucao(contrato)
                self.assertFalse(resultado["estrutura_valida"])
                self.assertIn(codigo, {item["codigo"] for item in resultado["erros"]})

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
