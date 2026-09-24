import hashlib
import io
import json
import socket
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.core.management import call_command
from django.test import SimpleTestCase

from .cenarios_tributarios import avaliar_cenario_fiscal_go
from .pre_homologacao_go import (
    BLOQUEADO,
    CONTRATO,
    DEPENDE_DE_HOMOLOGACAO,
    DEPENDE_DE_PARAMETRIZACAO,
    NAO_IMPLEMENTADO,
    STATUS_VALIDOS,
    SUPORTADO,
    consultar_capacidade_piloto_go,
    diagnostico_pre_homologacao_go,
    matriz_capacidades_piloto_go,
)


class PreHomologacaoGoTests(SimpleTestCase):
    def test_identifica_pacote_oficial_arquivado_sem_promover(self):
        resultado = diagnostico_pre_homologacao_go(settings.BASE_DIR)
        xsd = resultado["xsd"]

        self.assertEqual(resultado["contrato"], CONTRATO)
        self.assertEqual(xsd["pacote_atual"]["versao"], "PL_010f_v1.04")
        self.assertEqual(
            xsd["pacote_atual"]["sha256"],
            "b8589490a58a09a993a80e6ac4d7ed10f20892061ecfc56719337098d4b95998",
        )
        self.assertEqual(xsd["comparacao"], "IGUAIS_POR_SHA256")
        self.assertEqual(xsd["operacional_no_repositorio"]["estado"], "NAO_INSTALADO")
        self.assertEqual(xsd["arquivos_afetados"], [])

    def test_diagnostico_e_deterministico_e_nao_altera_pacote(self):
        arquivo = Path(settings.BASE_DIR) / "docs/evidencias/nfe_2026_09_10/schemas_010f.zip"
        antes = hashlib.sha256(arquivo.read_bytes()).hexdigest()

        primeiro = diagnostico_pre_homologacao_go(settings.BASE_DIR)
        segundo = diagnostico_pre_homologacao_go(settings.BASE_DIR)

        self.assertEqual(primeiro, segundo)
        self.assertEqual(antes, hashlib.sha256(arquivo.read_bytes()).hexdigest())
        self.assertEqual(len(primeiro["manifesto_sha256"]), 64)

    def test_diagnostico_nao_abre_rede(self):
        with patch.object(socket, "create_connection", side_effect=AssertionError("rede acionada")):
            resultado = diagnostico_pre_homologacao_go(settings.BASE_DIR)

        self.assertFalse(resultado["politica"]["acessou_rede"])
        self.assertFalse(resultado["politica"]["transmitiu"])
        self.assertFalse(resultado["politica"]["producao_liberada"])

    def test_comando_publica_o_mesmo_manifesto(self):
        saida = io.StringIO()
        call_command("diagnosticar_pre_homologacao_go", stdout=saida)

        publicado = json.loads(saida.getvalue())
        esperado = diagnostico_pre_homologacao_go(settings.BASE_DIR)
        self.assertEqual(publicado, esperado)

    def test_matriz_cobre_recorte_minimo_e_status_validos(self):
        itens = matriz_capacidades_piloto_go()
        por_codigo = {item["codigo"]: item for item in itens}

        self.assertEqual(len(itens), len(por_codigo))
        self.assertTrue(all(item["status"] in STATUS_VALIDOS for item in itens))
        self.assertTrue(all(not item["autoriza_producao"] for item in itens))
        for codigo in {
            "modelo_65_nfce", "modelo_55_nfe", "crt_1_simples", "crt_2_excesso",
            "crt_3_normal", "crt_4_mei", "pis", "cofins", "ipi", "cbenef",
            "pagamento_dinheiro", "pagamento_credito", "pagamento_debito",
            "pagamento_pix", "pagamento_vale_alimentacao", "pagamento_vale_refeicao",
            "pagamento_dividido", "destinatario_nao_identificado", "destinatario_cpf",
            "destinatario_cnpj", "endereco_emitente", "qrcode_nfce",
            "contingencia_nfce", "sefaz_direta_go", "focus", "ibs_cbs",
        }:
            self.assertIn(codigo, por_codigo)

    def test_estados_refletem_limites_comprovados(self):
        itens = {item["codigo"]: item for item in matriz_capacidades_piloto_go()}

        self.assertEqual(itens["pagamento_dinheiro"]["status"], SUPORTADO)
        self.assertEqual(itens["pis"]["status"], DEPENDE_DE_PARAMETRIZACAO)
        self.assertEqual(itens["pagamento_pix"]["status"], DEPENDE_DE_HOMOLOGACAO)
        self.assertEqual(itens["xsd_operacional"]["status"], BLOQUEADO)
        self.assertEqual(itens["ibs_cbs"]["status"], NAO_IMPLEMENTADO)

    def test_combinacao_desconhecida_falha_fechado(self):
        resultado = consultar_capacidade_piloto_go("tributo-futuro-nao-catalogado")

        self.assertEqual(resultado["status"], BLOQUEADO)
        self.assertEqual(resultado["motivo"], "CENARIO_NAO_CATALOGADO")
        self.assertFalse(resultado["autoriza_producao"])

    def test_avaliador_emissivo_existente_bloqueia_modelo_desconhecido(self):
        resultado = avaliar_cenario_fiscal_go(
            uf_emitente="GO",
            modelo="99",
            cfop="5102",
        )

        self.assertFalse(resultado["permitido"])
        self.assertIn("modelo 99", " ".join(resultado["pendencias"]))
