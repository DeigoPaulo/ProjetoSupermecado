import unittest
from unittest.mock import MagicMock, patch

import app


class DeTecAdminTests(unittest.TestCase):
    def test_verificar_servidor_retorna_nada_quando_login_responde(self):
        resposta = MagicMock()
        resposta.__enter__.return_value = resposta
        with patch("app.urlopen", return_value=resposta):
            self.assertIsNone(app.verificar_servidor("http://127.0.0.1:8001"))

    def test_verificar_servidor_informa_falha_sem_abrir_webview(self):
        with patch("app.urlopen", side_effect=app.URLError("Connection refused")):
            mensagem = app.verificar_servidor("http://127.0.0.1:8000")
        self.assertIn("Connection refused", mensagem)


if __name__ == "__main__":
    unittest.main()