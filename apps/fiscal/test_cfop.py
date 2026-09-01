import hashlib
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from .cfop import ler_catalogo_cfop_html, validar_cfop
from .models import CatalogoCFOP, ItemCFOP


HTML_CFOP_TESTE = """<!doctype html>
<html><head><meta charset="utf-8"></head><body><div id="content-core">
<p>1.100 - COMPRAS PARA COMERCIALIZAÇÃO</p>
<p>1.102 - Compra para comercialização</p>
<p>Classificam-se neste código as compras de mercadorias para comercialização.</p>
<p>2.102 – Compra para comercialização de outra UF</p>
<p>Classificam-se neste código as compras interestaduais para comercialização.</p>
<p>5.100 - VENDAS DE PRODUÇÃO OU DE TERCEIROS</p>
<p>5.102 - Venda de mercadoria adquirida ou recebida de terceiros</p>
<p>Classificam-se neste código as vendas internas de mercadorias de terceiros.</p>
<p>6.102 - Venda interestadual de mercadoria adquirida de terceiros</p>
<p>Classificam-se neste código as vendas interestaduais de mercadorias de terceiros.</p>
<p>7.102 - Venda de mercadoria adquirida de terceiros para o exterior</p>
<p>Classificam-se neste código as vendas de mercadorias de terceiros destinadas ao exterior.</p>
</div></body></html>"""


def _gravar_html(caminho):
    caminho.write_text(HTML_CFOP_TESTE, encoding="utf-8")


class CatalogoCFOPTests(TestCase):
    def test_parser_separa_agrupadores_e_deriva_direcao_alcance(self):
        with tempfile.TemporaryDirectory() as diretorio:
            caminho = Path(diretorio) / "cfop.html"
            _gravar_html(caminho)
            resultado = ler_catalogo_cfop_html(caminho, "2026-08-31")

        self.assertEqual(resultado["quantidade_linhas_origem"], 7)
        self.assertEqual(resultado["quantidade_agrupadores"], 2)
        self.assertEqual(len(resultado["itens"]), 5)
        interno = next(item for item in resultado["itens"] if item["codigo"] == "5102")
        self.assertEqual(interno["direcao"], "SAIDA")
        self.assertEqual(interno["alcance"], "INTERNA")
        self.assertTrue(interno["nota_explicativa"].startswith("Classificam-se"))

    def test_importacao_e_validacoes_objetivas(self):
        with tempfile.TemporaryDirectory() as diretorio:
            caminho = Path(diretorio) / "cfop.html"
            _gravar_html(caminho)
            sha256 = hashlib.sha256(caminho.read_bytes()).hexdigest()
            call_command(
                "importar_catalogo_cfop",
                str(caminho),
                versao="CONFAZ-2026-08-31",
                sha256_esperado=sha256,
                referencia_esperada="2026-08-31",
                quantidade_esperada=5,
                ativar=True,
                verbosity=0,
            )

        self.assertTrue(CatalogoCFOP.objects.get().ativo)
        self.assertEqual(ItemCFOP.objects.count(), 5)
        self.assertIsNone(validar_cfop("5.102", direcao="SAIDA", modelo="NFCE"))
        self.assertIn("saída interna", validar_cfop("6102", direcao="SAIDA", modelo="NFCE"))
        self.assertIn("não de saída", validar_cfop("1102", direcao="SAIDA", modelo="NFE"))
        self.assertIsNone(validar_cfop("6102", direcao="SAIDA", modelo="NFE"))
        self.assertIn("não consta", validar_cfop("5949", direcao="SAIDA"))

    def test_hash_divergente_nao_importa(self):
        with tempfile.TemporaryDirectory() as diretorio:
            caminho = Path(diretorio) / "cfop.html"
            _gravar_html(caminho)
            with self.assertRaisesMessage(CommandError, "SHA-256 divergente"):
                call_command(
                    "importar_catalogo_cfop",
                    str(caminho),
                    versao="invalido",
                    sha256_esperado="0" * 64,
                    referencia_esperada="2026-08-31",
                    quantidade_esperada=5,
                    verbosity=0,
                )
        self.assertFalse(CatalogoCFOP.objects.exists())

    def test_sem_catalogo_valida_formato_e_bloqueia_agrupador(self):
        self.assertIsNone(validar_cfop("5102", direcao="SAIDA", modelo="NFCE"))
        self.assertEqual(validar_cfop("5100"), "CFOP 5100 é agrupador e não pode ser usado na operação")
        self.assertEqual(validar_cfop("102"), "CFOP válido com 4 dígitos")