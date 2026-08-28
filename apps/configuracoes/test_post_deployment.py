import hashlib
import json
import os
import zipfile
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from cryptography.hazmat.primitives import hashes, padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from django.test import SimpleTestCase, override_settings

from apps.configuracoes.post_deployment import _diagnostico_backup, diagnostico_pos_implantacao_local


class PosImplantacaoTests(SimpleTestCase):
    def _criar_backup(self, diretorio, sufixo, *, contrato="erp_local_backup_v2"):
        caminho = Path(diretorio) / f"supermercado-local-{sufixo}.zip"
        ancora = json.dumps(
            {
                "contrato": "fiscal_evidence_anchor_v1",
                "integra": True,
                "ancora_global_sha256": "a" * 64,
            },
            sort_keys=True,
        ).encode("utf-8")
        manifesto = {
            "contrato": contrato,
            "inclui_dados_json": True,
            "banco_tipo": "sqlite",
            "inclui_sqlite": True,
            "sqlite_snapshot_consistente": True,
            "inclui_postgresql": False,
            "inclui_media": False,
            "inclui_ancora_evidencias_fiscais": True,
            "evidencias_fiscais_contrato": "fiscal_evidence_anchor_v1",
            "evidencias_fiscais_arquivo": "fiscal-evidence-anchor.json",
            "evidencias_fiscais_sha256": hashlib.sha256(ancora).hexdigest(),
        }
        with zipfile.ZipFile(caminho, "w", zipfile.ZIP_DEFLATED) as arquivo:
            arquivo.writestr("manifesto.json", json.dumps(manifesto))
            arquivo.writestr("dados.json", "{}")
            arquivo.writestr("db.sqlite3", b"sqlite-snapshot")
            arquivo.writestr("fiscal-evidence-anchor.json", ancora)
        digest = hashlib.sha256(caminho.read_bytes()).hexdigest()
        Path(f"{caminho}.sha256").write_text(
            f"{digest}  {caminho.name}\n", encoding="ascii"
        )
        return caminho

    def _criptografar_backup(self, caminho, senha):
        salt, iv = os.urandom(16), os.urandom(16)
        chave = PBKDF2HMAC(
            algorithm=hashes.SHA256(), length=32, salt=salt, iterations=200_000
        ).derive(senha.encode("utf-8"))
        padder = padding.PKCS7(128).padder()
        dados = padder.update(caminho.read_bytes()) + padder.finalize()
        encryptor = Cipher(algorithms.AES(chave), modes.CBC(iv)).encryptor()
        criptografado = Path(f"{caminho}.aes")
        criptografado.write_bytes(
            b"MFLOWAES1" + salt + iv + encryptor.update(dados) + encryptor.finalize()
        )
        digest = hashlib.sha256(criptografado.read_bytes()).hexdigest()
        Path(f"{criptografado}.sha256").write_text(
            f"{digest}  {criptografado.name}\n", encoding="ascii"
        )
        caminho.unlink()
        Path(f"{caminho}.sha256").unlink()
        return criptografado

    def _resposta_http(self):
        resposta = MagicMock()
        resposta.status = 200
        resposta.__enter__.return_value = resposta
        return resposta

    @override_settings(LOCAL_BACKUP_MAX_AGE_HOURS=36)
    def test_diagnostico_completo_fica_pronto_sem_expor_caminhos(self):
        with TemporaryDirectory() as diretorio:
            raiz = Path(diretorio)
            static = raiz / "static"
            media = raiz / "media"
            logs = raiz / "logs"
            backups = raiz / "backups"
            for pasta in (static, media, logs, backups):
                pasta.mkdir()
            self._criar_backup(backups, "20260804")
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
        self.assertEqual(diagnostico["backup"]["politica_contrato"], "backup_age_policy_v1")
        self.assertEqual(diagnostico["backup"]["politica_origem"], "ambiente")
        self.assertEqual(diagnostico["backup"]["idade_maxima_horas"], 36)

    @override_settings(LOCAL_BACKUP_MAX_AGE_HOURS=0)
    def test_backup_bloqueia_sem_politica_e_identifica_substituicao_explicita(self):
        with TemporaryDirectory() as diretorio:
            backups = Path(diretorio) / "backups"
            backups.mkdir()
            self._criar_backup(backups, "20260825")
            with patch.dict(os.environ, {"LOCAL_BACKUP_DIR": str(backups)}, clear=False):
                sem_politica = _diagnostico_backup()
                com_substituicao = _diagnostico_backup(idade_maxima_horas=48)

        self.assertFalse(sem_politica["pronto"])
        self.assertFalse(sem_politica["politica_configurada"])
        self.assertEqual(sem_politica["politica_origem"], "ambiente")
        self.assertIn("LOCAL_BACKUP_MAX_AGE_HOURS", " ".join(sem_politica["alertas"]))
        self.assertTrue(com_substituicao["pronto"])
        self.assertTrue(com_substituicao["politica_configurada"])
        self.assertEqual(com_substituicao["politica_origem"], "argumento")
        self.assertEqual(com_substituicao["idade_maxima_horas"], 48)
        self.assertNotIn(str(backups), json.dumps(com_substituicao))

    @override_settings(LOCAL_BACKUP_MAX_AGE_HOURS=48)
    def test_backup_adulterado_bloqueia_sem_expor_caminho(self):
        with TemporaryDirectory() as diretorio:
            backups = Path(diretorio) / "backups"
            backups.mkdir()
            caminho = self._criar_backup(backups, "20260825")
            with caminho.open("ab") as arquivo:
                arquivo.write(b"adulterado")
            with patch.dict(os.environ, {"LOCAL_BACKUP_DIR": str(backups)}, clear=False):
                diagnostico = _diagnostico_backup()

        self.assertFalse(diagnostico["pronto"])
        self.assertEqual(diagnostico["validacao"]["codigo"], "checksum_divergente")
        self.assertFalse(diagnostico["validacao"]["sha256_valido"])
        self.assertNotIn(str(backups), json.dumps(diagnostico))

    @override_settings(LOCAL_BACKUP_MAX_AGE_HOURS=48)
    def test_backup_com_contrato_incompativel_bloqueia(self):
        with TemporaryDirectory() as diretorio:
            backups = Path(diretorio) / "backups"
            backups.mkdir()
            self._criar_backup(backups, "20260825", contrato="erp_local_backup_v1")
            with patch.dict(os.environ, {"LOCAL_BACKUP_DIR": str(backups)}, clear=False):
                diagnostico = _diagnostico_backup()

        self.assertFalse(diagnostico["pronto"])
        self.assertTrue(diagnostico["validacao"]["sha256_valido"])
        self.assertEqual(diagnostico["validacao"]["codigo"], "contrato_incompativel")

    @override_settings(LOCAL_BACKUP_MAX_AGE_HOURS=48)
    def test_backup_com_caminho_inseguro_bloqueia(self):
        with TemporaryDirectory() as diretorio:
            backups = Path(diretorio) / "backups"
            backups.mkdir()
            caminho = self._criar_backup(backups, "20260825")
            with zipfile.ZipFile(caminho, "a", zipfile.ZIP_DEFLATED) as arquivo:
                arquivo.writestr("../escape.txt", "recusado")
            digest = hashlib.sha256(caminho.read_bytes()).hexdigest()
            Path(f"{caminho}.sha256").write_text(
                f"{digest}  {caminho.name}\n", encoding="ascii"
            )
            with patch.dict(os.environ, {"LOCAL_BACKUP_DIR": str(backups)}, clear=False):
                diagnostico = _diagnostico_backup()

        self.assertFalse(diagnostico["pronto"])
        self.assertEqual(
            diagnostico["validacao"]["codigo"], "estrutura_caminho_inseguro"
        )

    @override_settings(LOCAL_BACKUP_MAX_AGE_HOURS=48)
    def test_backup_aes_e_validado_com_senha_operacional(self):
        with TemporaryDirectory() as diretorio:
            backups = Path(diretorio) / "backups"
            backups.mkdir()
            caminho = self._criar_backup(backups, "20260825")
            self._criptografar_backup(caminho, "senha-de-homologacao")
            with patch.dict(
                os.environ,
                {
                    "LOCAL_BACKUP_DIR": str(backups),
                    "BACKUP_ENCRYPTION_PASSPHRASE": "senha-de-homologacao",
                },
                clear=False,
            ):
                diagnostico = _diagnostico_backup()

        self.assertTrue(diagnostico["pronto"])
        self.assertTrue(diagnostico["validacao"]["criptografado"])
        self.assertTrue(diagnostico["validacao"]["conteudo_validado"])
        self.assertNotIn("senha-de-homologacao", json.dumps(diagnostico))

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
        self.assertIsNone(
            diagnostico.call_args.kwargs["idade_maxima_backup_horas"]
        )

        diagnostico.reset_mock()
        diagnostico.return_value = {
            "pronto": True,
            "verificacoes": [],
            "bloqueios": [],
        }
        call_command(
            "verificar_pos_implantacao",
            "--backup-max-horas",
            "48",
            stdout=StringIO(),
        )
        self.assertEqual(
            diagnostico.call_args.kwargs["idade_maxima_backup_horas"], 48
        )
