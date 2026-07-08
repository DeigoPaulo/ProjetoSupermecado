import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app
from devices.printers import ErroDescobertaImpressoras, listar_impressoras_windows
from devices.labels import montar_etiquetas_epl, montar_etiquetas_nativas, montar_etiquetas_zpl
from devices.printing import ErroImpressao, montar_cupom_escpos, montar_texto_cupom


class RespostaJson:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return json.dumps({"status": "ok", "terminal": {"nome": "Caixa 01"}}).encode()


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

    def test_ponte_imprime_venda_no_spooler_com_limite_de_tres_vias(self):
        ponte = app.PonteLocal({})
        payload = {
            "venda": {"id": 10, "total_bruto": "1,00", "desconto": "0,00", "total_liquido": "1,00"},
            "impressao": {"impressora_padrao": "EPSON", "numero_vias": 8},
        }
        with patch("app.imprimir_raw_windows", return_value=120) as imprimir_mock:
            sucesso = ponte.imprimir_venda(payload)
        with patch("app.imprimir_raw_windows", side_effect=ErroImpressao("impressora offline")):
            falha = ponte.imprimir_venda(payload)

        self.assertTrue(sucesso["impresso"])
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

    def test_gera_epl_e_pplb_e_recusa_ppla_sem_adaptador(self):
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
        with self.assertRaisesRegex(ErroImpressao, "adaptador homologado"):
            montar_etiquetas_nativas(payload)

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
