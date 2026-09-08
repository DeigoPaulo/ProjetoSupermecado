import json
import tempfile
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase

from .verificador_artefatos_piloto import (
    LIMITE_ARQUIVO_JSON,
    calcular_sha256_artefato,
    carregar_artefato_upload,
    verificar_integridade_artefatos_piloto,
)


class VerificadorArtefatosPilotoTests(SimpleTestCase):
    def setUp(self):
        gerado_em = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
        objetos = {
            "entrada_id": 11,
            "venda_id": 12,
            "perda_id": 13,
            "inventario_id": 14,
            "fechamento_id": 15,
        }
        self.ficha = {
            "contrato": "inventory_pilot_execution_sheet_v2",
            "gerado_em": gerado_em.isoformat(),
            "objetos_selecionados_manualmente": objetos,
            "filial_id": 2,
            "produto_id": 3,
            "responsaveis": {
                "execucao": "Operador Piloto",
                "conferencia": "Conferente Piloto",
                "persistidos_no_banco": False,
            },
            "apta_para_verificacao_final": True,
            "aprovacao_automatica": False,
            "registra_aceite": False,
            "persiste_ficha": False,
            "somente_leitura": True,
            "comunicacao_externa": False,
        }
        self.ficha["conteudo_sha256"] = calcular_sha256_artefato(self.ficha)
        self.relatorio = {
            "contrato": "inventory_pilot_end_to_end_evidence_v3",
            "gerado_em": (gerado_em + timedelta(minutes=5)).isoformat(),
            "objetos": objetos,
            "filial_id": 2,
            "produto_id": 3,
            "valida": True,
            "somente_leitura": True,
            "comunicacao_externa": False,
        }
        self.relatorio["conteudo_sha256"] = calcular_sha256_artefato(
            self.relatorio
        )

    def test_confirma_integridade_e_vinculo_sem_repetir_responsaveis(self):
        resultado = verificar_integridade_artefatos_piloto(
            ficha=self.ficha,
            relatorio=self.relatorio,
            momento=datetime(2026, 9, 8, 12, 10, tzinfo=timezone.utc),
        )
        self.assertTrue(resultado["integridade_confirmada"])
        self.assertTrue(resultado["vinculo"]["confirmado"])
        self.assertEqual(resultado["impedimentos"], [])
        self.assertFalse(resultado["consulta_banco"])
        self.assertFalse(resultado["comunicacao_externa"])
        self.assertFalse(resultado["persiste_resultado"])
        self.assertNotIn("Operador Piloto", json.dumps(resultado))
        self.assertEqual(len(resultado["conteudo_sha256"]), 64)

    def test_detecta_adulteracao_e_relatorio_de_outros_objetos(self):
        ficha_adulterada = deepcopy(self.ficha)
        ficha_adulterada["produto_id"] = 99
        resultado_adulterado = verificar_integridade_artefatos_piloto(
            ficha=ficha_adulterada, relatorio=self.relatorio
        )
        self.assertFalse(resultado_adulterado["integridade_confirmada"])
        self.assertFalse(
            resultado_adulterado["verificacoes"]["sha256_ficha_integro"]
        )

        relatorio_divergente = deepcopy(self.relatorio)
        relatorio_divergente["objetos"]["venda_id"] = 999
        relatorio_divergente["conteudo_sha256"] = calcular_sha256_artefato(
            relatorio_divergente
        )
        resultado_divergente = verificar_integridade_artefatos_piloto(
            ficha=self.ficha, relatorio=relatorio_divergente
        )
        self.assertTrue(
            resultado_divergente["verificacoes"]["sha256_relatorio_integro"]
        )
        self.assertFalse(resultado_divergente["verificacoes"]["mesmos_objetos"])
        self.assertFalse(resultado_divergente["vinculo"]["confirmado"])

    def test_comando_confere_arquivos_locais_e_modo_estrito_reprova_alteracao(self):
        with tempfile.TemporaryDirectory() as diretorio:
            ficha_path = Path(diretorio) / "ficha.json"
            relatorio_path = Path(diretorio) / "relatorio.json"
            ficha_path.write_text(
                json.dumps(self.ficha, ensure_ascii=False), encoding="utf-8-sig"
            )
            relatorio_path.write_text(
                json.dumps(self.relatorio, ensure_ascii=False), encoding="utf-8"
            )
            saida = StringIO()
            call_command(
                "verificar_artefatos_piloto",
                ficha=str(ficha_path),
                relatorio=str(relatorio_path),
                estrito=True,
                stdout=saida,
            )
            self.assertTrue(json.loads(saida.getvalue())["integridade_confirmada"])

            ficha_adulterada = deepcopy(self.ficha)
            ficha_adulterada["observacao"] = "alteração posterior"
            ficha_path.write_text(
                json.dumps(ficha_adulterada, ensure_ascii=False), encoding="utf-8"
            )
            with self.assertRaisesMessage(CommandError, "foi reprovado"):
                call_command(
                    "verificar_artefatos_piloto",
                    ficha=str(ficha_path),
                    relatorio=str(relatorio_path),
                    estrito=True,
                    stdout=StringIO(),
                )

    def test_upload_em_memoria_recusa_extensao_e_tamanho_invalidos(self):
        valido = SimpleUploadedFile(
            "ficha.json", json.dumps(self.ficha).encode(), content_type="application/json"
        )
        self.assertEqual(carregar_artefato_upload(valido)["contrato"], self.ficha["contrato"])
        with self.assertRaisesMessage(ValueError, "extensão JSON"):
            carregar_artefato_upload(
                SimpleUploadedFile("ficha.txt", b"{}", content_type="text/plain")
            )
        with self.assertRaisesMessage(ValueError, "excede"):
            carregar_artefato_upload(
                SimpleUploadedFile(
                    "grande.json",
                    b"x" * (LIMITE_ARQUIVO_JSON + 1),
                    content_type="application/json",
                )
            )
