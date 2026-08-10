from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent


class BuildPortabilityTests(unittest.TestCase):
    def test_build_nao_depende_de_caminho_absoluto(self):
        script = (ROOT / "build_windows.ps1").read_text(encoding="utf-8")

        self.assertNotRegex(script, r"[A-Za-z]:\\Users\\")
        self.assertIn('Join-Path $Root "app.py"', script)
        self.assertIn('Join-Path $Root "assets\\deigo-admin-cart.ico"', script)
        self.assertIn("--workpath $Build", script)
        self.assertIn("--specpath $Build", script)

    def test_build_falha_se_dependencia_ou_executavel_falhar(self):
        script = (ROOT / "build_windows.ps1").read_text(encoding="utf-8")
        requirements = (ROOT / "requirements-build.txt").read_text(encoding="utf-8")

        self.assertIn("Assert-LastExitCode", script)
        self.assertIn("Test-Path -LiteralPath $Output -PathType Leaf", script)
        self.assertRegex(requirements, r"pyinstaller==\d+\.\d+\.\d+")

    def test_artefatos_gerados_ficam_fora_do_git(self):
        ignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")

        self.assertIn("desktop_admin/.build-venv/", ignore)
        self.assertIn("desktop_admin/build/", ignore)
        self.assertIn("desktop_admin/dist/", ignore)
        self.assertIn("desktop_admin/*.spec", ignore)
        self.assertEqual(list(ROOT.glob("*.spec")), [])


if __name__ == "__main__":
    unittest.main()