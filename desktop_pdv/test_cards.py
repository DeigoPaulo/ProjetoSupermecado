import unittest

from devices.cards import ErroLeitorCartao, ler_uid_pcsc


class FakePcsc:
    def __init__(self, uid):
        self.uid = uid
        self.preferido = None

    def ler_uid(self, leitor_preferido=""):
        self.preferido = leitor_preferido
        return self.uid


class LeitorCartaoTests(unittest.TestCase):
    def test_normaliza_uid_sem_expor_outros_dados(self):
        api = FakePcsc("04 a1 b2 c3")
        self.assertEqual(ler_uid_pcsc("ACR", api=api), "04A1B2C3")
        self.assertEqual(api.preferido, "ACR")

    def test_rejeita_identificador_invalido(self):
        with self.assertRaises(ErroLeitorCartao):
            ler_uid_pcsc(api=FakePcsc("UID: segredo"))


if __name__ == "__main__":
    unittest.main()
