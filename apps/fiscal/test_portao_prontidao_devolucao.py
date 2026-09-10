from copy import deepcopy

from django.test import SimpleTestCase

from .portao_prontidao_devolucao import (
    PORTOES_EXTERNOS,
    SUBCONTRATOS,
    construir_portao_prontidao,
    validar_portao_prontidao,
)


class PortaoProntidaoDevolucaoTests(SimpleTestCase):
    def extracao_completa(self):
        resultado = {}
        for grupo, contrato, chave_validacao, chave_origem in SUBCONTRATOS:
            validacao = {
                "estrutura_valida": True,
                "permite_gerar_xml": False,
                "permite_emissao": False,
                "bloqueios": [{"grupo": grupo, "codigo": "GERACAO_NAO_IMPLEMENTADA"}],
            }
            if grupo == "envelope":
                resultado.update({"conteudo": {"contrato": contrato}, "validacao": validacao})
            elif chave_validacao == "validacao_estrutural":
                resultado[grupo] = {
                    "conteudo": {"contrato": contrato},
                    "validacao_estrutural": validacao,
                    chave_origem: True,
                    "bloqueios": validacao["bloqueios"],
                    "permite_gerar_xml": False,
                    "permite_emissao": False,
                }
            else:
                validacao[chave_origem] = True
                resultado[grupo] = {"conteudo": {"contrato": contrato}, "validacao": validacao}
        return resultado

    def test_consolida_estrutura_sem_liberar_etapa_fiscal(self):
        portao = construir_portao_prontidao(self.extracao_completa())
        self.assertTrue(portao["validacao"]["estrutura_valida"])
        self.assertTrue(portao["validacao"]["estrutura_consolidada"])
        self.assertTrue(portao["validacao"]["origens_conferidas"])
        self.assertEqual(len(portao["conteudo"]["verificacoes"]), 13)
        self.assertTrue(portao["conteudo"]["todos_nao_emissivos"])
        self.assertFalse(portao["validacao"]["pronto_para_gerador"])
        self.assertFalse(portao["validacao"]["pronto_para_homologacao"])
        self.assertFalse(portao["validacao"]["permite_gerar_xml"])
        self.assertTrue(all(valor is False for valor in portao["conteudo"]["portoes_externos"].values()))
        codigos = {item["codigo"] for item in portao["conteudo"]["bloqueios_consolidados"]}
        self.assertEqual({codigo for _, codigo in PORTOES_EXTERNOS} - codigos, set())

    def test_subcontrato_nao_pode_liberar_xml_ou_emissao(self):
        extracao = self.extracao_completa()
        extracao["produtos"]["validacao"]["permite_gerar_xml"] = True
        extracao["transporte"]["validacao"]["permite_emissao"] = True
        portao = construir_portao_prontidao(extracao)
        self.assertFalse(portao["validacao"]["estrutura_valida"])
        self.assertFalse(portao["conteudo"]["todos_nao_emissivos"])
        codigos = {item["codigo"] for item in portao["validacao"]["erros"]}
        self.assertIn("SUBCONTRATO_TENTOU_LIBERAR_XML", codigos)
        self.assertIn("SUBCONTRATO_TENTOU_LIBERAR_EMISSAO", codigos)
        self.assertFalse(portao["validacao"]["permite_emissao"])

    def test_rejeita_ativacao_externa_ou_mudanca_da_politica(self):
        conteudo = construir_portao_prontidao(self.extracao_completa())["conteudo"]
        alterado = deepcopy(conteudo)
        alterado["portoes_externos"]["paridade_sefaz_direta_validada"] = True
        alterado["politica"]["permitir_emissao"] = True
        resultado = validar_portao_prontidao(alterado)
        self.assertFalse(resultado["estrutura_valida"])
        codigos = {item["codigo"] for item in resultado["erros"]}
        self.assertIn("PORTAO_EXTERNO_NAO_PODE_SER_ATIVADO", codigos)
        self.assertIn("POLITICA_DE_BLOQUEIO_INVALIDA", codigos)
        self.assertFalse(resultado["permite_gerar_xml"])
        self.assertFalse(resultado["permite_emissao"])
