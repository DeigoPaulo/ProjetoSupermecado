import hashlib
import json
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from apps.configuracoes.acceptance_evidence import gerar_evidencia_aceite


class EvidenciaAceiteTests(SimpleTestCase):
    def _validacao(self, liberavel=True):
        return {
            "liberavel": liberavel,
            "perfil": "servidor-local",
            "alvo": "producao",
            "erros": [],
            "avisos": [] if liberavel else ["Pacote pendente."],
        }

    def _pos(self, pronto=True):
        return {
            "pronto": pronto,
            "contrato": "local_post_deployment_health_v1",
            "bloqueios": [] if pronto else ["backup: pendente"],
        }

    @patch("apps.configuracoes.acceptance_evidence.diagnostico_pos_implantacao_local")
    @patch("apps.configuracoes.acceptance_evidence.validar_dossie_implantacao")
    def test_evidencia_vincula_hash_sem_expor_caminho(self, validar, pos):
        validar.return_value = self._validacao()
        pos.return_value = self._pos()
        with TemporaryDirectory() as diretorio:
            dossie = Path(diretorio) / "dossie.json"
            dossie.write_bytes(b"dossie")
            evidencia = gerar_evidencia_aceite(dossie)

        self.assertTrue(evidencia["liberavel"])
        self.assertEqual(evidencia["dossie"]["sha256"], hashlib.sha256(b"dossie").hexdigest())
        self.assertNotIn(str(dossie), json.dumps(evidencia))

    @patch("apps.configuracoes.management.commands.gerar_evidencia_aceite.gerar_evidencia_aceite")
    def test_comando_estrito_grava_e_recusa_aceite_bloqueado(self, gerar):
        gerar.return_value = {
            "contrato": "local_installation_acceptance_evidence_v1",
            "liberavel": False,
        }
        with TemporaryDirectory() as diretorio:
            saida = Path(diretorio) / "aceite.json"
            with self.assertRaises(CommandError):
                call_command(
                    "gerar_evidencia_aceite",
                    "--dossie",
                    str(Path(diretorio) / "dossie.json"),
                    "--saida",
                    str(saida),
                    "--estrito",
                    stdout=StringIO(),
                )
            self.assertTrue(saida.is_file())
            self.assertTrue(Path(str(saida) + ".sha256").is_file())
