import hashlib
import json
import zipfile
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from io import BytesIO

from django.test import SimpleTestCase

from .dossie_piloto import CONTRATO_DOSSIE_PILOTO, gerar_dossie_piloto
from .verificador_artefatos_piloto import (
    calcular_sha256_artefato,
    verificar_integridade_artefatos_piloto,
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
