from copy import deepcopy

from django.test import SimpleTestCase

from .confronto_cadastro_xml_fornecedor import (
    construir_confronto_cadastro_xml_fornecedor,
    validar_confronto_cadastro_xml_fornecedor,
)


class ConfrontoCadastroXmlFornecedorTests(SimpleTestCase):
    def dados(self):
        cadastro = {
            "cnpj": "11.111.111/0001-11", "razao_social": "Fornecedor Ágil Ltda",
            "nome_fantasia": "Fornecedor Ágil", "indicador_ie": "1", "inscricao_estadual": "123.456.789",
            "logradouro": "Rua do Fornecedor", "numero": "20", "complemento": "",
            "bairro": "Centro", "codigo_municipio_ibge": "5208707", "municipio": "Goiânia",
            "uf": "GO", "cep": "74000-000",
        }
        xml = {
            "cnpj": "11111111000111", "razao_social": "FORNECEDOR AGIL LTDA",
            "nome_fantasia": "Fornecedor Agil", "inscricao_estadual": "123456789",
            "logradouro": "Rua do Fornecedor", "numero": "20", "complemento": "",
            "bairro": "Centro", "codigo_municipio": "5208707", "municipio": "Goiania",
            "uf": "GO", "cep": "74000000",
        }
        return cadastro, xml

    def test_normaliza_formatacao_sem_esconder_divergencia_real(self):
        cadastro, xml = self.dados()
        resultado = construir_confronto_cadastro_xml_fornecedor(
            fornecedor_id=7, cadastro=cadastro, xml_historico=xml
        )
        campos = {item["campo"]: item for item in resultado["conteudo"]["campos"]}
        self.assertTrue(resultado["validacao"]["estrutura_valida"])
        self.assertTrue(resultado["validacao"]["cadastro_completo"])
        self.assertTrue(resultado["validacao"]["xml_historico_completo"])
        self.assertTrue(resultado["validacao"]["sem_divergencias"])
        self.assertEqual(campos["cnpj"]["estado"], "COINCIDENTE")
        self.assertEqual(campos["razao_social"]["estado"], "COINCIDENTE")
        self.assertEqual(campos["indicador_ie"]["estado"], "INFORMADO_SOMENTE_NO_CADASTRO")

    def test_aponta_ausencias_e_divergencias_sem_escolher_fonte(self):
        cadastro, xml = self.dados()
        cadastro["logradouro"] = "Avenida Atual"
        cadastro["cep"] = ""
        resultado = construir_confronto_cadastro_xml_fornecedor(
            fornecedor_id=7, cadastro=cadastro, xml_historico=xml
        )
        campos = {item["campo"]: item for item in resultado["conteudo"]["campos"]}
        self.assertEqual(campos["logradouro"]["estado"], "DIVERGENTE")
        self.assertEqual(campos["cep"]["estado"], "AUSENTE_NO_CADASTRO")
        self.assertFalse(resultado["validacao"]["cadastro_completo"])
        self.assertFalse(resultado["validacao"]["sem_divergencias"])
        self.assertEqual(resultado["conteudo"]["politica"]["fonte_preferencial_automatica"], "")
        self.assertFalse(resultado["validacao"]["permite_sobrescrever"])
        self.assertFalse(resultado["validacao"]["permite_emissao"])

    def test_xml_invalido_permanece_bloqueado(self):
        cadastro, _xml = self.dados()
        resultado = construir_confronto_cadastro_xml_fornecedor(
            fornecedor_id=7, cadastro=cadastro, xml_historico={}, erro_xml="NFE_NAO_AUTORIZADA"
        )
        self.assertFalse(resultado["validacao"]["xml_historico_completo"])
        self.assertIn("NFE_NAO_AUTORIZADA", {item["codigo"] for item in resultado["validacao"]["bloqueios"]})
        self.assertFalse(resultado["validacao"]["permite_focus"])
        self.assertFalse(resultado["validacao"]["permite_sefaz_direta"])

    def test_nao_declara_cadastro_completo_com_formatos_ou_ie_incoerentes(self):
        cadastro, xml = self.dados()
        cadastro.update({"cnpj": "123", "codigo_municipio_ibge": "52", "cep": "74", "uf": "G", "indicador_ie": "9"})
        resultado = construir_confronto_cadastro_xml_fornecedor(
            fornecedor_id=7, cadastro=cadastro, xml_historico=xml
        )
        self.assertFalse(resultado["validacao"]["cadastro_completo"])
        self.assertIn(
            "CADASTRO_FISCAL_INCOMPLETO",
            {item["codigo"] for item in resultado["validacao"]["bloqueios"]},
        )
        self.assertFalse(resultado["validacao"]["permite_emissao"])

    def test_rejeita_estado_resumo_ou_politica_adulterados(self):
        cadastro, xml = self.dados()
        conteudo = deepcopy(construir_confronto_cadastro_xml_fornecedor(
            fornecedor_id=7, cadastro=cadastro, xml_historico=xml
        )["conteudo"])
        conteudo["campos"][0]["estado"] = "DIVERGENTE"
        conteudo["campos"][1] = deepcopy(conteudo["campos"][0])
        conteudo["resumo"]["COINCIDENTE"] = 0
        conteudo["politica"]["sobrescrever_cadastro"] = True
        resultado = validar_confronto_cadastro_xml_fornecedor(conteudo)
        self.assertFalse(resultado["estrutura_valida"])
        codigos = {item["codigo"] for item in resultado["erros"]}
        self.assertIn("ESTADO_DIVERGENTE", codigos)
        self.assertIn("CAMPOS_CONFRONTO_DIVERGENTES", codigos)
        self.assertIn("RESUMO_DIVERGENTE", codigos)
        self.assertIn("POLITICA_INVALIDA", codigos)
        self.assertFalse(resultado["permite_emissao"])
