from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent


class BuildPortabilityTests(unittest.TestCase):
    def test_spec_nao_depende_de_caminho_de_outro_computador(self):
        spec = (ROOT / "DeTecPDV.spec").read_text(encoding="utf-8")

        self.assertIn("SPECPATH", spec)
        self.assertNotRegex(spec, r"[A-Za-z]:\\Users\\")
        self.assertIn('root / "app.py"', spec)
        self.assertIn('root / "assets" / "deigo-pdv-cart.ico"', spec)
        self.assertIn('name="DeTecPDV"', spec)
        self.assertIn('icon=[str(icon)]', spec)

    def test_spec_legado_nao_pode_voltar_ao_pacote(self):
        self.assertFalse(
            (ROOT / "SupermercadoPDV.spec").exists(),
            "O spec legado expoe caminho absoluto e pode gerar o executavel com a marca antiga.",
        )

    def test_build_usa_ambiente_local_ignorado_e_spec_portatil(self):
        script = (ROOT / "build_windows.ps1").read_text(encoding="utf-8")
        ignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
        desktop_ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

        self.assertIn('Join-Path $Root ".build-venv"', script)
        self.assertIn('Join-Path $Root "DeTecPDV.spec"', script)
        self.assertNotIn("pip install --upgrade pip", script)
        self.assertIn("desktop_pdv/.build-venv/", ignore)
        self.assertIn("!DeTecPDV.spec", desktop_ignore)

    def test_versao_padrao_e_unica_no_app_servidor_e_publicacao(self):
        version_source = (ROOT / "version.py").read_text(encoding="utf-8")
        match = re.search(r'APP_VERSION\s*=\s*"([0-9]+\.[0-9]+\.[0-9]+)"', version_source)
        self.assertIsNotNone(match)
        version = match.group(1)

        settings = (PROJECT_ROOT / "config" / "settings.py").read_text(encoding="utf-8")
        publish = (ROOT / "publish_windows.ps1").read_text(encoding="utf-8")
        self.assertIn(f'PDV_DESKTOP_VERSION = os.getenv("PDV_DESKTOP_VERSION", "{version}")', settings)
        self.assertIn(f'[string]$Version = "{version}"', publish)

    def test_manual_documenta_credencial_pcsc_com_fallback(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("## Credencial NFC de supervisor", readme)
        self.assertIn("winscard.dll", readme)
        self.assertIn("nao e gravado", readme)
        self.assertIn("leitor configurado como teclado", readme)

    def test_manual_documenta_publicacao_fora_do_git(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("## Deploy do instalador no servidor", readme)
        self.assertIn("artifacts/DeTecPDV.msi.version.json", readme)
        self.assertIn("Nunca compile o PDV no servidor Linux", readme)


if __name__ == "__main__":
    unittest.main()