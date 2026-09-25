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
    CONTROLES_VALIDOS,
    CONTRATO,
    DIAGNOSTICO,
    DEPENDE_DE_HOMOLOGACAO,
    DEPENDE_DE_PARAMETRIZACAO,
    DEPENDE_DE_DADO_REAL,
    DEPENDE_DE_HOMOLOGACAO_EXTERNA,
    BLOQUEADO_LACUNA_INTERNA,
    NAO_IMPLEMENTADO,
    PRONTO_INTERNAMENTE,
    STATUS_VALIDOS,
    SUPORTADO,
    consultar_capacidade_piloto_go,
    diagnostico_pre_homologacao_go,
    diagnostico_prontidao_interna_piloto_go,
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
        esperado["prontidao_interna_piloto"] = diagnostico_prontidao_interna_piloto_go(
            settings.BASE_DIR
        )
        self.assertEqual(publicado, esperado)

    def test_gate_consolida_recorte_ibs_cbs_e_canais_independentes(self):
        resultado = diagnostico_prontidao_interna_piloto_go(settings.BASE_DIR)

        self.assertEqual(resultado["recorte"], "fiscal_ibs_cbs_go_crt3_standard_v1")
        self.assertEqual(resultado["estado_geral_interno"], PRONTO_INTERNAMENTE)
        self.assertEqual(resultado["gaps_internos"], [])
        self.assertEqual(resultado["canais"]["SEFAZ_DIRETA_GO"]["papel"], "ALVO_PRINCIPAL")
        self.assertEqual(resultado["canais"]["FOCUS"]["papel"], "CANAL_SECUNDARIO")
        for canal in resultado["canais"].values():
            self.assertEqual(canal["estado_interno"], PRONTO_INTERNAMENTE)
            self.assertEqual(canal["estado_para_iniciar"], DEPENDE_DE_DADO_REAL)
            self.assertEqual(
                canal["estado_para_concluir"], DEPENDE_DE_HOMOLOGACAO_EXTERNA
            )
            self.assertFalse(canal["fallback_automatico"])

    def test_gate_prova_nucleo_decimal_cardinalidade_e_xsd_55_65_offline(self):
        resultado = diagnostico_prontidao_interna_piloto_go(settings.BASE_DIR)

        nucleo = resultado["nucleo_ibs_cbs"]
        self.assertTrue(nucleo["contrato_carregavel"])
        self.assertTrue(nucleo["catalogo_rastreavel"])
        self.assertEqual({item["modelo"] for item in nucleo["modelos"]}, {"55", "65"})
        self.assertTrue(all(item["decimal"] for item in nucleo["modelos"]))
        self.assertTrue(all(item["validacao_matematica"] for item in nucleo["modelos"]))
        self.assertTrue(all(item["cardinalidade_exclusividade"] for item in nucleo["modelos"]))
        xsd = resultado["xsd_offline"]
        self.assertTrue(xsd["pacote_integro"])
        self.assertTrue(xsd["dependencias_validas"])
        self.assertTrue(xsd["compilacao"])
        self.assertTrue(xsd["xml_55_valido_e_assinado"])
        self.assertTrue(xsd["xml_65_valido_e_assinado"])
        self.assertFalse(xsd["instalado"])
        self.assertFalse(xsd["promovido"])

    def test_dia_zero_classifica_dados_reais_sem_mascarar_lacuna_interna(self):
        resultado = diagnostico_prontidao_interna_piloto_go(settings.BASE_DIR)
        dia_zero = resultado["dia_zero_homologacao"]

        self.assertIn("FICTICIA", dia_zero["fixture"])
        self.assertEqual(dia_zero["estado_interno"], PRONTO_INTERNAMENTE)
        self.assertFalse(dia_zero["ausencia_dados_reais_e_lacuna_interna"])
        self.assertTrue(dia_zero["dependencias"])
        self.assertTrue(
            all(item["estado"] == DEPENDE_DE_DADO_REAL for item in dia_zero["dependencias"])
        )
        nomes = {item["item"] for item in dia_zero["dependencias"]}
        self.assertTrue(
            {
                "CNPJ da filial GO",
                "Inscricao estadual da filial GO",
                "Certificado A1 e senha",
                "CSC e idCSC",
                "Token Focus NFe de homologacao",
                "Autorizacao humana para iniciar homologacao",
            }.issubset(nomes)
        )

    def test_gate_nunca_transmite_nem_libera_producao(self):
        with patch.object(
            socket,
            "create_connection",
            side_effect=AssertionError("rede acionada"),
        ):
            resultado = diagnostico_prontidao_interna_piloto_go(settings.BASE_DIR)

        self.assertNotEqual(resultado["estado_geral_interno"], BLOQUEADO_LACUNA_INTERNA)
        self.assertFalse(resultado["politica"]["acessou_rede"])
        self.assertFalse(resultado["politica"]["transmitiu"])
        self.assertFalse(resultado["politica"]["homologacao_real"])
        self.assertFalse(resultado["politica"]["producao_liberada"])

    def test_lacuna_focus_nao_mascara_prontidao_independente_sefaz_direta(self):
        from . import pre_homologacao_go

        original = pre_homologacao_go._evidencia_local

        def evidencia_com_focus_ausente(base, codigo):
            item = original(base, codigo)
            if codigo == "pre_transmissao_focus":
                item["estado"] = BLOQUEADO_LACUNA_INTERNA
                item["ausentes"] = ["evidencia Focus simulada como ausente"]
            return item

        with patch(
            "apps.fiscal.pre_homologacao_go._evidencia_local",
            side_effect=evidencia_com_focus_ausente,
        ):
            resultado = diagnostico_prontidao_interna_piloto_go(settings.BASE_DIR)

        self.assertEqual(resultado["estado_geral_interno"], PRONTO_INTERNAMENTE)
        self.assertEqual(
            resultado["canais"]["SEFAZ_DIRETA_GO"]["estado_interno"],
            PRONTO_INTERNAMENTE,
        )
        self.assertEqual(
            resultado["canais"]["FOCUS"]["estado_interno"],
            BLOQUEADO_LACUNA_INTERNA,
        )

    def test_matriz_cobre_recorte_minimo_e_status_validos(self):
        itens = matriz_capacidades_piloto_go()
        por_codigo = {item["codigo"]: item for item in itens}

        self.assertEqual(len(itens), len(por_codigo))
        self.assertTrue(all(item["status"] in STATUS_VALIDOS for item in itens))
        self.assertTrue(all(not item["autoriza_producao"] for item in itens))
        self.assertTrue(all(item["efeito_da_consulta"] == "SOMENTE_DIAGNOSTICO" for item in itens))
        self.assertTrue(all(DIAGNOSTICO in item["controle"] for item in itens))
        self.assertTrue(
            all(set(item["controle"]).issubset(CONTROLES_VALIDOS) for item in itens)
        )
        for codigo in {
            "modelo_65_nfce", "modelo_55_nfe", "crt_1_simples", "crt_2_excesso",
            "crt_3_normal", "crt_4_mei", "pis", "cofins", "ipi", "cbenef",
            "pagamento_dinheiro", "pagamento_credito", "pagamento_debito",
            "pagamento_pix", "pagamento_vale_alimentacao", "pagamento_vale_refeicao",
            "pagamento_dividido", "destinatario_nao_identificado", "destinatario_cpf",
            "destinatario_cnpj", "endereco_emitente", "qrcode_nfce",
            "contingencia_nfce", "sefaz_direta_go", "focus", "ibs_cbs",
            "ibs_cbs_crt3_operacao_padrao",
            "finalidade_nao_suportada",
        }:
            self.assertIn(codigo, por_codigo)

    def test_estados_refletem_limites_comprovados(self):
        itens = {item["codigo"]: item for item in matriz_capacidades_piloto_go()}

        self.assertEqual(itens["pagamento_dinheiro"]["status"], SUPORTADO)
        self.assertEqual(itens["pis"]["status"], DEPENDE_DE_PARAMETRIZACAO)
        self.assertEqual(itens["pagamento_pix"]["status"], DEPENDE_DE_HOMOLOGACAO)
        self.assertEqual(itens["xsd_operacional"]["status"], BLOQUEADO)
        self.assertEqual(itens["ibs_cbs"]["status"], NAO_IMPLEMENTADO)
        self.assertEqual(
            itens["ibs_cbs_crt3_operacao_padrao"]["status"],
            DEPENDE_DE_HOMOLOGACAO,
        )

    def test_combinacao_desconhecida_bloqueia_so_o_diagnostico(self):
        resultado = consultar_capacidade_piloto_go("tributo-futuro-nao-catalogado")

        self.assertEqual(resultado["status"], BLOQUEADO)
        self.assertEqual(resultado["motivo"], "CENARIO_NAO_CATALOGADO")
        self.assertEqual(resultado["controle"], [DIAGNOSTICO])
        self.assertEqual(resultado["efeito_da_consulta"], "SOMENTE_DIAGNOSTICO")
        self.assertEqual(resultado["bloqueio_operacional"], "NAO_COMPROVADO")
        self.assertFalse(resultado["autoriza_producao"])

    def test_matriz_distingue_travas_operacionais_comprovadas(self):
        itens = {item["codigo"]: item for item in matriz_capacidades_piloto_go()}

        self.assertEqual(itens["icms_cst_desconhecido"]["bloqueio_operacional"], "COMPROVADO")
        self.assertEqual(itens["frete"]["bloqueio_operacional"], "COMPROVADO")
        self.assertEqual(
            itens["producao"]["bloqueio_operacional"], "COMPROVADO_NOS_ADAPTADORES"
        )
        self.assertEqual(itens["pagamento_dinheiro"]["bloqueio_operacional"], "NAO_COMPROVADO")

    def test_avaliador_emissivo_existente_bloqueia_modelo_desconhecido(self):
        resultado = avaliar_cenario_fiscal_go(
            uf_emitente="GO",
            modelo="99",
            cfop="5102",
        )

        self.assertFalse(resultado["permitido"])
        self.assertIn("modelo 99", " ".join(resultado["pendencias"]))
