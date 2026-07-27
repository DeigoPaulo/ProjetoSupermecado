import json
import tempfile
import unittest
from pathlib import Path

from devices.events import EventLog


class EventLogTests(unittest.TestCase):
    def test_eventos_recebem_ids_unicos_e_estaveis_no_arquivo(self):
        with tempfile.TemporaryDirectory() as pasta:
            fila = EventLog(Path(pasta) / "devices.log.jsonl")
            fila.append("balanca", {"indice": 1})
            fila.append("balanca", {"indice": 2})

            eventos = fila.listar(10)["eventos"]

        self.assertEqual(len(eventos), 2)
        self.assertNotEqual(eventos[0]["id"], eventos[1]["id"])
        self.assertEqual(eventos[0]["payload"]["indice"], 1)

    def test_cursor_envia_eventos_antigos_antes_dos_recentes(self):
        with tempfile.TemporaryDirectory() as pasta:
            fila = EventLog(Path(pasta) / "devices.log.jsonl")
            for indice in range(250):
                fila.append("teste", {"indice": indice})

            primeiro = fila.pendentes(0, 100)
            segundo = fila.pendentes(primeiro["proximo_cursor"], 100)
            terceiro = fila.pendentes(segundo["proximo_cursor"], 100)

        self.assertEqual([item["payload"]["indice"] for item in primeiro["eventos"]], list(range(100)))
        self.assertEqual([item["payload"]["indice"] for item in segundo["eventos"]], list(range(100, 200)))
        self.assertEqual([item["payload"]["indice"] for item in terceiro["eventos"]], list(range(200, 250)))

    def test_evento_legado_sem_id_recebe_id_deterministico(self):
        linha = json.dumps({"tipo": "balanca", "payload": {"status": "erro"}})

        primeira = EventLog.decodificar(linha)
        segunda = EventLog.decodificar(linha)

        self.assertTrue(primeira["id"].startswith("legado-"))
        self.assertEqual(primeira["id"], segunda["id"])

    def test_compactacao_remove_somente_confirmados_e_preserva_pendentes(self):
        with tempfile.TemporaryDirectory() as pasta:
            fila = EventLog(Path(pasta) / "devices.log.jsonl")
            for indice in range(650):
                fila.append("teste", {"indice": indice})

            resultado = fila.compactar_confirmados(
                600,
                manter_confirmados=100,
                forcar=True,
            )
            apos = fila.pendentes(resultado["cursor"], 100)
            todos = fila.listar(200)

        self.assertTrue(resultado["compactado"])
        self.assertEqual(resultado["removidos"], 500)
        self.assertEqual(resultado["cursor"], 100)
        self.assertEqual(resultado["total"], 150)
        self.assertEqual([item["payload"]["indice"] for item in apos["eventos"]], list(range(600, 650)))
        self.assertEqual(todos["eventos"][0]["payload"]["indice"], 500)

    def test_cursor_maior_que_log_e_reiniciado_sem_descartar_eventos(self):
        with tempfile.TemporaryDirectory() as pasta:
            fila = EventLog(Path(pasta) / "devices.log.jsonl")
            fila.append("teste", {"indice": 1})

            lote = fila.pendentes(99, 100)

        self.assertTrue(lote["cursor_reiniciado"])
        self.assertEqual(lote["cursor"], 0)
        self.assertEqual(lote["eventos"][0]["payload"]["indice"], 1)


if __name__ == "__main__":
    unittest.main()
