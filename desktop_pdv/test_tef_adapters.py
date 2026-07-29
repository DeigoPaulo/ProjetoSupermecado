import sys
import types
import unittest

import app
from devices.tef import RespostaTefInvalida, capacidades_adaptador_tef, validar_resposta_documento_pinpad


class AdaptadorFake:
    def __init__(self, *, provedor, modo, configuracao):
        self.provedor = provedor
        self.modo = modo
        self.configuracao = configuracao

    def processar(self, payload):
        return {
            "status": "ok",
            "aprovado": True,
            "transacao_externa_id": "STONE-123",
            "nsu": "987654",
            "codigo_autorizacao": "ABC123",
            "mensagem_processadora": "Aprovado pelo adaptador fake.",
        }

    def consultar(self, payload):
        return self.processar(payload)

    def estornar(self, payload):
        return {
            "status": "ok",
            "estornado": True,
            "estorno_transacao_id": "STONE-REF-123",
            "mensagem_processadora": "Estorno aprovado.",
        }


def criar_fake(**kwargs):
    return AdaptadorFake(**kwargs)


class RespostaInvalidaFake(AdaptadorFake):
    def processar(self, payload):
        return {"status": "ok", "aprovado": True}


def criar_fake_invalido(**kwargs):
    return RespostaInvalidaFake(**kwargs)


def criar_quebrado(**kwargs):
    raise RuntimeError("SDK indisponivel")


class AdaptadoresTefTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.modulo = types.ModuleType("tef_fake_testes")
        cls.modulo.criar = criar_fake
        cls.modulo.criar_invalido = criar_fake_invalido
        cls.modulo.criar_quebrado = criar_quebrado
        sys.modules[cls.modulo.__name__] = cls.modulo

    @classmethod
    def tearDownClass(cls):
        sys.modules.pop(cls.modulo.__name__, None)

    def test_producao_sem_driver_local_falha_sem_aprovar(self):
        ponte = app.PonteLocal(
            {
                "tef": {
                    "provedor": "STONE",
                    "modo_integracao": "DESKTOP_BRIDGE",
                    "simulador_permitido": False,
                }
            }
        )

        resultado = ponte.processPayment({"tipo": "DEBITO", "valor": "15.00"})

        self.assertEqual(resultado["status"], "erro")
        self.assertFalse(resultado["aprovado"])
        self.assertIn("nao instalado", resultado["mensagem"])

    def test_servidor_bloqueia_simulador_solicitado_localmente(self):
        ponte = app.PonteLocal(
            {"tef": {"provedor": "STONE", "simulador_permitido": False}},
            {"tef": {"adaptador": "SIMULADOR"}},
        )

        resultado = ponte.processPayment({"tipo": "PIX", "valor": "10.00"})

        self.assertEqual(resultado["status"], "erro")
        self.assertIn("nao foi autorizado", resultado["mensagem"])

    def test_adaptador_local_homologavel_usa_contrato_unico(self):
        ponte = app.PonteLocal(
            {
                "tef": {
                    "provedor": "STONE",
                    "modo_integracao": "DESKTOP_BRIDGE",
                    "simulador_permitido": False,
                }
            },
            {
                "tef": {
                    "adaptador": "tef_fake_testes:criar",
                    "configuracao": {"estabelecimento": "LOJA-1"},
                }
            },
        )

        pagamento = ponte.processPayment({"tipo": "CREDITO", "valor": "20,50"})
        estorno = ponte.refundPayment(
            {
                "tipo": "CREDITO",
                "valor": "20,50",
                "transacao_externa_id": pagamento["transacao_externa_id"],
            }
        )

        self.assertTrue(pagamento["aprovado"])
        self.assertEqual(pagamento["provedor"], "STONE")
        self.assertEqual(pagamento["valor"], "20.50")
        self.assertTrue(estorno["estornado"])
        self.assertEqual(estorno["estorno_transacao_id"], "STONE-REF-123")

    def test_resposta_incompleta_do_driver_nunca_aprova_venda(self):
        ponte = app.PonteLocal(
            {"tef": {"provedor": "STONE", "simulador_permitido": False}},
            {"tef": {"adaptador": "tef_fake_testes:criar_invalido"}},
        )

        resultado = ponte.processPayment({"tipo": "DEBITO", "valor": "9.90"})

        self.assertEqual(resultado["status"], "erro")
        self.assertFalse(resultado["aprovado"])
        self.assertIn("autorizacao completa", resultado["mensagem"])


    def test_excecao_do_sdk_vira_falha_controlada(self):
        ponte = app.PonteLocal(
            {"tef": {"provedor": "STONE", "simulador_permitido": False}},
            {"tef": {"adaptador": "tef_fake_testes:criar_quebrado"}},
        )

        resultado = ponte.processPayment({"tipo": "DEBITO", "valor": "9.90"})

        self.assertEqual(resultado["status"], "erro")
        self.assertFalse(resultado["aprovado"])
        self.assertIn("falhou ao inicializar", resultado["mensagem"])


    def test_capacidade_opcional_nao_quebra_driver_legado(self):
        adaptador = AdaptadorFake(provedor="STONE", modo="DESKTOP_BRIDGE", configuracao={})
        capacidades = capacidades_adaptador_tef(adaptador)
        self.assertFalse(capacidades["captura_documento_consumidor"])
        self.assertEqual(capacidades["contrato"], "pdv_tef_capabilities_v1")

    def test_valida_documento_recebido_do_pinpad(self):
        cpf = validar_resposta_documento_pinpad({"status": "ok", "documento": "529.982.247-25", "tipo": "CPF"})
        cnpj = validar_resposta_documento_pinpad({"status": "ok", "documento": "11.222.333/0001-81", "tipo": "CNPJ"})
        self.assertEqual(cpf["documento"], "52998224725")
        self.assertEqual(cnpj["documento"], "11222333000181")
        with self.assertRaises(RespostaTefInvalida):
            validar_resposta_documento_pinpad({"status": "ok", "documento": "52998224724", "tipo": "CPF"})


if __name__ == "__main__":
    unittest.main()
