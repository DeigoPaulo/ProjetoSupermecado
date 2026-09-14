import io
import json
import subprocess
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext

from .auditoria_importacoes_catalogo_teste import auditar_importacoes_catalogo_teste


class AuditoriaImportacoesCatalogoTesteTests(SimpleTestCase):
    def _arquivo(self, raiz, relativo, conteudo):
        caminho = raiz / relativo
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(conteudo, encoding="utf-8")

    def test_importacoes_runtime_direta_e_dinamica_sao_bloqueadas(self):
        with TemporaryDirectory() as temporario:
            raiz = Path(temporario)
            self._arquivo(
                raiz,
                "apps/operacional.py",
                "from apps.fiscal.test_support_identidades_fiscais import obter_identidade_fiscal_teste\n"
                "import importlib\n"
                "importlib.import_module('apps.fiscal.test_support_identidades_fiscais')\n"
                "from importlib import import_module\n"
                "import_module('apps.fiscal.test_support_identidades_fiscais')\n",
            )
            resultado = auditar_importacoes_catalogo_teste(raiz, incluir_detalhes=True)
        self.assertFalse(resultado["conforme"])
        self.assertEqual(resultado["resumo"]["importacoes_runtime_bloqueadas"], 3)
        self.assertEqual(
            {item["mecanismo"] for item in resultado["violacoes"]},
            {"IMPORT_FROM", "IMPORT_DINAMICO"},
        )

    def test_importacao_em_arquivo_de_teste_e_permitida(self):
        with TemporaryDirectory() as temporario:
            raiz = Path(temporario)
            self._arquivo(
                raiz,
                "apps/fiscal/test_exemplo.py",
                "from .test_support_identidades_fiscais import obter_identidade_fiscal_teste\n",
            )
            resultado = auditar_importacoes_catalogo_teste(raiz)
        self.assertTrue(resultado["conforme"])
        self.assertEqual(resultado["resumo"]["importacoes_permitidas_em_testes"], 1)
        self.assertNotIn("violacoes", resultado)

    def test_texto_sem_chamada_de_importacao_nao_e_falso_positivo(self):
        with TemporaryDirectory() as temporario:
            raiz = Path(temporario)
            self._arquivo(
                raiz,
                "apps/descricao.py",
                "MODULO_PROIBIDO = 'apps.fiscal.test_support_identidades_fiscais'\n",
            )
            resultado = auditar_importacoes_catalogo_teste(raiz)
        self.assertTrue(resultado["conforme"])
        self.assertEqual(resultado["resumo"]["importacoes_runtime_bloqueadas"], 0)

    def test_erro_de_sintaxe_fecha_o_portao(self):
        with TemporaryDirectory() as temporario:
            raiz = Path(temporario)
            self._arquivo(raiz, "apps/quebrado.py", "def incompleto(\n")
            resultado = auditar_importacoes_catalogo_teste(raiz, incluir_detalhes=True)
        self.assertFalse(resultado["conforme"])
        self.assertEqual(resultado["resumo"]["erros_leitura_ou_sintaxe"], 1)
        self.assertEqual(resultado["erros"][0]["tipo"], "SyntaxError")

    def test_projeto_atual_nao_possui_importacao_operacional(self):
        resultado = auditar_importacoes_catalogo_teste(settings.BASE_DIR)
        self.assertTrue(resultado["conforme"])
        self.assertGreaterEqual(resultado["resumo"]["importacoes_permitidas_em_testes"], 2)
        self.assertEqual(resultado["resumo"]["importacoes_runtime_bloqueadas"], 0)
        self.assertTrue(resultado["seguranca"]["analise_ast_sem_importar_modulos"])

    def test_rotina_padrao_executa_portao_antes_dos_testes(self):
        rotina = (Path(settings.BASE_DIR) / "scripts/test_regression.ps1").read_text(
            encoding="utf-8"
        )
        chamada_portao = '& $Python $Manage "auditar_importacoes_catalogo_teste"'
        inicio_testes = '$ArgumentosBase = @($Manage, "test", "-v", "1")'
        self.assertIn(chamada_portao, rotina)
        self.assertIn(inicio_testes, rotina)
        self.assertLess(rotina.index(chamada_portao), rotina.index(inicio_testes))
        trecho_portao = rotina[
            rotina.index(chamada_portao):rotina.index(inicio_testes)
        ]
        self.assertIn("$LASTEXITCODE -ne 0", trecho_portao)
        self.assertIn("throw", trecho_portao)

    def test_git_archive_exclui_catalogo_e_arquivos_de_teste(self):
        with TemporaryDirectory() as temporario:
            arquivo_zip = Path(temporario) / "apps-producao.zip"
            subprocess.run(
                [
                    "git", "archive", "--format=zip", f"--output={arquivo_zip}",
                    "HEAD", "--", "apps",
                ],
                cwd=settings.BASE_DIR,
                check=True,
                capture_output=True,
            )
            with zipfile.ZipFile(arquivo_zip) as pacote:
                nomes = [nome.replace("\\", "/") for nome in pacote.namelist()]

        self.assertIn("apps/fiscal/auditoria_importacoes_catalogo_teste.py", nomes)
        self.assertNotIn("apps/fiscal/test_support_identidades_fiscais.py", nomes)
        self.assertNotIn("apps/fiscal/test_catalogo_identidades_fiscais.py", nomes)
        testes_python = []
        for nome in nomes:
            partes = nome.casefold().split("/")
            base = partes[-1]
            if nome.casefold().endswith(".py") and (
                base == "tests.py" or base.startswith("test_") or "tests" in partes
            ):
                testes_python.append(nome)
        self.assertEqual(testes_python, [])


class ComandoAuditoriaImportacoesCatalogoTesteTests(TestCase):
    def test_comando_conforme_nao_consulta_banco(self):
        saida = io.StringIO()
        with CaptureQueriesContext(connection) as consultas:
            call_command("auditar_importacoes_catalogo_teste", stdout=saida)
        resultado = json.loads(saida.getvalue())
        self.assertTrue(resultado["conforme"])
        self.assertEqual(len(consultas), 0)

    def test_comando_recusa_runtime_invalido(self):
        with TemporaryDirectory() as temporario:
            raiz = Path(temporario)
            caminho = raiz / "apps/runtime.py"
            caminho.parent.mkdir(parents=True)
            caminho.write_text(
                "import apps.fiscal.test_support_identidades_fiscais\n", encoding="utf-8"
            )
            saida = io.StringIO()
            with self.assertRaisesMessage(
                CommandError, "IMPORTACAO_CATALOGO_TESTE_FORA_DE_ARQUIVO_DE_TESTE"
            ):
                call_command(
                    "auditar_importacoes_catalogo_teste",
                    "--base-dir", str(raiz), stdout=saida,
                )
        resultado = json.loads(saida.getvalue())
        self.assertFalse(resultado["conforme"])
        self.assertEqual(resultado["resumo"]["importacoes_runtime_bloqueadas"], 1)
