import hashlib
import io
import os
import subprocess
import sys
import unittest
import json
import tempfile
import zipfile
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, override_settings

from .artifacts import artefato_admin_desktop
from .offline_bundle import artefato_servidor_offline, validar_pacote_servidor_offline


class OfflineBundleTests(SimpleTestCase):
    @staticmethod
    def _zip_bytes(files):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            for name, content in files.items():
                archive.writestr(name, content)
        return buffer.getvalue()

    def _create_bundle(
        self, path, *, hash_override=None, missing_type=None, duplicate_type=None,
        unexpected=False, invalid_server=False, empty_wheelhouse=False, duplicate_member=False,
    ):
        server = b"not-a-zip" if invalid_server else self._zip_bytes({
            "manage.py": b"", "requirements.txt": b"Django==5.0",
            "config/settings.py": b"", "apps/core.py": b"",
        })
        wheelhouse = self._zip_bytes({} if empty_wheelhouse else {"Django-5.0-py3-none-any.whl": b"wheel"})
        pdv, admin = b"pdv-desktop", b"admin-desktop"
        payloads = {
            "payload/server.zip": server,
            "payload/python-runtime.zip": b"python-runtime",
            "payload/wheelhouse.zip": wheelhouse,
            "payload/postgresql-installer.exe": b"postgres-installer",
            "payload/WinSW.exe": b"winsw",
            "Instalar DeTec Server.exe": b"launcher",
            "payload/DeTecPDV.exe": pdv,
            "payload/DeTecPDV.exe.version.json": json.dumps(
                {"version": "1.2.3", "sha256": hashlib.sha256(pdv).hexdigest()}
            ).encode(),
            "payload/DeTecAdmin.exe": admin,
            "payload/DeTecAdmin.exe.version.json": json.dumps(
                {"version": "1.2.3", "sha256": hashlib.sha256(admin).hexdigest()}
            ).encode(),
        }
        types = {
            "servidor": "payload/server.zip",
            "python-runtime": "payload/python-runtime.zip",
            "python-wheelhouse": "payload/wheelhouse.zip",
            "postgresql": "payload/postgresql-installer.exe",
            "winsw": "payload/WinSW.exe",
            "launcher": "Instalar DeTec Server.exe",
            "pdv-desktop": "payload/DeTecPDV.exe",
            "pdv-desktop-manifest": "payload/DeTecPDV.exe.version.json",
            "admin-desktop": "payload/DeTecAdmin.exe",
            "admin-desktop-manifest": "payload/DeTecAdmin.exe.version.json",
        }
        if missing_type:
            payloads.pop(types.pop(missing_type))
        files = []
        for kind, member in types.items():
            digest = hashlib.sha256(payloads[member]).hexdigest()
            files.append({
                "tipo": kind, "caminho": member, "tamanho_bytes": len(payloads[member]),
                "sha256": hash_override if kind == "winsw" and hash_override else digest,
            })
        if duplicate_type:
            files.append(next(item.copy() for item in files if item["tipo"] == duplicate_type))
        manifest = {
            "contrato": "detech_server_offline_bundle_v1", "versao": "1.0.0",
            "instalador": "Install-DeTecServer.ps1", "arquivos": files,
        }
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("Install-DeTecServer.ps1", "Write-Host installer")
            archive.writestr("bundle.manifest.json", json.dumps(manifest))
            for member, value in payloads.items():
                archive.writestr(member, value)
            if unexpected:
                archive.writestr("payload/extra.bin", b"undeclared")
            if duplicate_member:
                archive.writestr("PAYLOAD/WINSW.EXE", b"duplicate")

    def _validate(self, path):
        return validar_pacote_servidor_offline(path, "1.0.0")

    def test_valid_bundle_is_available(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "DeTecServerOffline.zip"
            self._create_bundle(path)
            result = self._validate(path)
        self.assertEqual(result["contrato"], "detech_server_offline_package_validation_v2")
        self.assertTrue(result["publicavel"])
        self.assertTrue(result["conteudo_servidor_valido"])
        self.assertTrue(result["wheelhouse_valido"])

    def _central_validate(self, path):
        with override_settings(LOCAL_SERVER_OFFLINE_PACKAGE_PATH=path, LOCAL_SERVER_VERSION="1.0.0"):
            return artefato_servidor_offline()

    @staticmethod
    def _write_checksum(path, *, digest=None, name=None):
        digest = digest or hashlib.sha256(path.read_bytes()).hexdigest()
        name = name or path.name
        Path(f"{path}.sha256").write_text(f"{digest}  {name}\n", encoding="utf-8")

    def test_central_accepts_published_bundle_with_bound_checksum(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "DeTecServerOffline.zip"
            self._create_bundle(path)
            self._write_checksum(path)
            result = self._central_validate(path)
        self.assertEqual(result["contrato_publicacao"], "detech_server_offline_publication_validation_v1")
        self.assertTrue(result["checksum_hash_valido"])
        self.assertTrue(result["checksum_nome_vinculado"])
        self.assertTrue(result["publicacao_valida"])
        self.assertTrue(result["publicavel"])

    def test_central_blocks_bundle_without_published_checksum(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "DeTecServerOffline.zip"
            self._create_bundle(path)
            result = self._central_validate(path)
        self.assertFalse(result["checksum_encontrado"])
        self.assertFalse(result["publicacao_valida"])
        self.assertFalse(result["publicavel"])

    def test_central_blocks_checksum_with_wrong_hash_or_filename(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "DeTecServerOffline.zip"
            self._create_bundle(path)
            self._write_checksum(path, digest="0" * 64, name="outro-pacote.zip")
            result = self._central_validate(path)
        self.assertTrue(result["checksum_encontrado"])
        self.assertFalse(result["checksum_hash_valido"])
        self.assertFalse(result["checksum_nome_vinculado"])
        self.assertFalse(result["publicacao_valida"])
        self.assertFalse(result["publicavel"])


    def test_tampered_payload_is_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "DeTecServerOffline.zip"
            self._create_bundle(path, hash_override="0" * 64)
            result = self._validate(path)
        self.assertFalse(result["publicavel"])
        self.assertTrue(result["problemas"])

    def test_missing_wheelhouse_is_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "DeTecServerOffline.zip"
            self._create_bundle(path, missing_type="python-wheelhouse")
            result = self._validate(path)
        self.assertFalse(result["publicavel"])
        self.assertIn("python-wheelhouse", " ".join(result["problemas"]))

    def test_empty_wheelhouse_is_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "DeTecServerOffline.zip"
            self._create_bundle(path, empty_wheelhouse=True)
            result = self._validate(path)
        self.assertFalse(result["publicavel"])
        self.assertFalse(result["wheelhouse_valido"])

    def test_invalid_nested_server_is_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "DeTecServerOffline.zip"
            self._create_bundle(path, invalid_server=True)
            result = self._validate(path)
        self.assertFalse(result["publicavel"])
        self.assertFalse(result["conteudo_servidor_valido"])

    def test_duplicate_manifest_type_is_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "DeTecServerOffline.zip"
            self._create_bundle(path, duplicate_type="winsw")
            result = self._validate(path)
        self.assertFalse(result["publicavel"])
        self.assertIn("duplicado", " ".join(result["problemas"]).lower())

    def test_duplicate_archive_member_is_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "DeTecServerOffline.zip"
            self._create_bundle(path, duplicate_member=True)
            result = self._validate(path)
        self.assertFalse(result["publicavel"])
        self.assertIn("duplicada", " ".join(result["problemas"]).lower())

    def test_undeclared_archive_member_is_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "DeTecServerOffline.zip"
            self._create_bundle(path, unexpected=True)
            result = self._validate(path)
        self.assertFalse(result["publicavel"])
        self.assertIn("não declarado", " ".join(result["problemas"]).lower())



@unittest.skipUnless(os.name == "nt", "Empacotador offline exclusivo do Windows.")
class OfflineBundlePackagerContractTests(SimpleTestCase):
    def _run_packager(self, directory, *, extra_wheel=False):
        root = Path(directory)
        server = root / "server.zip"
        with zipfile.ZipFile(server, "w") as archive:
            archive.writestr("manage.py", "")
            archive.writestr("requirements.txt", "Django==5.0")
            archive.writestr("config/settings.py", "")
            archive.writestr("apps/core.py", "")
        wheelhouse = root / "wheelhouse"
        wheelhouse.mkdir()
        (wheelhouse / "Django-5.0-py3-none-any.whl").write_bytes(b"wheel")
        if extra_wheel:
            (wheelhouse / "arquivo-indevido.txt").write_bytes(b"blocked")

        runtime = root / "python-runtime.zip"
        postgres = root / "postgres.exe"
        winsw = root / "WinSW.exe"
        launcher = root / "launcher.exe"
        pdv = root / "DeTecPDV.exe"
        admin = root / "DeTecAdmin.exe"
        for path, value in (
            (runtime, b"runtime"), (postgres, b"postgres"), (winsw, b"winsw"),
            (launcher, b"launcher"), (pdv, b"pdv"), (admin, b"admin"),
        ):
            path.write_bytes(value)
        pdv_manifest = root / "pdv.json"
        admin_manifest = root / "admin.json"
        pdv_manifest.write_text(
            json.dumps({"version": "1.2.3", "sha256": hashlib.sha256(pdv.read_bytes()).hexdigest()}),
            encoding="utf-8",
        )
        admin_manifest.write_text(
            json.dumps({"version": "1.2.3", "sha256": hashlib.sha256(admin.read_bytes()).hexdigest()}),
            encoding="utf-8",
        )
        output = root / "output"
        script = Path(settings.BASE_DIR) / "scripts" / "package_detech_server_offline.ps1"
        powershell = Path(os.environ["SystemRoot"]) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
        command = [
            str(powershell), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
            "-Version", "1.0.0", "-ServerPackagePath", str(server),
            "-PythonRuntimePath", str(runtime), "-PythonRuntimeSha256", hashlib.sha256(runtime.read_bytes()).hexdigest(),
            "-PostgreSqlInstallerPath", str(postgres), "-PostgreSqlInstallerSha256", hashlib.sha256(postgres.read_bytes()).hexdigest(),
            "-WinSWPath", str(winsw), "-WinSWSha256", hashlib.sha256(winsw.read_bytes()).hexdigest(),
            "-InstallerLauncherPath", str(launcher), "-WheelhouseDirectory", str(wheelhouse),
            "-PdvDesktopPath", str(pdv), "-PdvDesktopManifestPath", str(pdv_manifest),
            "-AdminDesktopPath", str(admin), "-AdminDesktopManifestPath", str(admin_manifest),
            "-OutputDirectory", str(output), "-PythonPath", sys.executable, "-Force",
        ]
        completed = subprocess.run(
            command, cwd=settings.BASE_DIR, capture_output=True, text=True, timeout=90, check=False
        )
        return completed, output / "DeTecServer-1.0.0-windows-offline.zip"

    def test_packager_promotes_only_bundle_approved_by_shared_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            completed, package = self._run_packager(directory)
            output = completed.stdout + completed.stderr
            self.assertEqual(completed.returncode, 0, output)
            self.assertTrue(package.is_file())
            self.assertTrue(Path(f"{package}.sha256").is_file())
            self.assertFalse(Path(f"{package}.tmp.zip").exists())
            self.assertFalse(Path(f"{package}.sha256.tmp").exists())
            result = validar_pacote_servidor_offline(package, "1.0.0")
        self.assertTrue(result["publicavel"])
        self.assertEqual(result["contrato"], "detech_server_offline_package_validation_v2")

    def test_packager_rejects_invalid_wheelhouse_without_publishing_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            completed, package = self._run_packager(directory, extra_wheel=True)
            self.assertNotEqual(completed.returncode, 0)
            self.assertFalse(package.exists())
            self.assertFalse(Path(f"{package}.sha256").exists())
            self.assertFalse(Path(f"{package}.tmp.zip").exists())
            self.assertFalse(Path(f"{package}.sha256.tmp").exists())


    def _run_publisher(self, source_directory, destination, *, force=True):
        script = Path(settings.BASE_DIR) / "scripts" / "publish_detech_server_offline.ps1"
        powershell = Path(os.environ["SystemRoot"]) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
        command = [
            str(powershell), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
            "-Version", "1.0.0", "-SourceDirectory", str(source_directory),
            "-Destination", str(destination), "-PythonPath", sys.executable,
        ]
        if force:
            command.append("-Force")
        return subprocess.run(
            command, cwd=settings.BASE_DIR, capture_output=True, text=True, timeout=90, check=False
        )

    def test_publisher_validates_copy_and_promotes_zip_with_bound_checksum(self):
        with tempfile.TemporaryDirectory() as directory:
            completed, package = self._run_packager(directory)
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            destination = Path(directory) / "central" / "DeTecServerOffline.zip"
            published = self._run_publisher(package.parent, destination)
            output = published.stdout + published.stderr
            self.assertEqual(published.returncode, 0, output)
            checksum = Path(f"{destination}.sha256")
            self.assertTrue(destination.is_file())
            self.assertTrue(checksum.is_file())
            digest, name = checksum.read_text(encoding="utf-8").strip().split("  ", 1)
            self.assertEqual(name, destination.name)
            self.assertEqual(digest.lower(), hashlib.sha256(destination.read_bytes()).hexdigest())
            result = validar_pacote_servidor_offline(destination, "1.0.0")
            self.assertTrue(result["publicavel"])
            with override_settings(
                LOCAL_SERVER_OFFLINE_PACKAGE_PATH=destination,
                LOCAL_SERVER_VERSION="1.0.0",
            ):
                central_result = artefato_servidor_offline()
            self.assertTrue(central_result["publicacao_valida"])
            self.assertFalse(list(destination.parent.glob("*.uploading-*")))
            self.assertFalse(list(destination.parent.glob("*.rollback-*")))

    def test_publisher_rejects_tampered_source_without_creating_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            completed, package = self._run_packager(directory)
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            package.write_bytes(package.read_bytes() + b"tampered")
            destination = Path(directory) / "central" / "DeTecServerOffline.zip"
            published = self._run_publisher(package.parent, destination)
            self.assertNotEqual(published.returncode, 0)
            self.assertFalse(destination.exists())
            self.assertFalse(Path(f"{destination}.sha256").exists())

    def test_failed_forced_publication_preserves_previous_zip_and_checksum(self):
        with tempfile.TemporaryDirectory() as directory:
            completed, package = self._run_packager(directory)
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            destination = Path(directory) / "central" / "DeTecServerOffline.zip"
            first = self._run_publisher(package.parent, destination)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            checksum = Path(f"{destination}.sha256")
            original_package = destination.read_bytes()
            original_checksum = checksum.read_bytes()

            package.write_bytes(package.read_bytes() + b"tampered")
            rejected = self._run_publisher(package.parent, destination, force=True)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertEqual(destination.read_bytes(), original_package)
            self.assertEqual(checksum.read_bytes(), original_checksum)
            self.assertFalse(list(destination.parent.glob("*.uploading-*")))
            self.assertFalse(list(destination.parent.glob("*.rollback-*")))


class AdminDesktopArtifactTests(SimpleTestCase):
    def test_admin_desktop_requires_matching_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "DeTecAdmin.exe"
            content = b"admin-desktop"
            path.write_bytes(content)
            path.with_name(path.name + ".version.json").write_text(
                json.dumps({"version": "1.2.3", "sha256": hashlib.sha256(content).hexdigest()}),
                encoding="utf-8",
            )
            with override_settings(ADMIN_DESKTOP_INSTALLER_PATH=path, ADMIN_DESKTOP_VERSION="1.2.3"):
                result = artefato_admin_desktop()
        self.assertTrue(result["publicavel"])
        self.assertEqual(result["sha256"], hashlib.sha256(content).hexdigest())

    def test_tampered_admin_desktop_is_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "DeTecAdmin.exe"
            path.write_bytes(b"altered")
            path.with_name(path.name + ".version.json").write_text(
                json.dumps({"version": "1.2.3", "sha256": "0" * 64}), encoding="utf-8",
            )
            with override_settings(ADMIN_DESKTOP_INSTALLER_PATH=path, ADMIN_DESKTOP_VERSION="1.2.3"):
                result = artefato_admin_desktop()
        self.assertFalse(result["publicavel"])
        self.assertIn("SHA-256", result["problemas"][0])
