import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app
from devices.printers import ErroDescobertaImpressoras, listar_impressoras_windows
from devices.labels import montar_etiquetas_epl, montar_etiquetas_nativas, montar_etiquetas_ppla, montar_etiquetas_zpl
from devices.printing import ErroImpressao, montar_cupom_escpos, montar_pulso_gaveta_escpos, montar_texto_cupom
from devices.scales import ler_peso_balanca, normalizar_configuracao_balanca


class RespostaJson:
    def __init__(self, payload=None):
        self.payload = payload or {"status": "ok", "terminal": {"nome": "Caixa 01"}}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


class AppDesktopTests(unittest.TestCase):
    def test_salva_e_carrega_configuracao_fora_do_diretorio_do_executavel(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "terminal" / "config.json"
            config = {
                "servidor_base_url": "http://servidor.local/",
                "terminal_id": "terminal-1",
                "terminal_chave": "segredo",
            }
            with patch.dict(os.environ, {"SUPERMERCADO_PDV_CONFIG": str(caminho)}):
                app.salvar_configuracao(config)
                carregada = app.carregar_configuracao()

            self.assertTrue(caminho.exists())
            self.assertEqual(carregada["servidor_base_url"], "http://servidor.local")
            self.assertEqual(carregada["terminal_chave"], "segredo")

    def test_bootstrap_envia_identidade_e_chave_do_terminal(self):
        config = {
            "servidor_base_url": "http://servidor.local",
            "terminal_id": "terminal-1",
            "terminal_chave": "segredo",
        }
        with patch("app.urlopen", return_value=RespostaJson()) as urlopen_mock:
            resposta = app.validar_terminal(config)

        requisicao = urlopen_mock.call_args.args[0]
        self.assertEqual(resposta["status"], "ok")
        self.assertEqual(requisicao.get_header("X-terminal-id"), "terminal-1")
        self.assertEqual(requisicao.get_header("X-terminal-key"), "segredo")
        self.assertEqual(requisicao.get_header("X-pdv-version"), app.APP_VERSION)
        self.assertTrue(requisicao.full_url.endswith("/pdv/api/terminal/bootstrap/"))

    def test_bootstrap_operacional_salva_cache_e_abre_offline_quando_servidor_cai(self):
        payload = {
            "status": "ok",
            "terminal": {"nome": "Caixa 01", "permite_modo_offline": True},
            "recursos": {"modo_offline_permitido": True},
        }
        config = {
            "servidor_base_url": "http://servidor.local",
            "terminal_id": "terminal-1",
            "terminal_chave": "segredo",
        }
        with tempfile.TemporaryDirectory() as pasta:
            config_path = Path(pasta) / "terminal" / "config.json"
            with patch.dict(os.environ, {"SUPERMERCADO_PDV_CONFIG": str(config_path)}):
                with patch("app.validar_terminal", return_value=payload):
                    online = app.obter_bootstrap_operacional(config)
                with patch("app.validar_terminal", side_effect=app.ServidorPdvIndisponivel("Servidor PDV indisponivel: sem rede")):
                    offline = app.obter_bootstrap_operacional(config)
                diagnostico = app.listar_eventos_dispositivo()

        self.assertEqual(online["status"], "ok")
        self.assertEqual(offline["status"], "ok")
        self.assertEqual(offline["status_conexao"], "offline")
        self.assertIn("sem rede", offline["mensagem_conexao"])
        self.assertEqual(diagnostico["eventos"][-1]["tipo"], "bootstrap")
        self.assertEqual(diagnostico["eventos"][-1]["payload"]["status"], "offline")

    def test_bootstrap_offline_nao_esconde_terminal_recusado(self):
        payload = {
            "status": "ok",
            "terminal": {"nome": "Caixa 01", "permite_modo_offline": True},
            "recursos": {"modo_offline_permitido": True},
        }
        config = {
            "servidor_base_url": "http://servidor.local",
            "terminal_id": "terminal-1",
            "terminal_chave": "segredo",
        }
        with tempfile.TemporaryDirectory() as pasta:
            config_path = Path(pasta) / "terminal" / "config.json"
            with patch.dict(os.environ, {"SUPERMERCADO_PDV_CONFIG": str(config_path)}):
                app.salvar_bootstrap_cache(payload)
                with patch("app.validar_terminal", side_effect=app.TerminalRecusado("Terminal recusado pelo servidor")):
                    with self.assertRaises(app.TerminalRecusado):
                        app.obter_bootstrap_operacional(config)

    def test_identifica_atualizacao_opcional_e_obrigatoria(self):
        opcional = app.verificar_versao(
            {"aplicativo": {"versao_vigente": "0.2.0", "atualizacao_disponivel": True}}
        )
        obrigatoria = app.verificar_versao(
            {
                "aplicativo": {
                    "versao_vigente": "1.0.0",
                    "atualizacao_disponivel": True,
                    "atualizacao_obrigatoria": True,
                }
            }
        )

        self.assertTrue(opcional["atualizacao_disponivel"])
        self.assertFalse(opcional["atualizacao_obrigatoria"])
        self.assertTrue(obrigatoria["atualizacao_obrigatoria"])

    @patch("devices.printers.platform.system", return_value="Windows")
    @patch("devices.printers.subprocess.run")
    def test_lista_impressoras_instaladas_no_windows(self, executar_mock, _sistema_mock):
        executar_mock.return_value.returncode = 0
        executar_mock.return_value.stderr = ""
        executar_mock.return_value.stdout = json.dumps(
            [
                {
                    "Name": "EPSON TM-T20",
                    "PortName": "USB001",
                    "DriverName": "EPSON",
                    "Default": True,
                    "WorkOffline": False,
                    "PrinterStatus": 3,
                },
                {
                    "Name": "Microsoft Print to PDF",
                    "PortName": "PORTPROMPT:",
                    "DriverName": "Microsoft",
                    "Default": False,
                    "WorkOffline": False,
                    "PrinterStatus": 3,
                },
            ]
        )

        impressoras = listar_impressoras_windows()

        self.assertEqual(len(impressoras), 2)
        self.assertEqual(impressoras[0]["nome"], "EPSON TM-T20")
        self.assertEqual(impressoras[0]["porta"], "USB001")
        self.assertTrue(impressoras[0]["padrao"])
        self.assertFalse(impressoras[0]["offline"])
        self.assertFalse(executar_mock.call_args.kwargs["shell"] if "shell" in executar_mock.call_args.kwargs else False)

    def test_ponte_local_expoe_impressora_padrao_e_trata_falha(self):
        ponte = app.PonteLocal({"terminal": {"nome": "Caixa 01"}})
        with patch("app.listar_impressoras_windows", return_value=[{"nome": "EPSON", "padrao": True}]):
            sucesso = ponte.listar_impressoras()
        with patch("app.listar_impressoras_windows", side_effect=ErroDescobertaImpressoras("servico indisponivel")):
            falha = ponte.listar_impressoras()

        self.assertEqual(sucesso["padrao"], "EPSON")
        self.assertEqual(sucesso["total"], 1)
        self.assertEqual(falha["status"], "erro")
        self.assertIn("indisponivel", falha["mensagem"])

    def test_ponte_local_expoe_balanca_com_fallback_manual(self):
        ponte = app.PonteLocal(
            {
                "dispositivos": {
                    "balanca": {
                        "contrato": "pdv_scale_v1",
                        "habilitada": True,
                        "protocolo": "SERIAL",
                        "porta": "COM3",
                        "modelo": "Toledo Prix",
                        "leitura_automatica": True,
                        "fallback_manual": True,
                    }
                }
            }
        )

        config = ponte.configuracao_balanca()
        leitura = ponte.ler_peso_balanca()

        self.assertEqual(config["contrato"], "pdv_scale_v1")
        self.assertEqual(config["porta"], "COM3")
        self.assertTrue(config["leitura_automatica"])
        self.assertEqual(config["unidade_padrao"], "KG")
        self.assertEqual(leitura["status"], "erro")
        self.assertTrue(leitura["fallback_manual"])
        self.assertIn("Driver fisico", leitura["mensagem"])
        self.assertEqual(ponte.scaleConfig()["contrato"], "pdv_scale_v1")
        self.assertEqual(ponte.readScale()["status"], "erro")

    def test_falha_de_balanca_grava_log_local_de_dispositivo(self):
        with tempfile.TemporaryDirectory() as pasta:
            config_path = Path(pasta) / "terminal" / "config.json"
            with patch.dict(os.environ, {"SUPERMERCADO_PDV_CONFIG": str(config_path)}):
                ponte = app.PonteLocal(
                    {
                        "dispositivos": {
                            "balanca": {
                                "habilitada": True,
                                "protocolo": "SERIAL",
                                "porta": "COM3",
                                "leitura_automatica": True,
                                "fallback_manual": True,
                            }
                        }
                    }
                )

                leitura = ponte.readScale()
                diagnostico = ponte.deviceLogs()
                linhas = app.caminho_log_dispositivos().read_text(encoding="utf-8").splitlines()

        evento = json.loads(linhas[-1])
        self.assertEqual(leitura["status"], "erro")
        self.assertEqual(diagnostico["status"], "ok")
        self.assertEqual(diagnostico["total"], 1)
        self.assertEqual(diagnostico["eventos"][0]["tipo"], "balanca")
        self.assertEqual(evento["tipo"], "balanca")
        self.assertEqual(evento["payload"]["status"], "erro")
        self.assertEqual(evento["payload"]["porta"], "COM3")
        self.assertTrue(evento["payload"]["fallback_manual"])

    def test_diagnostico_local_limita_eventos_de_dispositivo(self):
        with tempfile.TemporaryDirectory() as pasta:
            config_path = Path(pasta) / "terminal" / "config.json"
            with patch.dict(os.environ, {"SUPERMERCADO_PDV_CONFIG": str(config_path)}):
                for indice in range(3):
                    app.registrar_evento_dispositivo("balanca", {"status": "erro", "indice": indice})

                eventos = app.listar_eventos_dispositivo(limite=2)

        self.assertEqual(eventos["status"], "ok")
        self.assertEqual(eventos["total"], 3)
        self.assertEqual(len(eventos["eventos"]), 2)
        self.assertEqual(eventos["eventos"][0]["payload"]["indice"], 1)
        self.assertEqual(eventos["eventos"][1]["payload"]["indice"], 2)

    def test_sincroniza_diagnosticos_locais_com_servidor_do_terminal(self):
        with tempfile.TemporaryDirectory() as pasta:
            config_path = Path(pasta) / "terminal" / "config.json"
            config = {
                "servidor_base_url": "http://servidor.local",
                "terminal_id": "terminal-1",
                "terminal_chave": "segredo",
            }
            with patch.dict(os.environ, {"SUPERMERCADO_PDV_CONFIG": str(config_path)}):
                app.salvar_configuracao(config)
                app.registrar_evento_dispositivo("balanca", {"status": "erro", "indice": 1})
                app.registrar_evento_dispositivo("impressora", {"status": "manual", "indice": 2})
                with patch("app.urlopen", return_value=RespostaJson({"status": "ok", "recebidos": 2})) as urlopen_mock:
                    retorno = app.sincronizar_eventos_dispositivo(config)
                carregada = app.carregar_configuracao()

        requisicao = urlopen_mock.call_args.args[0]
        corpo = json.loads(requisicao.data.decode("utf-8"))
        self.assertEqual(retorno["status"], "ok")
        self.assertEqual(retorno["enviados"], 2)
        self.assertEqual(carregada["diagnostico_eventos_sincronizados"], 2)
        self.assertTrue(requisicao.full_url.endswith("/pdv/api/terminal/device-events/"))
        self.assertEqual(requisicao.get_header("X-terminal-id"), "terminal-1")
        self.assertEqual(len(corpo["eventos"]), 2)

    def test_simulador_tef_aprova_pagamento_quando_terminal_tem_maquininha(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "terminal" / "config.json"
            with patch.dict(os.environ, {"SUPERMERCADO_PDV_CONFIG": str(caminho)}):
                ponte = app.PonteLocal({"tef": {"provedor": "STONE", "modo_integracao": "DESKTOP_BRIDGE"}})

                aprovado = ponte.processPayment({"tipo": "PIX", "valor": "25.50"})
                sem_tef = app.PonteLocal({"tef": {"provedor": "NAO_CONFIGURADO"}}).processPayment({"tipo": "PIX", "valor": "25.50"})
                diagnostico = app.listar_eventos_dispositivo()

        self.assertEqual(aprovado["status"], "ok")
        self.assertTrue(aprovado["aprovado"])
        self.assertTrue(aprovado["transacao_externa_id"].startswith("TEF-SIM-"))
        self.assertTrue(aprovado["nsu"])
        self.assertTrue(aprovado["codigo_autorizacao"])
        self.assertEqual(sem_tef["status"], "erro")
        self.assertIn("nao configurado", sem_tef["mensagem"])
        self.assertEqual(diagnostico["total"], 2)
        self.assertEqual(diagnostico["eventos"][0]["tipo"], "tef")
        self.assertEqual(diagnostico["eventos"][0]["payload"]["status"], "ok")
        self.assertEqual(diagnostico["eventos"][1]["payload"]["status"], "erro")

    def test_simulador_tef_aprova_estorno_e_registra_diagnostico(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "terminal" / "config.json"
            with patch.dict(os.environ, {"SUPERMERCADO_PDV_CONFIG": str(caminho)}):
                ponte = app.PonteLocal({"tef": {"provedor": "STONE", "modo_integracao": "DESKTOP_BRIDGE"}})

                aprovado = ponte.refundPayment(
                    {
                        "tipo": "PIX",
                        "valor": "25.50",
                        "transacao_externa_id": "TEF-SIM-ORIGINAL",
                    }
                )
                sem_tef = app.PonteLocal({"tef": {"provedor": "NAO_CONFIGURADO"}}).refundPayment(
                    {
                        "tipo": "PIX",
                        "valor": "25.50",
                        "transacao_externa_id": "TEF-SIM-ORIGINAL",
                    }
                )
                diagnostico = app.listar_eventos_dispositivo()

        self.assertEqual(aprovado["status"], "ok")
        self.assertTrue(aprovado["estornado"])
        self.assertTrue(aprovado["estorno_transacao_id"].startswith("TEF-SIM-REF-"))
        self.assertTrue(aprovado["codigo_autorizacao"])
        self.assertEqual(sem_tef["status"], "erro")
        self.assertIn("nao configurado", sem_tef["mensagem"])
        self.assertEqual(diagnostico["total"], 2)
        self.assertEqual(diagnostico["eventos"][0]["tipo"], "tef_estorno")
        self.assertEqual(diagnostico["eventos"][0]["payload"]["status"], "ok")
        self.assertEqual(diagnostico["eventos"][1]["payload"]["status"], "erro")

    def test_leitura_de_balanca_aceita_peso_simulado_para_homologacao(self):
        config = normalizar_configuracao_balanca(
            {"habilitada": True, "protocolo": "SERIAL", "porta": "COM3", "leitura_automatica": True}
        )

        with patch.dict(os.environ, {"SUPERMERCADO_PDV_PESO_SIMULADO": "1,250"}):
            leitura = ler_peso_balanca(config)

        self.assertEqual(leitura["status"], "ok")
        self.assertEqual(leitura["peso"], "1.250")
        self.assertEqual(leitura["unidade"], "KG")
        self.assertTrue(leitura["simulado"])

    def test_monta_cupom_operacional_sem_imagens_com_corte_e_gaveta(self):
        payload = {
            "venda": {
                "id": 27,
                "empresa": "Supermercado Modelo",
                "filial": "Loja Matriz",
                "data": "2026-07-08T10:00:00",
                "operador": "CAIXA01",
                "cliente": "Cliente avulso",
                "total_bruto": "12,50",
                "desconto": "0,50",
                "total_liquido": "12,00",
            },
            "itens": [{"sequencia": 1, "produto": "Cafe 500g", "quantidade": "1", "preco_unitario": "12,50", "total": "12,50"}],
            "pagamentos": [{"forma": "Dinheiro", "valor": "12,00"}],
            "impressao": {"mensagem_rodape": "Obrigado pela preferencia"},
            "gaveta": {"abrir": True},
        }

        texto = montar_texto_cupom(payload)
        dados = montar_cupom_escpos(payload)

        self.assertIn("Supermercado Modelo", texto)
        self.assertIn("Cafe 500g", texto)
        self.assertIn("TOTAL", texto)
        self.assertNotIn("logo_url", texto)
        self.assertTrue(dados.startswith(b"\x1b@"))
        self.assertIn(b"\x1bp\x00\x19\xfa", dados)
        self.assertTrue(dados.endswith(b"\x1dV\x42\x00"))

    def test_ponte_aciona_gaveta_e_registra_diagnostico_local(self):
        with tempfile.TemporaryDirectory() as pasta:
            config_path = Path(pasta) / "terminal" / "config.json"
            ponte = app.PonteLocal(
                {
                    "dispositivos": {
                        "gaveta": {
                            "contrato": "pdv_cash_drawer_v1",
                            "habilitada": True,
                            "impressora_padrao": "EPSON TM-T20",
                            "abrir_em_movimento_caixa": True,
                        }
                    }
                }
            )
            with patch.dict(os.environ, {"SUPERMERCADO_PDV_CONFIG": str(config_path)}):
                with patch("app.imprimir_raw_windows", return_value=len(montar_pulso_gaveta_escpos())) as imprimir_mock:
                    resposta = ponte.openCashDrawer({"motivo": "sangria"})
                eventos = app.listar_eventos_dispositivo()

        self.assertEqual(resposta["status"], "ok")
        self.assertTrue(resposta["acionada"])
        self.assertEqual(resposta["impressora"], "EPSON TM-T20")
        self.assertEqual(imprimir_mock.call_args.args[0], "EPSON TM-T20")
        self.assertEqual(imprimir_mock.call_args.args[1], montar_pulso_gaveta_escpos())
        self.assertEqual(eventos["eventos"][-1]["tipo"], "gaveta")
        self.assertEqual(eventos["eventos"][-1]["payload"]["status"], "ok")

    def test_ponte_gaveta_desabilitada_retorna_aviso_sem_bloquear(self):
        with tempfile.TemporaryDirectory() as pasta:
            config_path = Path(pasta) / "terminal" / "config.json"
            ponte = app.PonteLocal({"dispositivos": {"gaveta": {"habilitada": False}}})
            with patch.dict(os.environ, {"SUPERMERCADO_PDV_CONFIG": str(config_path)}):
                resposta = ponte.openCashDrawer({"motivo": "suprimento"})
                eventos = app.listar_eventos_dispositivo()

        self.assertEqual(resposta["status"], "manual")
        self.assertFalse(resposta["acionada"])
        self.assertIn("desabilitada", resposta["mensagem"])
        self.assertEqual(eventos["eventos"][-1]["tipo"], "gaveta")
        self.assertEqual(eventos["eventos"][-1]["payload"]["status"], "manual")

    def test_ponte_imprime_venda_no_spooler_com_limite_de_tres_vias(self):
        ponte = app.PonteLocal({})
        payload = {
            "venda": {"id": 10, "total_bruto": "1,00", "desconto": "0,00", "total_liquido": "1,00"},
            "impressao": {"impressora_padrao": "EPSON", "numero_vias": 8},
        }
        with patch("app.imprimir_raw_windows", return_value=120) as imprimir_mock:
            sucesso = ponte.imprimir_venda(payload)
        with patch("app.imprimir_raw_windows", return_value=80):
            sucesso_alias = ponte.printSale(payload)
        with patch("app.imprimir_raw_windows", side_effect=ErroImpressao("impressora offline")):
            falha = ponte.imprimir_venda(payload)

        self.assertTrue(sucesso["impresso"])
        self.assertTrue(sucesso_alias["impresso"])
        self.assertEqual(sucesso["vias"], 3)
        self.assertEqual(sucesso["bytes"], 360)
        self.assertEqual(imprimir_mock.call_count, 3)
        self.assertFalse(falha["impresso"])
        self.assertIn("offline", falha["mensagem"])

    def test_gera_etiquetas_zpl_com_medidas_dpi_codigo_e_copias(self):
        payload = {
            "linguagem": "ZPL",
            "dpi": 203,
            "densidade": 9,
            "velocidade": 4,
            "modelo": {"largura_mm": "100", "altura_mm": "50", "gap_vertical_mm": "2"},
            "itens": [{"nome": "Cafe Tradicional 500g", "codigo": "7891234567890", "preco": "17.27", "copias": 3}],
        }

        dados = montar_etiquetas_zpl(payload)

        self.assertIn(b"^XA", dados)
        self.assertIn(b"^PW799", dados)
        self.assertIn(b"^LL400", dados)
        self.assertIn(b"^BCN", dados)
        self.assertIn(b"7891234567890", dados)
        self.assertIn(b"R$ 17,27", dados)
        self.assertIn(b"^PQ3", dados)
        self.assertTrue(dados.rstrip().endswith(b"^XZ"))

    def test_gera_epl_ppla_e_pplb_com_comandos_nativos(self):
        payload = {
            "linguagem": "PPLB",
            "dpi": 203,
            "modelo": {"largura_mm": 80, "altura_mm": 40, "gap_vertical_mm": 3},
            "itens": [{"nome": "Leite Integral", "codigo": "7890001", "preco": "4,79", "copias": 2}],
        }

        dados = montar_etiquetas_epl(payload)
        dados_pplb = montar_etiquetas_nativas(payload)

        self.assertTrue(dados.startswith(b"N\nq"))
        self.assertIn(b'B20,', dados)
        self.assertIn(b'"7890001"', dados)
        self.assertIn(b"P2", dados)
        self.assertEqual(dados_pplb, dados)
        payload["linguagem"] = "PPLA"
        dados_ppla = montar_etiquetas_ppla(payload)
        dados_ppla_nativo = montar_etiquetas_nativas(payload)
        self.assertTrue(dados_ppla.startswith(b"\x02L"))
        self.assertIn(b"7890001", dados_ppla)
        self.assertIn(b"R$ 4,79", dados_ppla)
        self.assertIn(b"\nE\n", dados_ppla)
        self.assertEqual(dados_ppla_nativo, dados_ppla)

    def test_ponte_envia_etiqueta_nativa_ao_spooler(self):
        ponte = app.PonteLocal({})
        payload = {
            "impressora_padrao": "Zebra ZD421",
            "linguagem": "ZPL",
            "dpi": 203,
            "modelo": {"largura_mm": 100, "altura_mm": 50},
            "itens": [{"nome": "Arroz 5kg", "codigo": "789123", "preco": "23.90"}],
        }

        with patch("app.imprimir_raw_windows", return_value=320) as imprimir_mock:
            resposta = ponte.imprimir_etiquetas(payload)

        self.assertTrue(resposta["impresso"])
        self.assertEqual(resposta["linguagem"], "ZPL")
        self.assertEqual(resposta["bytes"], 320)
        self.assertEqual(imprimir_mock.call_args.args[0], "Zebra ZD421")
        self.assertTrue(imprimir_mock.call_args.args[1].startswith(b"^XA"))


if __name__ == "__main__":
    unittest.main()
