import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.db import connection
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext

from .inventario_estatico_identidades_fiscais import (
    classificar_candidato,
    inventariar_identidades_fiscais_estaticas,
)


class ClassificacaoCandidatosFiscaisTests(SimpleTestCase):
    def test_classifica_finalidades_sem_depender_do_valor(self):
        casos = [
            ("apps/empresas/services_lookup.py", '"mascara": "00.000.000/0000-00"', "CNPJ_MASCARADO", "MASCARA_VISUAL"),
            ("apps/configuracoes/management/commands/popular_demo.py", 'DEMO_CNPJ = "99.999.999/0001-99"', "CNPJ_MASCARADO", "DEMONSTRACAO_LOCAL"),
            ("apps/fiscal/test_x.py", 'chave = "52260812345678000199550010000001231000001234"', "CHAVE_44", "CHAVE_FISCAL_TESTE"),
            ("apps/fiscal/test_x.py", '<emit><CNPJ>12345678000199</CNPJ></emit>', "BLOCO_14", "XML_FISCAL_TESTE"),
            ("apps/fiscal/test_x.py", 'cnpj="11.111.111/0001-11"', "CNPJ_MASCARADO", "IDENTIDADE_MODELO_TESTE"),
            ("docs/evidencias/exemplo/README.md", "exemplo oficial 12.ABC.345/01DE-35", "CNPJ_MASCARADO", "EXEMPLO_NORMATIVO_DOCUMENTADO"),
        ]
        for caminho, linha, tipo, esperado in casos:
            with self.subTest(caminho=caminho, esperado=esperado):
                self.assertEqual(classificar_candidato(caminho, linha, tipo), esperado)

    def test_categoria_desconhecida_permanece_para_revisao(self):
        self.assertEqual(
            classificar_candidato("apps/outro/modulo.py", 'valor = "12345678000190"', "BLOCO_14"),
            "OUTRO_RUNTIME_REVISAR",
        )

    def test_papeis_conhecidos_de_testes_nao_ficam_ambiguos(self):
        self.assertEqual(
            classificar_candidato(
                "apps/fiscal/test_portao_leitura_dupla_cnpj.py",
                'self.registro(1, "04.252.011/0001-10")',
                "CNPJ_MASCARADO",
            ),
            "VALIDACAO_DOCUMENTO_TESTE",
        )
        self.assertEqual(
            classificar_candidato(
                "apps/empresas/tests.py", '"44.444.444/0001-44": {', "CNPJ_MASCARADO"
            ),
            "IDENTIDADE_MODELO_TESTE",
        )
        self.assertEqual(
            classificar_candidato(
                "apps/compras/tests.py", 'destinatario = "98765432000110"', "BLOCO_14"
            ),
            "IDENTIDADE_MODELO_TESTE",
        )

    def test_inventario_tem_resultado_deterministico_e_protegido(self):
        with TemporaryDirectory() as temporario:
            raiz = Path(temporario)
            (raiz / "apps/fiscal").mkdir(parents=True)
            (raiz / "docs").mkdir()
            (raiz / "apps/fiscal/test_amostra.py").write_text(
                'cnpj = "11.111.111/0001-11"\n'
                'xml = "<CNPJ>12345678000199</CNPJ>"\n'
                'chave = "52260812345678000199550010000001231000001234"\n',
                encoding="utf-8",
            )
            (raiz / "docs/manual.md").write_text(
                'SINCRONIZACAO_TOKENS_EMPRESA_JSON={"00.000.000/0001-00":"TOKEN"}\n',
                encoding="utf-8",
            )
            primeiro = inventariar_identidades_fiscais_estaticas(raiz, incluir_ocorrencias=True)
            segundo = inventariar_identidades_fiscais_estaticas(raiz, incluir_ocorrencias=True)
        self.assertEqual(primeiro, segundo)
        self.assertEqual(primeiro["resumo"]["total_candidatos"], 4)
        self.assertEqual(primeiro["resumo"]["por_tipo"]["CHAVE_44"], 1)
        self.assertEqual(len(primeiro["ocorrencias"]), 4)
        serializado = json.dumps(primeiro)
        for valor in (
            "11.111.111/0001-11", "12345678000199",
            "52260812345678000199550010000001231000001234", "00.000.000/0001-00",
        ):
            self.assertNotIn(valor, serializado)
        self.assertTrue(all(not item["valor_exposto"] for item in primeiro["ocorrencias"]))
        self.assertTrue(all(len(item["impressao_digital"]) == 16 for item in primeiro["ocorrencias"]))

    def test_resumo_omite_ocorrencias_por_padrao(self):
        with TemporaryDirectory() as temporario:
            raiz = Path(temporario)
            (raiz / "apps").mkdir()
            (raiz / "apps/amostra.py").write_text('cnpj="12345678000199"', encoding="utf-8")
            resultado = inventariar_identidades_fiscais_estaticas(raiz)
        self.assertNotIn("ocorrencias", resultado)
        self.assertTrue(resultado["seguranca"]["somente_leitura_de_fontes"])
        self.assertFalse(resultado["seguranca"]["consulta_banco"])
        self.assertFalse(resultado["seguranca"]["altera_arquivos"])
        self.assertFalse(resultado["seguranca"]["reescreve_fixtures"])
        self.assertFalse(resultado["seguranca"]["libera_emissao"])

    def test_bloco_de_14_sem_contexto_fiscal_nao_vira_candidato(self):
        with TemporaryDirectory() as temporario:
            raiz = Path(temporario)
            (raiz / "apps").mkdir()
            (raiz / "apps/amostra.py").write_text(
                'codigo_barras = "17891234567897"\ntexto = "ABCDEFGHIJKLMN"\n',
                encoding="utf-8",
            )
            resultado = inventariar_identidades_fiscais_estaticas(raiz)
        self.assertEqual(resultado["resumo"]["total_candidatos"], 0)

    def test_cnpj_alfanumerico_mantem_dois_digitos_finais_obrigatorios(self):
        with TemporaryDirectory() as temporario:
            raiz = Path(temporario)
            (raiz / "apps").mkdir()
            (raiz / "apps/amostra.py").write_text(
                'cnpj_invalido = "ABCDEFGHIJKLMN"\ncnpj_valido = "12ABC34501DE35"\n',
                encoding="utf-8",
            )
            resultado = inventariar_identidades_fiscais_estaticas(
                raiz, incluir_ocorrencias=True
            )
        self.assertEqual(resultado["resumo"]["total_candidatos"], 1)
        self.assertEqual(resultado["ocorrencias"][0]["tipo"], "BLOCO_14")


class ComandoInventarioEstaticoTests(TestCase):
    def test_comando_resumo_nao_consulta_banco_nem_expoe_valor(self):
        saida = io.StringIO()
        with CaptureQueriesContext(connection) as consultas:
            call_command("inventariar_identidades_fiscais_estaticas", stdout=saida)
        resultado = json.loads(saida.getvalue())
        self.assertEqual(resultado["contrato"], "static_fiscal_identity_candidate_inventory_v1")
        self.assertEqual(len(consultas), 0)
        self.assertNotIn("ocorrencias", resultado)
        self.assertNotIn("99.999.999/0001-99", saida.getvalue())

    def test_comando_detalhado_mantem_valores_protegidos(self):
        saida = io.StringIO()
        call_command("inventariar_identidades_fiscais_estaticas", "--detalhes", stdout=saida)
        resultado = json.loads(saida.getvalue())
        self.assertTrue(resultado["ocorrencias"])
        self.assertTrue(all(not item["valor_exposto"] for item in resultado["ocorrencias"]))
        self.assertNotIn("12.ABC.345/01DE-35", saida.getvalue())
