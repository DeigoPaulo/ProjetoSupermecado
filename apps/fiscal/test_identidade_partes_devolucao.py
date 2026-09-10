from django.test import SimpleTestCase

from .identidade_partes_devolucao import (
    CONTRATO_IDENTIDADE_PARTES,
    validar_identidade_partes_devolucao,
)


class IdentidadePartesDevolucaoTests(SimpleTestCase):
    def contrato(self):
        endereco = {
            "cnpj": "11111111000111",
            "razao_social": "Parte fiscal",
            "nome_fantasia": "",
            "inscricao_estadual": "123456789",
            "logradouro": "Rua Um",
            "numero": "10",
            "complemento": "",
            "bairro": "Centro",
            "codigo_municipio": "5208707",
            "municipio": "Goiânia",
            "uf": "GO",
            "cep": "74000000",
        }
        return {
            "contrato": CONTRATO_IDENTIDADE_PARTES,
            "operacao": "DEVOLUCAO_COMPRA",
            "permite_emissao": False,
            "identificacao": {
                "modelo": "55", "finalidade": "4", "tipo_operacao": "1",
                "natureza_operacao": "Devolução de compra", "codigo_municipio_fato_gerador": "5208707",
                "destino_operacao": "1", "consumidor_final": "0", "presenca_comprador": "9",
            },
            "emitente": {
                "fonte": "FILIAL_E_CONFIGURACAO_FISCAL", "filial_id": 1,
                "crt": "3", **endereco,
            },
            "destinatario": {
                "fonte": "XML_ORIGINAL_E_CADASTRO_FORNECEDOR", "fornecedor_id": 2,
                **{**endereco, "cnpj": "22222222000122"},
            },
        }

    def test_contrato_completo_e_nao_emissivo(self):
        resultado = validar_identidade_partes_devolucao(self.contrato())
        self.assertTrue(resultado["estrutura_valida"])
        self.assertTrue(resultado["dados_completos"])
        self.assertFalse(resultado["permite_gerar_xml"])
        self.assertFalse(resultado["permite_emissao"])

    def test_campos_ausentes_ficam_explicitos_sem_liberar_emissao(self):
        contrato = self.contrato()
        contrato["identificacao"]["consumidor_final"] = ""
        contrato["emitente"]["inscricao_estadual"] = ""
        contrato["destinatario"]["cep"] = ""
        resultado = validar_identidade_partes_devolucao(contrato)
        self.assertTrue(resultado["estrutura_valida"])
        self.assertFalse(resultado["dados_completos"])
        self.assertEqual(
            {item["codigo"] for item in resultado["pendencias"]},
            {"CONSUMIDOR_FINAL_PENDENTE", "INSCRICAO_ESTADUAL_PENDENTE", "CEP_PENDENTE"},
        )
        self.assertFalse(resultado["permite_emissao"])

    def test_rejeita_formato_contrato_e_tentativa_de_emissao(self):
        for alterar in (
            lambda item: item.update({"campo_extra": True}),
            lambda item: item.update({"permite_emissao": True}),
            lambda item: item["identificacao"].update({"modelo": "65"}),
            lambda item: item["emitente"].update({"fonte": "FORMULARIO_LIVRE"}),
        ):
            contrato = self.contrato()
            alterar(contrato)
            resultado = validar_identidade_partes_devolucao(contrato)
            self.assertFalse(resultado["estrutura_valida"])
            self.assertFalse(resultado["permite_emissao"])
