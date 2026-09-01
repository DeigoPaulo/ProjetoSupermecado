import hashlib
import json
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from .models import CatalogoNCM, ItemNCM
from .ncm import ler_catalogo_ncm_json, validar_ncm


def _dados_ncm_teste():
    return {
        "Data_Ultima_Atualizacao_NCM": "Vigente em 28/08/2026",
        "Ato": "Resolução Gecex nº 926/2026",
        "Nomenclaturas": [
            {
                "Codigo": "10",
                "Descricao": "Cereais.",
                "Data_Inicio": "01/04/2022",
                "Data_Fim": "31/12/9999",
                "Tipo_Ato_Ini": "Res Gecex",
                "Numero_Ato_Ini": "272",
                "Ano_Ato_Ini": "2021",
            },
            {
                "Codigo": "1006.30.21",
                "Descricao": "Arroz <i>parboilizado</i>",
                "Data_Inicio": "01/04/2022",
                "Data_Fim": "31/12/9999",
                "Tipo_Ato_Ini": "Res Gecex",
                "Numero_Ato_Ini": "272",
                "Ano_Ato_Ini": "2021",
            },
            {
                "Codigo": "1006.30.29",
                "Descricao": "Outros",
                "Data_Inicio": "01/04/2022",
                "Data_Fim": "31/12/9999",
                "Tipo_Ato_Ini": "Res Gecex",
                "Numero_Ato_Ini": "272",
                "Ano_Ato_Ini": "2021",
            },
        ],
    }


def _gravar_json(caminho, dados=None):
    caminho.write_text(
        json.dumps(dados or _dados_ncm_teste(), ensure_ascii=False),
        encoding="utf-8",
    )


class CatalogoNCMTests(TestCase):
    def test_parser_seleciona_so_codigos_finais_e_remove_html(self):
        with tempfile.TemporaryDirectory() as diretorio:
            caminho = Path(diretorio) / "ncm.json"
            _gravar_json(caminho)
            resultado = ler_catalogo_ncm_json(caminho)

        self.assertEqual(resultado["referencia_em"].isoformat(), "2026-08-28")
        self.assertEqual(resultado["ato"], "Resolução Gecex nº 926/2026")
        self.assertEqual(resultado["quantidade_linhas_origem"], 3)
        self.assertEqual([item["codigo"] for item in resultado["itens"]], ["10063021", "10063029"])
        self.assertEqual(resultado["itens"][0]["descricao"], "Arroz parboilizado")

    def test_importacao_exige_hash_referencia_quantidade_e_ativa(self):
        with tempfile.TemporaryDirectory() as diretorio:
            caminho = Path(diretorio) / "ncm.json"
            _gravar_json(caminho)
            sha256 = hashlib.sha256(caminho.read_bytes()).hexdigest()
            call_command(
                "importar_catalogo_ncm",
                str(caminho),
                versao="snapshot-2026-08-28",
                sha256_esperado=sha256,
                referencia_esperada="2026-08-28",
                quantidade_esperada=2,
                ativar=True,
                verbosity=0,
            )

        catalogo = CatalogoNCM.objects.get()
        self.assertTrue(catalogo.ativo)
        self.assertEqual(catalogo.quantidade_itens, 2)
        self.assertEqual(catalogo.quantidade_linhas_origem, 3)
        self.assertEqual(ItemNCM.objects.count(), 2)
        self.assertIsNone(validar_ncm("10063021"))
        self.assertIn("não consta", validar_ncm("99999999"))

    def test_divergencia_de_referencia_nao_importa(self):
        with tempfile.TemporaryDirectory() as diretorio:
            caminho = Path(diretorio) / "ncm.json"
            _gravar_json(caminho)
            sha256 = hashlib.sha256(caminho.read_bytes()).hexdigest()
            with self.assertRaisesMessage(CommandError, "Referência divergente"):
                call_command(
                    "importar_catalogo_ncm",
                    str(caminho),
                    versao="snapshot-invalido",
                    sha256_esperado=sha256,
                    referencia_esperada="2026-08-27",
                    quantidade_esperada=2,
                    verbosity=0,
                )
        self.assertFalse(CatalogoNCM.objects.exists())

    def test_sem_catalogo_preserva_validacao_de_formato(self):
        self.assertIsNone(validar_ncm("10063021"))
        self.assertEqual(validar_ncm("1006"), "NCM com 8 dígitos")

    def test_codigo_fora_da_vigencia_e_bloqueado(self):
        catalogo = CatalogoNCM.objects.create(
            versao="teste",
            referencia_em="2026-08-28",
            ato="Ato teste",
            fonte_nome="Siscomex",
            fonte_url="https://portalunico.siscomex.gov.br/classif/api/publico/nomenclatura/download/json",
            fonte_sha256="a" * 64,
            ativo=True,
            quantidade_itens=1,
            quantidade_linhas_origem=1,
        )
        ItemNCM.objects.create(
            catalogo=catalogo,
            codigo="10063021",
            codigo_formatado="1006.30.21",
            descricao="Arroz",
            vigencia_inicio="2022-04-01",
            vigencia_fim="2025-12-31",
            ato_inicio="Res Gecex 272 2021",
        )

        self.assertIn("não consta", validar_ncm("10063021"))
