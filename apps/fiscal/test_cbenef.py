import hashlib
import tempfile
import zipfile
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from xml.etree import ElementTree as ET

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from .cbenef import ler_catalogo_cbenef_go_docx, validar_cbenef_go
from .models import CatalogoBeneficioFiscal
from .perfis_uf import pendencias_produto_por_uf


WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _criar_docx_teste(caminho, linhas):
    ET.register_namespace("w", WORD_NS)
    documento = ET.Element(f"{{{WORD_NS}}}document")
    corpo = ET.SubElement(documento, f"{{{WORD_NS}}}body")
    tabela = ET.SubElement(corpo, f"{{{WORD_NS}}}tbl")
    for valores in linhas:
        linha = ET.SubElement(tabela, f"{{{WORD_NS}}}tr")
        for valor in valores:
            celula = ET.SubElement(linha, f"{{{WORD_NS}}}tc")
            paragrafo = ET.SubElement(celula, f"{{{WORD_NS}}}p")
            trecho = ET.SubElement(paragrafo, f"{{{WORD_NS}}}r")
            texto = ET.SubElement(trecho, f"{{{WORD_NS}}}t")
            texto.text = valor
    with zipfile.ZipFile(caminho, "w") as pacote:
        pacote.writestr("word/document.xml", ET.tostring(documento, encoding="utf-8"))


class CatalogoCBenefGoTests(TestCase):
    def _arquivo_oficial_sintetico(self, diretorio):
        caminho = Path(diretorio) / "cbenef-go.docx"
        _criar_docx_teste(
            caminho,
            [
                ["CÓDIGO", "CST 20", "CST 40", "DISPOSITIVO LEGAL", "DESCRIÇÃO", "OBSERVAÇÃO"],
                ["GO821019", "SIM", "", "RCTE, Anexo IX", "Cesta básica", ""],
                ["GO811003", "", "SIM", "RCTE", "Isenção", ""],
            ],
        )
        return caminho

    def test_importacao_exige_hash_e_cria_catalogo_ativo_com_cst(self):
        with tempfile.TemporaryDirectory() as diretorio:
            caminho = self._arquivo_oficial_sintetico(diretorio)
            sha256 = hashlib.sha256(caminho.read_bytes()).hexdigest()
            call_command(
                "importar_catalogo_cbenef_go",
                str(caminho),
                versao="teste-2026",
                fonte_url="https://goias.gov.br/economia/codigos-de-beneficios-fiscais/",
                sha256_esperado=sha256,
                vigencia_inicio="2023-07-01",
                quantidade_esperada=2,
                ativar=True,
                verbosity=0,
            )

        catalogo = CatalogoBeneficioFiscal.objects.get()
        self.assertTrue(catalogo.ativo)
        self.assertEqual(catalogo.quantidade_itens, 2)
        self.assertIsNone(validar_cbenef_go("GO821019", "20"))
        self.assertIn("incompatível com CST ICMS 40", validar_cbenef_go("GO821019", "40"))

    def test_hash_divergente_nao_importa(self):
        with tempfile.TemporaryDirectory() as diretorio:
            caminho = self._arquivo_oficial_sintetico(diretorio)
            with self.assertRaisesMessage(CommandError, "SHA-256 divergente"):
                call_command(
                    "importar_catalogo_cbenef_go",
                    str(caminho),
                    versao="teste",
                    fonte_url="https://goias.gov.br/economia/codigos-de-beneficios-fiscais/",
                    sha256_esperado="0" * 64,
                    vigencia_inicio="2023-07-01",
                    verbosity=0,
                )
        self.assertFalse(CatalogoBeneficioFiscal.objects.exists())

    def test_parser_consolida_ultima_redacao_e_informa_duplicidade(self):
        with tempfile.TemporaryDirectory() as diretorio:
            caminho = Path(diretorio) / "duplicado.docx"
            _criar_docx_teste(
                caminho,
                [
                    ["CÓDIGO", "CST 20", "CST 90", "DISPOSITIVO", "DESCRIÇÃO", "OBSERVAÇÃO"],
                    ["SEM CBENEF", "", "SIM", "", "Redação anterior", ""],
                    ["SEM CBENEF", "", "SIM", "", "Redação vigente", ""],
                ],
            )
            itens, duplicados = ler_catalogo_cbenef_go_docx(caminho)

        self.assertEqual(len(itens), 1)
        self.assertEqual(itens[0]["descricao"], "Redação vigente")
        self.assertEqual(duplicados, ["SEM CBENEF"])

    def test_sem_catalogo_bloqueia_codigo_e_simples_nao_exige_por_reducao(self):
        self.assertIn(
            "não instalado",
            validar_cbenef_go("GO821019", "20"),
        )
        produto = SimpleNamespace(
            codigo_beneficio_fiscal="",
            reducao_base_icms=Decimal("10.00"),
            cst_icms="20",
        )
        self.assertEqual(
            pendencias_produto_por_uf(produto, ["GO"], ["1"]),
            [],
        )
