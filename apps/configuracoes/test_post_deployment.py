import json
import os
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings

from apps.configuracoes.post_deployment import diagnostico_pos_implantacao_local


class PosImplantacaoTests(SimpleTestCase):
    def _resposta_http(self):
        resposta = MagicMock()
        resposta.status = 200
        resposta.__enter__.return_value = resposta
        return resposta

    def test_diagnostico_completo_fica_pronto_sem_expor_caminhos(self):
        with TemporaryDirectory() as diretorio:
            raiz = Path(diretorio)
            static = raiz / "static"
            media = raiz / "media"
            logs = raiz / "logs"
            backups = raiz / "backups"
            for pasta in (static, media, logs, backups):
                pasta.mkdir()
            (backups / "supermercado-local-20260804.zip").write_bytes(b"backup")
            banco = {
                "pronto": True,
                "postgresql": True,
                "migracoes_pendentes": 0,
                "alertas": [],
            }
            with override_settings(STATIC_ROOT=static, MEDIA_ROOT=media, LOG_DIR=logs), patch.dict(
                os.environ, {"LOCAL_BACKUP_DIR": str(backups)}, clear=False
            ), patch(
                "apps.configuracoes.post_deployment.diagnostico_prontidao_banco_dados",
                return_value=banco,
            ), patch(
                "apps.configuracoes.post_deployment.urllib.request.urlopen",
                return_value=self._resposta_http(),
            ):
                diagnostico = diagnostico_pos_implantacao_local()

        self.assertTrue(diagnostico["pronto"])
        serializado = json.dumps(diagnostico).casefold()
        self.assertNotIn(str(raiz).casefold(), serializado)
        self.assertFalse(diagnostico["segredos_expostos"])

    @patch(
        "apps.configuracoes.management.commands.verificar_pos_implantacao.diagnostico_pos_implantacao_local"
    )
    def test_modo_estrito_bloqueia_instalacao_incompleta(self, diagnostico):
        diagnostico.return_value = {
            "pronto": False,
            "verificacoes": [],
            "bloqueios": ["backup: pendente"],
        }
        with self.assertRaises(CommandError):
            call_command("verificar_pos_implantacao", "--estrito", stdout=StringIO())
