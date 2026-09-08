import hashlib
import json
import tempfile
import zipfile
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from io import BytesIO, StringIO
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase

from .dossie_piloto import CONTRATO_DOSSIE_PILOTO, gerar_dossie_piloto
from .verificador_artefatos_piloto import (
    calcular_sha256_artefato,
    verificar_integridade_artefatos_piloto,
)
from .verificador_dossie_piloto import (
    verificar_dossie_piloto,
    verificar_dossie_piloto_upload,
)


class DossiePilotoTests(SimpleTestCase):
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
        self.verificacao = verificar_integridade_artefatos_piloto(
            ficha=self.ficha,
            relatorio=self.relatorio,
            momento=gerado_em + timedelta(minutes=10),
        )

    def test_gera_zip_com_manifesto_e_hashes_dos_tres_arquivos(self):
        conteudo, manifesto = gerar_dossie_piloto(
            ficha=self.ficha,
            relatorio=self.relatorio,
            verificacao=self.verificacao,
            momento=datetime(2026, 9, 8, 12, 15, tzinfo=timezone.utc),
        )
        self.assertEqual(manifesto["contrato"], CONTRATO_DOSSIE_PILOTO)
        self.assertTrue(manifesto["integridade_confirmada"])
        self.assertFalse(manifesto["registra_aceite"])
        self.assertFalse(manifesto["persiste_dossie"])
        self.assertFalse(manifesto["assinatura_digital"])
        self.assertEqual(
            manifesto["conteudo_sha256"], calcular_sha256_artefato(manifesto)
        )

        with zipfile.ZipFile(BytesIO(conteudo)) as pacote:
            self.assertEqual(
                set(pacote.namelist()),
                {
                    "ficha.json",
                    "relatorio.json",
                    "verificacao_integridade.json",
                    "manifesto.json",
                },
            )
            self.assertTrue(all("/" not in nome for nome in pacote.namelist()))
            self.assertEqual(json.loads(pacote.read("ficha.json")), self.ficha)
            self.assertEqual(json.loads(pacote.read("manifesto.json")), manifesto)
            for arquivo in manifesto["arquivos"]:
                bytes_arquivo = pacote.read(arquivo["nome"])
                self.assertEqual(len(bytes_arquivo), arquivo["bytes"])
                self.assertEqual(
                    hashlib.sha256(bytes_arquivo).hexdigest(),
                    arquivo["sha256_arquivo"],
                )

    def test_recusa_conferencia_adulterada_ou_de_outro_conjunto(self):
        adulterada = deepcopy(self.verificacao)
        adulterada["vinculo"]["produto_id"] = 999
        adulterada["conteudo_sha256"] = calcular_sha256_artefato(adulterada)
        with self.assertRaisesMessage(ValueError, "conjunto íntegro"):
            gerar_dossie_piloto(
                ficha=self.ficha,
                relatorio=self.relatorio,
                verificacao=adulterada,
            )

        outro_relatorio = deepcopy(self.relatorio)
        outro_relatorio["produto_id"] = 999
        outro_relatorio["conteudo_sha256"] = calcular_sha256_artefato(
            outro_relatorio
        )
        with self.assertRaisesMessage(ValueError, "conjunto íntegro"):
            gerar_dossie_piloto(
                ficha=self.ficha,
                relatorio=outro_relatorio,
                verificacao=self.verificacao,
            )

    def test_recusa_estrutura_malformada_sem_expor_erro_interno(self):
        malformada = deepcopy(self.verificacao)
        malformada["artefatos"] = []
        malformada["conteudo_sha256"] = calcular_sha256_artefato(malformada)
        with self.assertRaisesMessage(ValueError, "conjunto íntegro"):
            gerar_dossie_piloto(
                ficha=self.ficha,
                relatorio=self.relatorio,
                verificacao=malformada,
            )
        hash_invalido = deepcopy(self.verificacao)
        hash_invalido["conteudo_sha256"] = "á" * 64
        with self.assertRaisesMessage(ValueError, "conjunto íntegro"):
            gerar_dossie_piloto(
                ficha=self.ficha,
                relatorio=self.relatorio,
                verificacao=hash_invalido,
            )

    def test_verificador_offline_confere_zip_sem_extrair_ou_expor_caminho(self):
        conteudo, _ = gerar_dossie_piloto(
            ficha=self.ficha,
            relatorio=self.relatorio,
            verificacao=self.verificacao,
        )
        with tempfile.TemporaryDirectory() as diretorio:
            caminho = Path(diretorio) / "dossie.zip"
            caminho.write_bytes(conteudo)
            antes = {item.name for item in Path(diretorio).iterdir()}
            resultado = verificar_dossie_piloto(caminho)
            depois = {item.name for item in Path(diretorio).iterdir()}

        self.assertTrue(resultado["integridade_confirmada"])
        self.assertEqual(resultado["impedimentos"], [])
        self.assertEqual(antes, depois)
        self.assertFalse(resultado["extrai_arquivos"])
        self.assertFalse(resultado["consulta_banco"])
        self.assertFalse(resultado["caminho_incluido_resultado"])
        self.assertNotIn("Operador Piloto", json.dumps(resultado))
        self.assertNotIn(str(caminho), json.dumps(resultado))

    def test_verificador_offline_detecta_arquivo_interno_adulterado(self):
        conteudo, _ = gerar_dossie_piloto(
            ficha=self.ficha,
            relatorio=self.relatorio,
            verificacao=self.verificacao,
        )
        with zipfile.ZipFile(BytesIO(conteudo)) as original:
            entradas = {nome: original.read(nome) for nome in original.namelist()}
        ficha = json.loads(entradas["ficha.json"])
        ficha["produto_id"] = 999
        entradas["ficha.json"] = json.dumps(ficha).encode()
        adulterado = BytesIO()
        with zipfile.ZipFile(adulterado, "w", zipfile.ZIP_DEFLATED) as pacote:
            for nome, bytes_entrada in entradas.items():
                pacote.writestr(nome, bytes_entrada)

        with tempfile.TemporaryDirectory() as diretorio:
            caminho = Path(diretorio) / "adulterado.zip"
            caminho.write_bytes(adulterado.getvalue())
            resultado = verificar_dossie_piloto(caminho)
        self.assertFalse(resultado["integridade_confirmada"])
        self.assertFalse(resultado["verificacoes"]["conjunto_coerente"])
        self.assertFalse(
            resultado["verificacoes"]["manifesto_corresponde_conteudo"]
        )

    def test_verificador_offline_recusa_entrada_extra_e_duplicada(self):
        conteudo, _ = gerar_dossie_piloto(
            ficha=self.ficha,
            relatorio=self.relatorio,
            verificacao=self.verificacao,
        )
        with zipfile.ZipFile(BytesIO(conteudo)) as original:
            entradas = [(nome, original.read(nome)) for nome in original.namelist()]
        for nome_teste, extra_nome, extra_conteudo in (
            ("extra.zip", "pasta/extra.txt", b"indevido"),
            ("duplicado.zip", "ficha.json", entradas[0][1]),
        ):
            saida = BytesIO()
            with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as pacote:
                for nome, bytes_entrada in entradas:
                    pacote.writestr(nome, bytes_entrada)
                pacote.writestr(extra_nome, extra_conteudo)
            with tempfile.TemporaryDirectory() as diretorio:
                caminho = Path(diretorio) / nome_teste
                caminho.write_bytes(saida.getvalue())
                resultado = verificar_dossie_piloto(caminho)
            self.assertFalse(resultado["integridade_confirmada"])
            self.assertFalse(resultado["verificacoes"]["estrutura_exata"])

    def test_comando_offline_aprova_valido_e_modo_estrito_recusa_zip_invalido(self):
        conteudo, _ = gerar_dossie_piloto(
            ficha=self.ficha,
            relatorio=self.relatorio,
            verificacao=self.verificacao,
        )
        with tempfile.TemporaryDirectory() as diretorio:
            valido = Path(diretorio) / "valido.zip"
            invalido = Path(diretorio) / "invalido.zip"
            valido.write_bytes(conteudo)
            invalido.write_bytes(b"nao e um zip")
            saida = StringIO()
            call_command(
                "verificar_dossie_piloto",
                dossie=str(valido),
                estrito=True,
                stdout=saida,
            )
            self.assertTrue(json.loads(saida.getvalue())["integridade_confirmada"])
            with self.assertRaisesMessage(CommandError, "foi reprovada"):
                call_command(
                    "verificar_dossie_piloto",
                    dossie=str(invalido),
                    estrito=True,
                    stdout=StringIO(),
                )

    def test_upload_em_memoria_confere_zip_e_recusa_extensao_invalida(self):
        conteudo, _ = gerar_dossie_piloto(
            ficha=self.ficha,
            relatorio=self.relatorio,
            verificacao=self.verificacao,
        )
        resultado = verificar_dossie_piloto_upload(
            SimpleUploadedFile(
                "dossie.zip", conteudo, content_type="application/zip"
            )
        )
        self.assertTrue(resultado["integridade_confirmada"])
        with self.assertRaisesMessage(ValueError, "extensão ZIP"):
            verificar_dossie_piloto_upload(
                SimpleUploadedFile(
                    "dossie.txt", conteudo, content_type="text/plain"
                )
            )
