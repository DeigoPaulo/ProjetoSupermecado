import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app
from devices.secrets import PREFIXO_DPAPI, desproteger_segredo, proteger_segredo


@unittest.skipUnless(os.name == "nt", "DPAPI exige Windows")
class SegredosTerminalTests(unittest.TestCase):
    def test_dpapi_protege_e_recupera_para_o_mesmo_usuario(self):
        protegido = proteger_segredo("chave-super-secreta")

        self.assertTrue(protegido.startswith(PREFIXO_DPAPI))
        self.assertNotIn("chave-super-secreta", protegido)
        self.assertEqual(desproteger_segredo(protegido), "chave-super-secreta")

    def test_configuracao_persistida_nao_contem_chave_em_texto(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "terminal" / "config.json"
            config = {
                "servidor_base_url": "http://servidor.local",
                "terminal_id": "terminal-1",
                "terminal_chave": "segredo-que-nao-pode-vazar",
            }
            with patch.dict(os.environ, {"SUPERMERCADO_PDV_CONFIG": str(caminho)}):
                app.salvar_configuracao(config)
                conteudo_persistido = caminho.read_text(encoding="utf-8")
                persistida = json.loads(conteudo_persistido)
                carregada = app.carregar_configuracao()
                seguranca = app.PonteLocal({}, carregada).status()["seguranca_local"]

        self.assertNotIn("terminal_chave", persistida)
        self.assertTrue(persistida["terminal_chave_protegida"].startswith(PREFIXO_DPAPI))
        self.assertNotIn("segredo-que-nao-pode-vazar", conteudo_persistido)
        self.assertEqual(carregada["terminal_chave"], "segredo-que-nao-pode-vazar")
        self.assertTrue(seguranca["credencial_protegida"])
        self.assertEqual(seguranca["contrato"], "pdv_local_secret_v1")
        self.assertEqual(seguranca["contrato_instancia"], "pdv_single_instance_v1")
        self.assertTrue(seguranca["instancia_unica_por_terminal"])

    def test_configuracao_legada_e_migrada_automaticamente(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "terminal" / "config.json"
            caminho.parent.mkdir(parents=True)
            caminho.write_text(
                json.dumps(
                    {
                        "servidor_base_url": "http://servidor.local/",
                        "terminal_id": "terminal-legado",
                        "terminal_chave": "segredo-legado",
                    }
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"SUPERMERCADO_PDV_CONFIG": str(caminho)}):
                carregada = app.carregar_configuracao()
                migrada = json.loads(caminho.read_text(encoding="utf-8"))

        self.assertEqual(carregada["terminal_chave"], "segredo-legado")
        self.assertEqual(carregada["servidor_base_url"], "http://servidor.local")
        self.assertNotIn("terminal_chave", migrada)
        self.assertTrue(migrada["terminal_chave_protegida"].startswith(PREFIXO_DPAPI))

    def test_chave_corrompida_bloqueia_inicializacao(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "terminal" / "config.json"
            caminho.parent.mkdir(parents=True)
            caminho.write_text(
                json.dumps(
                    {
                        "servidor_base_url": "http://servidor.local",
                        "terminal_id": "terminal-1",
                        "terminal_chave_protegida": f"{PREFIXO_DPAPI}invalida",
                    }
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"SUPERMERCADO_PDV_CONFIG": str(caminho)}):
                with self.assertRaisesRegex(RuntimeError, "chave protegida"):
                    app.carregar_configuracao()


    def test_parametros_tef_sao_protegidos_e_restaurados_somente_em_memoria(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "terminal" / "config.json"
            config = {
                "servidor_base_url": "http://servidor.local",
                "terminal_id": "terminal-tef",
                "terminal_chave": "chave-terminal",
                "tef": {
                    "adaptador": "drivers.stone:criar",
                    "configuracao": {"token": "token-adquirente-secreto", "estabelecimento": "LOJA-1"},
                },
            }
            with patch.dict(os.environ, {"SUPERMERCADO_PDV_CONFIG": str(caminho)}):
                app.salvar_configuracao(config)
                conteudo = caminho.read_text(encoding="utf-8")
                persistida = json.loads(conteudo)
                carregada = app.carregar_configuracao()
                seguranca = app.PonteLocal({}, carregada).status()["seguranca_local"]

        self.assertNotIn("configuracao", persistida["tef"])
        self.assertTrue(persistida["tef"]["configuracao_protegida"].startswith(PREFIXO_DPAPI))
        self.assertNotIn("token-adquirente-secreto", conteudo)
        self.assertEqual(carregada["tef"]["configuracao"]["token"], "token-adquirente-secreto")
        self.assertTrue(seguranca["configuracao_tef_protegida"])

    def test_parametros_tef_legados_sao_migrados_automaticamente(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "terminal" / "config.json"
            caminho.parent.mkdir(parents=True)
            caminho.write_text(
                json.dumps(
                    {
                        "servidor_base_url": "http://servidor.local",
                        "terminal_id": "terminal-legado-tef",
                        "terminal_chave": "chave-legada",
                        "tef": {
                            "adaptador": "drivers.rede:criar",
                            "configuracao": {"token": "token-legado"},
                        },
                    }
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"SUPERMERCADO_PDV_CONFIG": str(caminho)}):
                carregada = app.carregar_configuracao()
                migrada = json.loads(caminho.read_text(encoding="utf-8"))

        self.assertEqual(carregada["tef"]["configuracao"]["token"], "token-legado")
        self.assertNotIn("configuracao", migrada["tef"])
        self.assertNotIn("token-legado", json.dumps(migrada))
        self.assertTrue(migrada["tef"]["configuracao_protegida"].startswith(PREFIXO_DPAPI))

    def test_parametros_tef_protegidos_corrompidos_bloqueiam_inicializacao(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "terminal" / "config.json"
            caminho.parent.mkdir(parents=True)
            caminho.write_text(
                json.dumps(
                    {
                        "servidor_base_url": "http://servidor.local",
                        "terminal_id": "terminal-1",
                        "terminal_chave_protegida": proteger_segredo("chave-valida"),
                        "tef": {
                            "adaptador": "drivers.stone:criar",
                            "configuracao_protegida": f"{PREFIXO_DPAPI}invalida",
                        },
                    }
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"SUPERMERCADO_PDV_CONFIG": str(caminho)}):
                with self.assertRaisesRegex(RuntimeError, "configuracao TEF protegida"):
                    app.carregar_configuracao()


if __name__ == "__main__":
    unittest.main()
