import hashlib
import json
import tempfile
import zipfile
from pathlib import Path

from django.test import SimpleTestCase, override_settings

from .offline_bundle import artefato_servidor_offline


class OfflineBundleTests(SimpleTestCase):
    def _create_bundle(self, path, *, hash_override=None):
        payloads = {
            "payload/server.zip": b"server-package",
            "payload/python-runtime.zip": b"python-runtime",
            "payload/postgresql-installer.exe": b"postgres-installer",
            "payload/WinSW.exe": b"winsw",
        }
        types = {
            "servidor": "payload/server.zip",
            "python-runtime": "payload/python-runtime.zip",
            "postgresql": "payload/postgresql-installer.exe",
            "winsw": "payload/WinSW.exe",
        }
        files = []
        for kind, member in types.items():
            digest = hashlib.sha256(payloads[member]).hexdigest()
            files.append(
                {
                    "tipo": kind,
                    "caminho": member,
                    "tamanho_bytes": len(payloads[member]),
                    "sha256": hash_override if kind == "winsw" and hash_override else digest,
                }
            )
        manifest = {"contrato": "detech_server_offline_bundle_v1", "versao": "1.0.0", "arquivos": files}
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("Install-DeTecServer.ps1", "Write-Host installer")
            archive.writestr("bundle.manifest.json", json.dumps(manifest))
            for member, content in payloads.items():
                archive.writestr(member, content)

    def test_valid_bundle_is_available(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "DeTecServerOffline.zip"
            self._create_bundle(path)
            with override_settings(LOCAL_SERVER_OFFLINE_PACKAGE_PATH=path, LOCAL_SERVER_VERSION="1.0.0"):
                result = artefato_servidor_offline()
        self.assertTrue(result["publicavel"])
        self.assertTrue(result["integridade_valida"])

    def test_tampered_payload_is_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "DeTecServerOffline.zip"
            self._create_bundle(path, hash_override="0" * 64)
            with override_settings(LOCAL_SERVER_OFFLINE_PACKAGE_PATH=path, LOCAL_SERVER_VERSION="1.0.0"):
                result = artefato_servidor_offline()
        self.assertFalse(result["publicavel"])
        self.assertTrue(result["problemas"])
