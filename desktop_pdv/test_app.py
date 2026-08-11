import base64
import hashlib
import io
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import app
from devices.printers import ErroDescobertaImpressoras, listar_impressoras_windows
from devices.labels import montar_etiquetas_epl, montar_etiquetas_nativas, montar_etiquetas_ppla, montar_etiquetas_zpl
from devices.printing import ErroImpressao, montar_cupom_escpos, montar_pulso_gaveta_escpos, montar_texto_comanda_entrega, montar_texto_cupom, montar_texto_danfe_nfce
from devices.scales import ErroBalanca, extrair_peso_resposta, ler_peso_balanca, normalizar_configuracao_balanca


class RespostaJson:
    def __init__(self, payload=None):
        self.payload = payload or {"status": "ok", "terminal": {"nome": "Caixa 01"}}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return json.dumps(self.payload).encode()

class RespostaBinaria:
    def __init__(self, conteudo):
        self.buffer = io.BytesIO(conteudo)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self, tamanho=-1):
        return self.buffer.read(tamanho)

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

    def test_executavel_instalado_ignora_config_ao_lado_do_app(self):
        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            (raiz / "config.json").write_text('{"servidor_base_url": "http://outro-computador"}', encoding="utf-8")
            app_data = raiz / "perfil"
            ambiente = {"LOCALAPPDATA": str(app_data), "DEIGO_PDV_CONFIG": "", "SUPERMERCADO_PDV_CONFIG": ""}
            with patch.dict(os.environ, ambiente), patch.object(app, "APP_DIR", raiz), patch.object(app.sys, "frozen", True, create=True):
                caminho = app.caminho_configuracao()

            self.assertEqual(caminho, app_data / "DeTecPDV" / "config.json")

    def test_migra_configuracao_legada_para_deigo_pdv(self):
        with tempfile.TemporaryDirectory() as pasta:
            local_app_data = Path(pasta)
            legado = local_app_data / "SupermercadoPDV" / "config.json"
            legado.parent.mkdir(parents=True)
            legado.write_text('{"terminal_id": "caixa-legado"}', encoding="utf-8")
            ambiente = {"LOCALAPPDATA": str(local_app_data), "DEIGO_PDV_CONFIG": "", "SUPERMERCADO_PDV_CONFIG": ""}

            with patch.dict(os.environ, ambiente):
                caminho = app.caminho_configuracao()

            self.assertEqual(caminho, local_app_data / "DeTecPDV" / "config.json")
            self.assertTrue(caminho.exists())
            self.assertEqual(json.loads(caminho.read_text(encoding="utf-8"))["terminal_id"], "caixa-legado")
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

    def test_bootstrap_offline_recusa_cache_expirado(self):
        config = {
            "servidor_base_url": "http://servidor.local",
            "terminal_id": "terminal-1",
            "terminal_chave": "segredo",
            "offline_cache_max_hours": 24,
        }
        payload = {
            "status": "ok",
            "terminal": {"nome": "Caixa 01", "permite_modo_offline": True},
            "recursos": {"modo_offline_permitido": True},
            "cache_salvo_em": (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat(),
        }
        with tempfile.TemporaryDirectory() as pasta:
            config_path = Path(pasta) / "terminal" / "config.json"
            cache_path = config_path.parent / "bootstrap_cache.json"
            cache_path.parent.mkdir(parents=True)
            cache_path.write_text(json.dumps(payload), encoding="utf-8")
            with patch.dict(os.environ, {"SUPERMERCADO_PDV_CONFIG": str(config_path)}):
                with patch("app.validar_terminal", side_effect=app.ServidorPdvIndisponivel("sem rede")):
                    with self.assertRaisesRegex(RuntimeError, "bootstrap offline autorizado expirou"):
                        app.obter_bootstrap_operacional(config)
                diagnostico = app.listar_eventos_dispositivo()

        self.assertEqual(diagnostico["eventos"][-1]["payload"]["status"], "cache_expirado")

    def test_pagina_de_contingencia_nao_expoe_chave_e_oferece_reconexao_por_teclado(self):
        pagina = app.montar_pagina_contingencia(
            {
                "terminal": {"nome": "Caixa <01>"},
                "cache_salvo_em": "2026-07-27T13:00:00+00:00",
                "mensagem_conexao": "Servidor sem rede",
                "terminal_chave": "segredo-nao-pode-aparecer",
            }
        )

        self.assertIn("PDV temporariamente indisponivel", pagina)
        self.assertIn("Caixa &lt;01&gt;", pagina)
        self.assertIn("F5", pagina)
        self.assertIn("reconnect", pagina)
        self.assertIn("Sair do aplicativo", pagina)
        self.assertIn("Ctrl+F5", pagina)
        self.assertIn("event.key.toLowerCase() === 'q'", pagina)
        self.assertIn("closeApplication", pagina)
        self.assertIn("vendas, pagamentos e alteracoes de estoque permanecem bloqueados", pagina)
        self.assertNotIn("`n", pagina)
        self.assertNotIn("segredo-nao-pode-aparecer", pagina)

    def test_ponte_reconecta_somente_apos_servidor_validar_terminal(self):
        config = {
            "servidor_base_url": "http://servidor.local",
            "terminal_id": "terminal-1",
            "terminal_chave": "segredo",
        }
        offline = {"status_conexao": "offline", "terminal": {"nome": "Caixa 01"}}
        online = {"status": "ok", "terminal": {"nome": "Caixa 01"}}
        with tempfile.TemporaryDirectory() as pasta:
            config_path = Path(pasta) / "terminal" / "config.json"
            with patch.dict(os.environ, {"SUPERMERCADO_PDV_CONFIG": str(config_path)}):
                ponte = app.PonteLocal(offline, config)
                with patch("app.validar_terminal", return_value=online), patch("app.sincronizar_eventos_dispositivo", return_value={"status": "ok"}):
                    conectado = ponte.reconnect()
                with patch("app.validar_terminal", side_effect=app.TerminalRecusado("licenca bloqueada")):
                    bloqueado = app.PonteLocal(offline, config).reconnect()

        self.assertEqual(conectado["status"], "ok")
        self.assertEqual(conectado["url"], "http://servidor.local/pdv/")
        self.assertEqual(ponte.status()["status_conexao"], "online")
        self.assertEqual(bloqueado["status"], "bloqueado")
        self.assertIn("licenca bloqueada", bloqueado["mensagem"])
    def test_executar_abre_html_local_em_vez_da_url_quando_servidor_esta_offline(self):
        config = {
            "servidor_base_url": "http://servidor.local",
            "terminal_id": "terminal-1",
            "terminal_chave": "segredo",
            "tela_cheia": True,
        }
        bootstrap = {
            "status": "ok",
            "status_conexao": "offline",
            "terminal": {"nome": "Caixa 01", "permite_modo_offline": True},
            "cache_salvo_em": datetime.now(timezone.utc).isoformat(),
        }
        janela = MagicMock()
        webview = MagicMock()
        webview.create_window.return_value = janela
        with patch.dict("sys.modules", {"webview": webview}):
            with patch("app.carregar_configuracao", return_value=config), patch("app.obter_bootstrap_operacional", return_value=bootstrap):
                with patch("app.sincronizar_eventos_dispositivo", return_value={"status": "ok"}), patch("app.avisar_atualizacao"):
                    app.executar()

        kwargs = webview.create_window.call_args.kwargs
        self.assertIn("PDV temporariamente indisponivel", kwargs["html"])
        self.assertNotIn("url", kwargs)
        self.assertIsInstance(kwargs["js_api"], app.PonteLocal)
        webview.start.assert_called_once_with(private_mode=False)

    def test_executar_reabre_ativacao_quando_credencial_do_terminal_e_recusada(self):
        config_invalida = {
            "servidor_base_url": "http://servidor-antigo.local",
            "terminal_id": "terminal-antigo",
            "terminal_chave": "chave-invalida",
        }
        config_nova = {
            "servidor_base_url": "http://servidor-novo.local",
            "terminal_id": "terminal-novo",
            "terminal_chave": "chave-valida",
        }
        with patch("app.carregar_configuracao", return_value=config_invalida):
            with patch(
                "app._executar_interface_pdv",
                side_effect=[app.TerminalRecusado("credencial invalida"), False],
            ) as executar_interface:
                with patch("app.ativar_terminal", return_value=config_nova) as ativar:
                    app.executar()

        ativar.assert_called_once_with(config_invalida)
        self.assertEqual(executar_interface.call_args_list[1].args[0], config_nova)

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

    def test_prepara_atualizacao_autorizada_e_confere_sha256(self):
        conteudo = b"pacote-atualizacao-pdv"
        sha256 = hashlib.sha256(conteudo).hexdigest()
        bootstrap = {
            "aplicativo": {
                "versao_vigente": "0.4.0",
                "atualizacao_disponivel": True,
                "pacote": {
                    "disponivel": True,
                    "nome": "DeTecPDV.exe",
                    "sha256": sha256,
                    "url": "http://servidor.local/pdv/api/terminal/update/",
                },
            }
        }
        config = {"terminal_id": "terminal-1", "terminal_chave": "segredo"}
        with tempfile.TemporaryDirectory() as pasta:
            config_path = Path(pasta) / "terminal" / "config.json"
            with patch.dict(os.environ, {"SUPERMERCADO_PDV_CONFIG": str(config_path)}):
                with patch("app.urlopen", return_value=RespostaBinaria(conteudo)) as urlopen_mock:
                    resultado = app.preparar_atualizacao(config, app.verificar_versao(bootstrap))
                destino = Path(resultado["arquivo"])
                recebido = destino.read_bytes()

        requisicao = urlopen_mock.call_args.args[0]
        self.assertEqual(recebido, conteudo)
        self.assertEqual(resultado["sha256"], sha256)
        self.assertEqual(requisicao.get_header("X-terminal-id"), "terminal-1")
        self.assertEqual(requisicao.get_header("X-terminal-key"), "segredo")

    def test_descarta_atualizacao_com_sha256_invalido(self):
        bootstrap = {
            "aplicativo": {
                "versao_vigente": "0.4.0",
                "atualizacao_disponivel": True,
                "pacote": {
                    "disponivel": True,
                    "nome": "DeTecPDV.exe",
                    "sha256": "0" * 64,
                    "url": "http://servidor.local/pdv/api/terminal/update/",
                },
            }
        }
        config = {"terminal_id": "terminal-1", "terminal_chave": "segredo"}
        with tempfile.TemporaryDirectory() as pasta:
            config_path = Path(pasta) / "terminal" / "config.json"
            with patch.dict(os.environ, {"SUPERMERCADO_PDV_CONFIG": str(config_path)}):
                with patch("app.urlopen", return_value=RespostaBinaria(b"pacote-adulterado")):
                    with self.assertRaisesRegex(RuntimeError, "SHA-256"):
                        app.preparar_atualizacao(config, app.verificar_versao(bootstrap))
                self.assertFalse((config_path.parent / "updates" / "DeTecPDV.exe").exists())
                self.assertFalse((config_path.parent / "updates" / "DeTecPDV.exe.part").exists())
    def test_atualizacao_obrigatoria_preparada_bloqueia_abertura_do_pdv(self):
        messagebox = MagicMock()
        messagebox.askyesno.return_value = True
        modulo_tkinter = MagicMock(messagebox=messagebox)
        situacao = {
            "instalada": "0.1.0",
            "vigente": "0.4.0",
            "atualizacao_disponivel": True,
            "atualizacao_obrigatoria": True,
            "pacote_disponivel": True,
        }
        with patch.dict("sys.modules", {"tkinter": modulo_tkinter}):
            with patch("app.preparar_atualizacao", return_value={"arquivo": "C:/update/DeTecPDV.exe"}):
                with self.assertRaisesRegex(RuntimeError, "instale o pacote"):
                    app.avisar_atualizacao(situacao, {"terminal_id": "1"})

        messagebox.showinfo.assert_called_once()
    def test_ponte_le_credencial_pcsc_sem_registrar_uid(self):
        ponte = app.PonteLocal({"terminal": {"nome": "Caixa 01"}}, {})
        with patch("app.ler_uid_pcsc", return_value="04A1B2C3") as leitor:
            resultado = ponte.readSupervisorCredential("ACR")
        self.assertEqual(resultado["status"], "ok")
        self.assertEqual(resultado["credencial"], "04A1B2C3")
        self.assertEqual(resultado["origem"], "PCSC")
        leitor.assert_called_once_with("ACR")

    def test_ponte_orienta_fallback_quando_pcsc_falha(self):
        ponte = app.PonteLocal({"terminal": {"nome": "Caixa 01"}}, {})
        with patch("app.ler_uid_pcsc", side_effect=app.ErroLeitorCartao("Sem cartao")):
            resultado = ponte.readSupervisorCredential()
        self.assertEqual(resultado["status"], "erro")
        self.assertNotIn("credencial", resultado)
        self.assertIn("modo teclado", resultado["fallback"])

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
        self.assertIn("COM3", leitura["mensagem"])
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

    def test_sincronizacao_em_volume_envia_do_evento_mais_antigo_sem_saltar_linhas(self):
        with tempfile.TemporaryDirectory() as pasta:
            config_path = Path(pasta) / "terminal" / "config.json"
            config = {
                "servidor_base_url": "http://servidor.local",
                "terminal_id": "terminal-volume",
                "terminal_chave": "segredo",
            }
            with patch.dict(os.environ, {"SUPERMERCADO_PDV_CONFIG": str(config_path)}):
                app.salvar_configuracao(config)
                for indice in range(250):
                    app.registrar_evento_dispositivo("teste", {"indice": indice})
                respostas = [
                    RespostaJson({"status": "ok", "recebidos": 100, "processados": 100}),
                    RespostaJson({"status": "ok", "recebidos": 100, "processados": 100}),
                    RespostaJson({"status": "ok", "recebidos": 50, "processados": 50}),
                ]
                with patch("app.urlopen", side_effect=respostas) as urlopen_mock:
                    primeira = app.sincronizar_eventos_dispositivo(config)
                    segunda = app.sincronizar_eventos_dispositivo(config)
                    terceira = app.sincronizar_eventos_dispositivo(config)
                carregada = app.carregar_configuracao()

        lotes = [
            json.loads(chamada.args[0].data.decode("utf-8"))["eventos"]
            for chamada in urlopen_mock.call_args_list
        ]
        self.assertEqual([evento["payload"]["indice"] for evento in lotes[0]], list(range(100)))
        self.assertEqual([evento["payload"]["indice"] for evento in lotes[1]], list(range(100, 200)))
        self.assertEqual([evento["payload"]["indice"] for evento in lotes[2]], list(range(200, 250)))
        self.assertEqual(primeira["pendentes"], 150)
        self.assertEqual(segunda["pendentes"], 50)
        self.assertEqual(terceira["pendentes"], 0)
        self.assertEqual(carregada["diagnostico_eventos_sincronizados"], 250)

    def test_sincronizacao_nao_avanca_cursor_sem_confirmacao_integral_do_lote(self):
        with tempfile.TemporaryDirectory() as pasta:
            config_path = Path(pasta) / "terminal" / "config.json"
            config = {
                "servidor_base_url": "http://servidor.local",
                "terminal_id": "terminal-parcial",
                "terminal_chave": "segredo",
            }
            with patch.dict(os.environ, {"SUPERMERCADO_PDV_CONFIG": str(config_path)}):
                app.salvar_configuracao(config)
                for indice in range(3):
                    app.registrar_evento_dispositivo("teste", {"indice": indice})
                with patch(
                    "app.urlopen",
                    return_value=RespostaJson({"status": "ok", "recebidos": 2, "processados": 2}),
                ):
                    retorno = app.sincronizar_eventos_dispositivo(config)
                carregada = app.carregar_configuracao()

        self.assertEqual(retorno["status"], "erro")
        self.assertEqual(retorno["enviados"], 0)
        self.assertEqual(carregada.get("diagnostico_eventos_sincronizados", 0), 0)


    def test_intervalo_da_sincronizacao_periodica_e_limitado(self):
        self.assertEqual(app.intervalo_sincronizacao_eventos({}), 60)
        self.assertEqual(app.intervalo_sincronizacao_eventos({"diagnostico_sync_interval_seconds": 1}), 15)
        self.assertEqual(app.intervalo_sincronizacao_eventos({"diagnostico_sync_interval_seconds": 99999}), 3600)
        self.assertEqual(app.intervalo_sincronizacao_eventos({"diagnostico_sync_interval_seconds": "invalido"}), 60)

    def test_sincronizacao_periodica_para_sem_nova_tentativa_ao_encerrar(self):
        parar = MagicMock()
        parar.wait.side_effect = [False, False, True]

        with patch("app.sincronizar_eventos_dispositivo", return_value={"status": "ok"}) as sincronizar:
            app.sincronizar_eventos_periodicamente(
                {"diagnostico_sync_interval_seconds": 15},
                parar,
            )

        self.assertEqual(parar.wait.call_args_list, [unittest.mock.call(15)] * 3)
        self.assertEqual(sincronizar.call_count, 2)

    def test_status_da_ponte_expoe_sincronizacao_periodica(self):
        status = app.PonteLocal({}, {"diagnostico_sync_interval_seconds": 30}).status()

        self.assertEqual(status["sincronizacao_eventos"]["contrato"], "pdv_device_event_queue_v1")
        self.assertTrue(status["sincronizacao_eventos"]["periodica"])
        self.assertEqual(status["sincronizacao_eventos"]["intervalo_segundos"], 30)

    def test_ponte_solicita_encerramento_da_janela(self):
        janela = MagicMock()
        ponte = app.PonteLocal({})
        ponte.vincular_janela(janela)

        with patch("app.threading.Timer") as timer:
            resultado = ponte.closeApplication()

        self.assertEqual(resultado["status"], "ok")
        timer.assert_called_once_with(0.15, janela.destroy)
        timer.return_value.start.assert_called_once_with()


    def test_simulador_tef_aprova_pagamento_quando_terminal_tem_maquininha(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "terminal" / "config.json"
            with patch.dict(os.environ, {"SUPERMERCADO_PDV_CONFIG": str(caminho)}):
                ponte = app.PonteLocal({"tef": {"provedor": "STONE", "modo_integracao": "DESKTOP_BRIDGE", "simulador_permitido": True}})

                pendente = ponte.processPayment({"tipo": "PIX", "valor": "25.50", "idempotency_key": "pix-25-50"})
                primeira_consulta = ponte.checkPayment({"transacao_externa_id": pendente["transacao_externa_id"]})
                aprovado = ponte.checkPayment({"transacao_externa_id": pendente["transacao_externa_id"]})
                sem_tef = app.PonteLocal({"tef": {"provedor": "NAO_CONFIGURADO"}}).processPayment({"tipo": "PIX", "valor": "25.50"})
                diagnostico = app.listar_eventos_dispositivo()

        self.assertEqual(pendente["status"], "pending")
        self.assertFalse(pendente["aprovado"])
        self.assertEqual(primeira_consulta["status"], "pending")
        self.assertTrue(pendente["pix_qr_code_image"].startswith("data:image/png;base64,"))
        png = base64.b64decode(pendente["pix_qr_code_image"].split(",", 1)[1])
        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertTrue(pendente["pix_simulado"])
        self.assertEqual(aprovado["status"], "ok")
        self.assertTrue(aprovado["aprovado"])
        self.assertTrue(aprovado["simulado"])
        self.assertTrue(aprovado["transacao_externa_id"].startswith("TEF-SIM-"))
        self.assertTrue(aprovado["nsu"])
        self.assertTrue(aprovado["codigo_autorizacao"])
        self.assertEqual(sem_tef["status"], "erro")
        self.assertIn("nao configurado", sem_tef["mensagem"])
        self.assertEqual(diagnostico["total"], 3)
        self.assertEqual(diagnostico["eventos"][0]["tipo"], "tef")
        self.assertEqual(diagnostico["eventos"][0]["payload"]["status"], "pending")
        self.assertEqual(diagnostico["eventos"][1]["payload"]["status"], "ok")
        self.assertEqual(diagnostico["eventos"][2]["payload"]["status"], "erro")

    def test_tef_processa_vale_alimentacao_como_voucher_proprio(self):
        ponte = app.PonteLocal(
            {
                "tef": {
                    "provedor": "STONE",
                    "modo_integracao": "DESKTOP_BRIDGE",
                    "simulador_permitido": True,
                    "tipos_pagamento": ["VALE_ALIMENTACAO", "VALE_REFEICAO"],
                }
            }
        )

        resultado = ponte.processPayment({"tipo": "VALE_ALIMENTACAO", "valor": "32.90"})

        self.assertEqual(resultado["status"], "ok")
        self.assertTrue(resultado["aprovado"])
        self.assertEqual(resultado["tipo"], "VALE_ALIMENTACAO")
        self.assertTrue(resultado["nsu"])
        self.assertTrue(resultado["codigo_autorizacao"])
    def test_tef_valida_valor_e_modalidade_antes_de_processar(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "terminal" / "config.json"
            with patch.dict(os.environ, {"SUPERMERCADO_PDV_CONFIG": str(caminho)}):
                ponte = app.PonteLocal(
                    {
                        "tef": {
                            "provedor": "STONE",
                            "modo_integracao": "DESKTOP_BRIDGE", "simulador_permitido": True,
                            "tipos_pagamento": ["DEBITO", "PIX"],
                        }
                    }
                )

                decimal_brasileiro = ponte.processPayment({"tipo": "PIX", "valor": "25,50"})
                modalidade_bloqueada = ponte.processPayment({"tipo": "CREDITO", "valor": "25.50"})
                valor_negativo = ponte.processPayment({"tipo": "PIX", "valor": "-1"})
                fracao_centavo = ponte.processPayment({"tipo": "PIX", "valor": "1.001"})

        self.assertEqual(decimal_brasileiro["status"], "pending")
        self.assertEqual(decimal_brasileiro["valor"], "25.50")
        self.assertFalse(modalidade_bloqueada["aprovado"])
        self.assertIn("nao habilitado", modalidade_bloqueada["mensagem"])
        self.assertFalse(valor_negativo["aprovado"])
        self.assertIn("maior que zero", valor_negativo["mensagem"])
        self.assertFalse(fracao_centavo["aprovado"])
        self.assertIn("fracao menor", fracao_centavo["mensagem"])

    def test_tef_reutiliza_pagamento_com_mesma_chave_sem_nova_autorizacao(self):
        ponte = app.PonteLocal({"tef": {"provedor": "STONE", "modo_integracao": "DESKTOP_BRIDGE", "simulador_permitido": True}})
        payload = {"tipo": "PIX", "valor": "25.50", "idempotency_key": "venda-local-1-pix"}

        primeira = ponte.processPayment(payload)
        repetida_pendente = ponte.processPayment(payload)
        ponte.checkPayment({"transacao_externa_id": primeira["transacao_externa_id"]})
        confirmado = ponte.checkPayment({"transacao_externa_id": primeira["transacao_externa_id"]})
        repetida_confirmada = ponte.processPayment(payload)
        conflito = ponte.processPayment({**payload, "valor": "30.00"})

        self.assertEqual(repetida_pendente["transacao_externa_id"], primeira["transacao_externa_id"])
        self.assertTrue(repetida_pendente["reutilizado"])
        self.assertEqual(confirmado["status"], "ok")
        self.assertTrue(confirmado["aprovado"])
        self.assertEqual(repetida_confirmada["transacao_externa_id"], primeira["transacao_externa_id"])
        self.assertTrue(repetida_confirmada["reutilizado"])
        self.assertEqual(conflito["status"], "erro")
        self.assertIn("dados diferentes", conflito["mensagem"])

    def test_simulador_tef_aprova_estorno_e_registra_diagnostico(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "terminal" / "config.json"
            with patch.dict(os.environ, {"SUPERMERCADO_PDV_CONFIG": str(caminho)}):
                ponte = app.PonteLocal({"tef": {"provedor": "STONE", "modo_integracao": "DESKTOP_BRIDGE", "simulador_permitido": True}})

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

    def test_tef_valida_valor_do_estorno_antes_de_processar(self):
        ponte = app.PonteLocal({"tef": {"provedor": "STONE", "modo_integracao": "DESKTOP_BRIDGE", "simulador_permitido": True}})

        sem_transacao = ponte.refundPayment({"tipo": "PIX", "valor": "10.00"})
        valor_zero = ponte.refundPayment(
            {"tipo": "PIX", "valor": "0", "transacao_externa_id": "TEF-SIM-ORIGINAL"}
        )

        self.assertFalse(sem_transacao["estornado"])
        self.assertIn("transacao original", sem_transacao["mensagem"])
        self.assertFalse(valor_zero["estornado"])
        self.assertIn("maior que zero", valor_zero["mensagem"])

    def test_tef_reutiliza_estorno_com_mesma_chave(self):
        ponte = app.PonteLocal({"tef": {"provedor": "STONE", "modo_integracao": "DESKTOP_BRIDGE", "simulador_permitido": True}})
        payload = {
            "tipo": "PIX",
            "valor": "10.00",
            "transacao_externa_id": "TEF-SIM-ORIGINAL",
            "idempotency_key": "refund:TEF-SIM-ORIGINAL:10.00",
        }

        primeiro = ponte.refundPayment(payload)
        repetido = ponte.refundPayment(payload)

        self.assertEqual(repetido["estorno_transacao_id"], primeiro["estorno_transacao_id"])
        self.assertTrue(repetido["reutilizado"])

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

    def test_parser_generico_de_balanca_aceita_decimal_e_conversao_de_gramas(self):
        self.assertEqual(extrair_peso_resposta(b"ST,GS, 1.250 kg\r\n"), "1.250")
        self.assertEqual(extrair_peso_resposta("PESO: 001250", fator_conversao="0.001"), "1.250")
        with self.assertRaisesRegex(ErroBalanca, "peso instavel"):
            extrair_peso_resposta("US,GS, 1.250 kg")

    def test_driver_serial_generico_le_resposta_sem_simulador(self):
        conexao = MagicMock()
        conexao.read_until.return_value = b"ST,GS, 2.375 kg\r\n"
        config = {
            "habilitada": True,
            "leitura_automatica": True,
            "protocolo": "SERIAL",
            "porta": "COM3",
        }

        with patch("devices.scales._abrir_serial", return_value=conexao):
            resultado = ler_peso_balanca(config)

        self.assertEqual(resultado["status"], "ok")
        self.assertEqual(resultado["peso"], "2.375")
        self.assertFalse(resultado["simulado"])
        conexao.read_until.assert_called_once_with(b"\r\n", 256)
        conexao.close.assert_called_once()

    def test_driver_tcp_generico_valida_endereco_e_le_resposta(self):
        conexao = MagicMock()
        conexao.recv.return_value = b"0.875 kg\r\n"
        contexto = MagicMock()
        contexto.__enter__.return_value = conexao
        config = {
            "habilitada": True,
            "leitura_automatica": True,
            "protocolo": "TCP_IP",
            "porta": "192.168.1.50:4001",
            "timeout_ms": 1500,
        }

        with patch("devices.scales.socket.create_connection", return_value=contexto) as conectar:
            resultado = ler_peso_balanca(config)
        endereco_invalido = ler_peso_balanca({**config, "porta": "sem-porta"})

        self.assertEqual(resultado["peso"], "0.875")
        self.assertFalse(resultado["simulado"])
        conectar.assert_called_once_with(("192.168.1.50", 4001), timeout=1.5)
        self.assertEqual(endereco_invalido["status"], "erro")
        self.assertIn("endereco:porta", endereco_invalido["mensagem"])

    def test_driver_arquivo_texto_le_peso_com_limite_local(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "peso.txt"
            caminho.write_text("PESO=3,420 KG", encoding="ascii")
            resultado = ler_peso_balanca(
                {
                    "habilitada": True,
                    "leitura_automatica": True,
                    "protocolo": "ARQUIVO_TXT",
                    "porta": str(caminho),
                }
            )

        self.assertEqual(resultado["status"], "ok")
        self.assertEqual(resultado["peso"], "3.420")
        self.assertFalse(resultado["simulado"])

    def test_monta_cupom_operacional_sem_imagens_com_corte_e_gaveta(self):
        payload = {
            "venda": {
                "id": 27,
                "empresa": "Supermercado Modelo",
                "filial": "Loja Matriz",
                "cnpj": "00.000.000/0001-00",
                "endereco": "Rua Exemplo, 123 - Centro",
                "data": "2026-07-08T10:00:00",
                "operador": "CAIXA01",
                "cliente": "Cliente avulso",
                "caixa": 1,
                "quantidade_total": "2",
                "total_bruto": "12,50",
                "desconto": "0,50",
                "total_liquido": "12,00",
                "total_pago": "20,00",
                "troco": "8,00",
            },
            "itens": [{"sequencia": 1, "produto": "MA\u00c7\u00c3", "codigo_barras": "123", "quantidade": "2", "preco_unitario": "6,25", "total": "12,50"}],
            "pagamentos": [{"forma": "Dinheiro", "valor": "12,00"}],
            "impressao": {"mensagem_rodape": "Obrigado pela preferencia"},
            "gaveta": {"abrir": True},
        }

        texto = montar_texto_cupom(payload)
        dados = montar_cupom_escpos(payload)

        self.assertIn("Supermercado Modelo", texto)
        self.assertIn("MA\u00c7\u00c3", texto)
        self.assertIn("CUPOM NAO FISCAL", texto)
        self.assertIn("R$ 6,25", texto)
        self.assertIn("TROCO:", texto)
        self.assertIn("R$ 8,00", texto)
        self.assertIn("NAO E DOCUMENTO FISCAL", texto)
        self.assertNotIn("logo_url", texto)
        self.assertTrue(dados.startswith(b"\x1b@"))
        self.assertIn("MA\u00c7\u00c3".encode("cp850"), dados)
        self.assertIn(b"\x1bp\x00\x19\xfa", dados)
        self.assertTrue(dados.endswith(b"\x1dV\x42\x00"))

    def test_monta_comanda_entrega_com_endereco_itens_e_pagamento(self):
        payload = {
            "tipo": "comanda_entrega",
            "pedido": {
                "id": 31,
                "empresa": "Supermercado Modelo",
                "filial": "Matriz",
                "criado_em": "2026-07-30T14:00:00",
                "status": "Pronto",
                "cliente": "Cliente Entrega",
                "telefone": "(62) 99999-0000",
                "endereco": "Rua 18, QD 81, LT 12",
                "bairro": "Santos Dumont",
                "observacoes": "Tocar o interfone",
                "total": "25,90",
                "pagamento": "Pago",
                "forma_pagamento": "PIX",
            },
            "itens": [{"produto": "ARROZ 5KG", "quantidade": "2", "unidade": "UN"}],
            "impressao": {"modelo_papel": "80MM"},
            "gaveta": {"abrir": False},
        }

        texto = montar_texto_comanda_entrega(payload)
        dados = montar_cupom_escpos(payload)

        self.assertIn("COMANDA DE ENTREGA #31", texto)
        self.assertIn("Cliente Entrega", texto)
        self.assertIn("Rua 18, QD 81, LT 12", texto)
        self.assertIn("ARROZ 5KG", texto)
        self.assertIn("PAGAMENTO:", texto)
        self.assertIn("Pago", texto)
        self.assertNotIn("NAO E DOCUMENTO FISCAL", texto)
        self.assertTrue(dados.startswith(b"\x1b@"))
        self.assertTrue(dados.endswith(b"\x1dV\x42\x00"))
    def test_monta_danfe_nfce_com_qrcode_nativo_e_sem_marca_nao_fiscal(self):
        chave = "35260712345678000190650010000001001123456780"
        qrcode_url = f"https://nfce.example.com/qrcode?p={chave}|3|2"
        payload = {
            "tipo": "danfe_nfce",
            "venda": {
                "id": 30,
                "empresa": "Supermercado Modelo",
                "filial": "Matriz",
                "cnpj": "12.345.678/0001-90",
                "data": "2026-07-29T10:00:00",
                "quantidade_total": "1",
                "total_bruto": "25,90",
                "desconto": "0,00",
                "total_liquido": "25,90",
            },
            "itens": [{"sequencia": 1, "produto": "ARROZ 5KG", "quantidade": "1", "preco_unitario": "25,90", "total": "25,90"}],
            "pagamentos": [{"forma": "PIX", "valor": "25,90"}],
            "fiscal": {
                "status": "EMITIDO",
                "serie": 1,
                "numero": 100,
                "chave_acesso": chave,
                "protocolo": "135260000000001",
                "qrcode_url": qrcode_url,
                "url_consulta": "https://nfce.example.com/consulta",
                "emitido_em": "2026-07-29T10:00:00",
            },
            "impressao": {"modelo_papel": "80MM"},
        }

        texto = montar_texto_danfe_nfce(payload)
        dados = montar_cupom_escpos(payload)

        self.assertIn("DOCUMENTO AUXILIAR DA NOTA FISCAL", texto)
        self.assertIn("R$ 25,90", texto)
        self.assertIn("CHAVE DE ACESSO", texto)
        self.assertNotIn("NAO E DOCUMENTO FISCAL", texto)
        self.assertIn(qrcode_url.encode("utf-8"), dados)
        self.assertIn(b"\x1d(k", dados)
        self.assertTrue(dados.endswith(b"\x1dV\x42\x00"))
        payload["fiscal"]["qrcode_url"] = ""
        with self.assertRaisesRegex(ErroImpressao, "QR Code oficial"):
            montar_cupom_escpos(payload)

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
            "contrato": "label_print_v1",
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
            "contrato": "label_print_v1",
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

    def test_ponte_envia_etiqueta_nativa_ao_spooler_e_grava_diagnostico(self):
        ponte = app.PonteLocal({})
        payload = {
            "contrato": "label_print_v1",
            "impressora_padrao": "Zebra ZD421",
            "linguagem": "ZPL",
            "dpi": 203,
            "modelo": {"largura_mm": 100, "altura_mm": 50},
            "itens": [{"nome": "Arroz 5kg", "codigo": "789123", "preco": "23.90", "copias": 2}],
        }

        with tempfile.TemporaryDirectory() as pasta:
            config_path = Path(pasta) / "terminal" / "config.json"
            with patch.dict(os.environ, {"SUPERMERCADO_PDV_CONFIG": str(config_path)}):
                with patch("app.imprimir_raw_windows", return_value=320) as imprimir_mock:
                    resposta = ponte.imprimir_etiquetas(payload)
                falha = ponte.imprimir_etiquetas({**payload, "contrato": "desconhecido"})
                diagnostico = app.listar_eventos_dispositivo()

        self.assertTrue(resposta["impresso"])
        self.assertEqual(resposta["linguagem"], "ZPL")
        self.assertEqual(resposta["bytes"], 320)
        self.assertEqual(resposta["itens"], 1)
        self.assertEqual(resposta["copias"], 2)
        self.assertEqual(imprimir_mock.call_args.args[0], "Zebra ZD421")
        self.assertTrue(imprimir_mock.call_args.args[1].startswith(b"^XA"))
        self.assertFalse(falha["impresso"])
        self.assertIn("Contrato de etiquetas", falha["mensagem"])
        self.assertEqual(diagnostico["eventos"][0]["tipo"], "etiquetas")
        self.assertEqual(diagnostico["eventos"][0]["payload"]["status"], "ok")
        self.assertEqual(diagnostico["eventos"][0]["payload"]["copias"], 2)
        self.assertEqual(diagnostico["eventos"][1]["payload"]["status"], "erro")

    def test_etiquetas_rejeitam_codigo_ausente_e_lotes_excessivos(self):
        base = {
            "contrato": "label_print_v1",
            "linguagem": "ZPL",
            "dpi": 203,
            "modelo": {"largura_mm": 100, "altura_mm": 50},
        }
        with self.assertRaisesRegex(ErroImpressao, "codigo de barras ou SKU"):
            montar_etiquetas_nativas({**base, "itens": [{"nome": "Sem codigo", "preco": "1.00"}]})
        with self.assertRaisesRegex(ErroImpressao, "entre 1 e 100 copias"):
            montar_etiquetas_nativas(
                {**base, "itens": [{"nome": "Arroz", "codigo": "789123", "preco": "1.00", "copias": 101}]}
            )
        with self.assertRaisesRegex(ErroImpressao, "2.000 etiquetas"):
            montar_etiquetas_nativas(
                {
                    **base,
                    "itens": [
                        {"nome": f"Produto {indice}", "codigo": f"SKU{indice}", "preco": "1.00", "copias": 100}
                        for indice in range(21)
                    ],
                }
            )

    def test_pre_homologacao_padrao_e_nao_invasiva_e_grava_evidencia(self):
        bootstrap = {
            "dispositivos": {
                "balanca": {
                    "habilitada": True,
                    "leitura_automatica": True,
                    "protocolo": "SERIAL",
                    "porta": "COM3",
                },
                "gaveta": {
                    "habilitada": True,
                    "impressora_padrao": "EPSON TM-T20",
                },
            },
            "tef": {"provedor": "STONE", "modo_integracao": "DESKTOP_BRIDGE", "simulador_permitido": True},
        }
        with tempfile.TemporaryDirectory() as pasta:
            config_path = Path(pasta) / "terminal" / "config.json"
            with patch.dict(os.environ, {"SUPERMERCADO_PDV_CONFIG": str(config_path)}):
                with patch(
                    "app.listar_impressoras_windows",
                    return_value=[{"nome": "EPSON TM-T20", "padrao": True, "offline": False}],
                ):
                    with patch("app.imprimir_raw_windows") as imprimir_mock:
                        resultado = app.PonteLocal(bootstrap).runDeviceDiagnostics()
                eventos = app.listar_eventos_dispositivo()["eventos"]

        self.assertEqual(resultado["contrato"], "pdv_device_homologation_v1")
        self.assertEqual(resultado["status"], "atencao")
        self.assertFalse(resultado["homologacao_fisica_concluida"])
        self.assertEqual([item["codigo"] for item in resultado["verificacoes"]], ["impressora", "balanca", "gaveta", "tef"])
        self.assertFalse(imprimir_mock.called)
        self.assertEqual(eventos[-1]["tipo"], "homologacao_dispositivos")
        self.assertEqual(eventos[-1]["payload"]["contrato"], "pdv_device_homologation_v1")

    def test_pre_homologacao_executa_acoes_fisicas_somente_quando_solicitadas(self):
        bootstrap = {
            "dispositivos": {
                "balanca": {
                    "habilitada": True,
                    "leitura_automatica": True,
                    "protocolo": "SERIAL",
                    "porta": "COM3",
                },
                "gaveta": {
                    "habilitada": True,
                    "impressora_padrao": "EPSON TM-T20",
                },
            },
            "tef": {"provedor": "NAO_CONFIGURADO"},
        }
        with tempfile.TemporaryDirectory() as pasta:
            config_path = Path(pasta) / "terminal" / "config.json"
            with patch.dict(
                os.environ,
                {
                    "SUPERMERCADO_PDV_CONFIG": str(config_path),
                    "SUPERMERCADO_PDV_PESO_SIMULADO": "1,250",
                },
            ):
                with patch(
                    "app.listar_impressoras_windows",
                    return_value=[{"nome": "EPSON TM-T20", "padrao": True, "offline": False}],
                ):
                    with patch("app.imprimir_raw_windows", return_value=5) as imprimir_mock:
                        resultado = app.PonteLocal(bootstrap).homologar_dispositivos(
                            {"ler_balanca": True, "acionar_gaveta": True}
                        )

        por_codigo = {item["codigo"]: item for item in resultado["verificacoes"]}
        self.assertEqual(por_codigo["balanca"]["status"], "ok")
        self.assertEqual(por_codigo["balanca"]["detalhes"]["peso"], "1.250")
        self.assertEqual(por_codigo["gaveta"]["status"], "ok")
        self.assertEqual(imprimir_mock.call_count, 1)


    def test_pinpad_simulado_expoe_capacidade_sem_gravar_documento_no_log(self):
        ponte = app.PonteLocal({"tef": {"provedor": "STONE", "modo_integracao": "DESKTOP_BRIDGE", "simulador_permitido": True}})
        with patch("app.registrar_evento_dispositivo") as registrar:
            capacidades = ponte.tefCapabilities()
            resultado = ponte.captureConsumerDocument({"tipo": "CPF"})
        self.assertTrue(capacidades["captura_documento_consumidor"])
        self.assertEqual(resultado["status"], "ok")
        self.assertEqual(resultado["documento"], "52998224725")
        evidencia = registrar.call_args.args[1]
        self.assertNotIn("documento", evidencia)
        self.assertNotIn("52998224725", json.dumps(evidencia))
    def test_atalhos_globais_de_saida_existem_no_shell_desktop_com_confirmacao(self):
        fonte = Path(app.__file__).read_text(encoding="utf-8")

        self.assertIn("window.__deigoDesktopQuitInstalled", fonte)
        self.assertIn("event.key.toLowerCase() === 'q'", fonte)
        self.assertIn("event.key === 'F5'", fonte)
        self.assertIn('raiz.bind_all("<Control-F5>"', fonte)
        self.assertIn("Operações ainda não salvas serão descartadas", fonte)
        self.assertIn('raiz.bind_all("<Control-q>"', fonte)
        self.assertIn("window.SupermercadoDesktop.closeApplication();", fonte)

if __name__ == "__main__":
    unittest.main()
