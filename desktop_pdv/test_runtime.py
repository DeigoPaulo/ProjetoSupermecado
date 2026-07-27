import os
import unittest
from contextlib import contextmanager
from unittest.mock import patch

import app
from devices.runtime import (
    InstanciaPdvEmUso,
    instancia_unica_terminal,
    nome_mutex_terminal,
)


class RuntimePdvTests(unittest.TestCase):
    def test_nome_mutex_nao_expoe_identificador_do_terminal(self):
        nome = nome_mutex_terminal("caixa-principal-segredo")

        self.assertTrue(nome.startswith("Local\\SupermercadoPDV-"))
        self.assertNotIn("caixa-principal-segredo", nome)
        self.assertEqual(nome, nome_mutex_terminal("caixa-principal-segredo"))
        self.assertNotEqual(nome, nome_mutex_terminal("outro-caixa"))

    def test_identificador_vazio_e_rejeitado(self):
        with self.assertRaisesRegex(ValueError, "Identificador do terminal"):
            nome_mutex_terminal(" ")

    @unittest.skipUnless(os.name == "nt", "Mutex nomeado exige Windows")
    def test_segunda_instancia_do_mesmo_terminal_e_bloqueada(self):
        with instancia_unica_terminal("terminal-teste-instancia-unica"):
            with self.assertRaisesRegex(InstanciaPdvEmUso, "ja esta aberto"):
                with instancia_unica_terminal("terminal-teste-instancia-unica"):
                    pass

    @unittest.skipUnless(os.name == "nt", "Mutex nomeado exige Windows")
    def test_mutex_e_liberado_ao_fechar_contexto(self):
        with instancia_unica_terminal("terminal-teste-liberacao"):
            pass

        with instancia_unica_terminal("terminal-teste-liberacao"):
            pass


    def test_reconfiguracao_reserva_identidade_atual_antes_da_ativacao(self):
        eventos = []

        @contextmanager
        def mutex_fake(terminal_id):
            eventos.append(("bloqueou", terminal_id))
            try:
                yield
            finally:
                eventos.append(("liberou", terminal_id))

        atual = {"terminal_id": "terminal-atual"}
        reconfigurada = {"terminal_id": "terminal-atual"}

        with patch("app.carregar_configuracao", return_value=atual), patch(
            "app.instancia_unica_terminal", side_effect=mutex_fake
        ), patch(
            "app.ativar_terminal", side_effect=lambda config: eventos.append(("ativou", config["terminal_id"])) or reconfigurada
        ), patch(
            "app._executar_interface_pdv", side_effect=lambda config: eventos.append(("abriu", config["terminal_id"]))
        ):
            app.executar(reconfigurar=True)

        self.assertEqual(
            eventos,
            [
                ("bloqueou", "terminal-atual"),
                ("ativou", "terminal-atual"),
                ("abriu", "terminal-atual"),
                ("liberou", "terminal-atual"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
