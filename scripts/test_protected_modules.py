import json
import tempfile
import unittest
import zipfile
from pathlib import Path

import protected_modules


class ProtectedModulesTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "apps" / "licenciamento" / "services.py"
        self.source.parent.mkdir(parents=True)
        self.source.write_text("VALUE = 1\n", encoding="utf-8")
        self.overlay = self.root / "overlay"
        suffix = protected_modules.importlib.machinery.EXTENSION_SUFFIXES[0]
        self.binary = self.overlay / "apps" / "licenciamento" / ("services" + suffix)
        self.binary.parent.mkdir(parents=True)
        self.binary.write_bytes(b"compiled-module")
        self.manifest = {
            "contract": protected_modules.CONTRACT,
            "commit": "a" * 40,
            "runtime": protected_modules.runtime_identity(),
            "modules": [{
                "module": "apps.licenciamento.services",
                "source": "apps/licenciamento/services.py",
                "source_sha256": protected_modules.sha256(self.source),
                "binary": self.binary.relative_to(self.overlay).as_posix(),
                "binary_sha256": protected_modules.sha256(self.binary),
                "binary_size": self.binary.stat().st_size,
            }],
        }
        (self.overlay / "protected-modules.manifest.json").write_text(
            json.dumps(self.manifest), encoding="utf-8"
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_validate_accepts_matching_overlay(self):
        result = protected_modules.validate(self.root, self.overlay, commit="a" * 40)
        self.assertEqual(result["contract"], protected_modules.CONTRACT)

    def test_validate_rejects_tampered_binary(self):
        self.binary.write_bytes(b"tampered")
        with self.assertRaisesRegex(protected_modules.ProtectionError, "adulterado"):
            protected_modules.validate(self.root, self.overlay, commit="a" * 40)

    def test_validate_rejects_changed_source(self):
        self.source.write_text("VALUE = 2\n", encoding="utf-8")
        with self.assertRaisesRegex(protected_modules.ProtectionError, "Fonte alterada"):
            protected_modules.validate(self.root, self.overlay, commit="a" * 40)

    def test_apply_rejects_archive_from_another_source_revision(self):
        archive = self.root / "wrong-server.zip"
        with zipfile.ZipFile(archive, "w") as package:
            package.writestr("apps/licenciamento/services.py", "VALUE = 99\n")
        with self.assertRaisesRegex(protected_modules.ProtectionError, "Fonte do pacote diverge"):
            protected_modules.apply(self.root, archive, self.overlay, "a" * 40)

    def test_apply_replaces_source_and_embeds_manifest(self):
        archive = self.root / "server.zip"
        with zipfile.ZipFile(archive, "w") as package:
            package.write(self.source, "apps/licenciamento/services.py")
        protected_modules.apply(self.root, archive, self.overlay, "a" * 40)
        with zipfile.ZipFile(archive) as package:
            names = set(package.namelist())
            self.assertNotIn("apps/licenciamento/services.py", names)
            self.assertIn(self.manifest["modules"][0]["binary"], names)
            self.assertIn("protected-modules.manifest.json", names)


if __name__ == "__main__":
    unittest.main()
