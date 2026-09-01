import hashlib
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from .cest import ler_catalogo_cest_html, validar_cest
from .models import CatalogoCEST, ItemCEST


HTML_CEST_TESTE = """<!doctype html>
<html><head><meta charset="utf-8"></head><body>
<table>
<tr><th>ITEM</th><th>NOME DO SEGMENTO</th><th>CÓDIGO DO SEGMENTO</th></tr>
<tr><td>01</td><td>Autopeças</td><td>01</td></tr>
<tr><td>17</td><td>Produtos alimentícios</td><td>17</td></tr>
<tr><td>28</td><td>Venda porta a porta</td><td>28</td></tr>
</table>
<table>
<tr><th>ITEM</th><th>CEST</th><th>NCM/SH</th><th>DESCRIÇÃO</th></tr>
<tr><td>1.0</td><td>17.001.00</td><td>1704.90.10</td><td>Chocolate branco vigente</td></tr>
<tr><td>1.0</td><td>17.001.00</td><td>1704.90.90</td><td>Redação histórica</td></tr>
<tr><td>2.0</td><td>17.002.00</td><td>1806</td><td>REVOGADO</td></tr>
<tr><td>2.0</td><td>17.002.00</td><td>1806</td><td>Redação anterior revogada</td></tr>
<tr><td>55.0</td><td>28.055.00</td><td>Capítulo 33</td><td>Cosméticos porta a porta</td></tr>
<tr><td>999.0</td><td>01.999.00</td><td></td><td>Outras peças conforme descrição</td></tr>
</table>
</body></html>"""


def _gravar_html(caminho):
    caminho.write_text(HTML_CEST_TESTE, encoding="utf-8")


class CatalogoCESTTests(TestCase):
    def test_parser_seleciona_primeira_redacao_e_ignora_revogado(self):
        with tempfile.TemporaryDirectory() as diretorio:
            caminho = Path(diretorio) / "cest.html"
            _gravar_html(caminho)
            resultado = ler_catalogo_cest_html(caminho, "2026-08-31")

        self.assertEqual(resultado["referencia_em"].isoformat(), "2026-08-31")
        self.assertEqual(resultado["quantidade_linhas_origem"], 6)
        self.assertEqual([item["codigo"] for item in resultado["itens"]], ["1700100", "2805500", "0199900"])
        self.assertEqual(resultado["itens"][0]["ncm_prefixos"], ["17049010"])
        self.assertEqual(resultado["itens"][1]["ncm_prefixos"], ["33"])
        self.assertEqual(resultado["itens"][2]["ncm_prefixos"], [])
        self.assertNotIn("Redação histórica", [item["descricao"] for item in resultado["itens"]])

    def test_importacao_exige_hash_quantidade_e_ativa(self):
        with tempfile.TemporaryDirectory() as diretorio:
            caminho = Path(diretorio) / "cest.html"
            _gravar_html(caminho)
            sha256 = hashlib.sha256(caminho.read_bytes()).hexdigest()
            call_command(
                "importar_catalogo_cest",
                str(caminho),
                versao="CONFAZ-2026-08-31",
                sha256_esperado=sha256,
                referencia_esperada="2026-08-31",
                quantidade_esperada=3,
                ativar=True,
                verbosity=0,
            )

        catalogo = CatalogoCEST.objects.get()
        self.assertTrue(catalogo.ativo)
        self.assertEqual(catalogo.quantidade_itens, 3)
        self.assertEqual(ItemCEST.objects.count(), 3)
        self.assertIsNone(validar_cest("17.001.00", "17049010"))
        self.assertIn("não é compatível", validar_cest("17.001.00", "18069000"))
        self.assertIsNone(validar_cest("28.055.00", "33030010"))
        self.assertIsNone(validar_cest("01.999.00", "87089990"))
        self.assertIn("não consta", validar_cest("17.999.00", "17049010"))

    def test_hash_divergente_nao_importa(self):
        with tempfile.TemporaryDirectory() as diretorio:
            caminho = Path(diretorio) / "cest.html"
            _gravar_html(caminho)
            with self.assertRaisesMessage(CommandError, "SHA-256 divergente"):
                call_command(
                    "importar_catalogo_cest",
                    str(caminho),
                    versao="invalido",
                    sha256_esperado="0" * 64,
                    referencia_esperada="2026-08-31",
                    quantidade_esperada=3,
                    verbosity=0,
                )
        self.assertFalse(CatalogoCEST.objects.exists())

    def test_sem_catalogo_preserva_compatibilidade(self):
        self.assertIsNone(validar_cest("17.001.00", "17049010"))
        self.assertEqual(validar_cest("17001", "17049010"), "CEST com 7 dígitos")