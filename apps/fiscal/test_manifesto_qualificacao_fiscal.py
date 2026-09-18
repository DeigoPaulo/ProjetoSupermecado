import copy
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from .manifesto_qualificacao_fiscal import (
    gerar_identidade_instalacao,
    gerar_manifesto_qualificacao,
    validar_qualificacao_instalada_payload,
)
from .politica_canais_fiscais import (
    OPERACOES_FISCAIS_CANONICAS,
    diagnosticar_compatibilidade_canal_uf,
)
from .roteamento_operacoes_fiscais import resolver_adaptador_operacao


class ManifestoQualificacaoFiscalTests(SimpleTestCase):
    def setUp(self):
        self.commit = "a" * 40
        self.manifesto = gerar_manifesto_qualificacao(
            raiz_projeto=Path(__file__).resolve().parents[2],
            versao="1.2.3", commit=self.commit, hash_base_pacote="b" * 64,
            gerado_em="2026-09-18T00:00:00+00:00",
        )
        self.identidade = gerar_identidade_instalacao(
            versao="1.2.3", commit=self.commit
        )

    def validar(self, manifesto=None, identidade=None, canal="SEFAZ_DIRETA_GO", operacoes=None):
        return validar_qualificacao_instalada_payload(
            manifesto if manifesto is not None else self.manifesto,
            identidade if identidade is not None else self.identidade,
            canal=canal, operacoes=operacoes,
        )

    def test_manifesto_direto_cobre_sete_operacoes_sem_homologar_ou_liberar_producao(self):
        resultado = self.validar()
        self.assertTrue(resultado["valido"])
        self.assertEqual(resultado["operacoes"], OPERACOES_FISCAIS_CANONICAS)
        self.assertFalse(resultado["homologacao_real_executada"])
        self.assertFalse(resultado["producao_liberada"])
        self.assertEqual(self.manifesto["canais"]["FOCUS"]["lacunas_internas"], ["EVENTOS"])

    def test_falha_fechado_para_ausencia_malformacao_contrato_e_integridade(self):
        self.assertFalse(self.validar(manifesto={})["valido"])
        adulterado = copy.deepcopy(self.manifesto)
        adulterado["canal_piloto"] = "FOCUS"
        self.assertFalse(self.validar(manifesto=adulterado)["valido"])
        desconhecido = copy.deepcopy(self.manifesto)
        desconhecido["contrato"] = "desconhecido"
        self.assertFalse(self.validar(manifesto=desconhecido)["valido"])
        pacote_invalido = copy.deepcopy(self.manifesto)
        pacote_invalido["pacote"]["hash_base_sha256"] = "invalido"
        pacote_invalido["hash_integridade"] = ""
        self.assertFalse(self.validar(manifesto=pacote_invalido)["valido"])

    def test_falha_fechado_para_commit_versao_canal_e_operacao_divergentes(self):
        identidade_commit = gerar_identidade_instalacao(versao="1.2.3", commit="c" * 40)
        identidade_versao = gerar_identidade_instalacao(versao="9.9.9", commit=self.commit)
        self.assertFalse(self.validar(identidade=identidade_commit)["valido"])
        self.assertFalse(self.validar(identidade=identidade_versao)["valido"])
        self.assertFalse(self.validar(canal="DESCONHECIDO")["valido"])
        self.assertFalse(self.validar(operacoes=("OPERACAO_FANTASMA",))["valido"])

    def test_focus_eventos_permanece_lacuna_sem_bloquear_canal_direto(self):
        self.assertFalse(self.validar(canal="FOCUS")["valido"])
        self.assertTrue(self.validar(canal="SEFAZ_DIRETA_GO")["valido"])

    def test_politica_uf_e_caminho_direto_nao_dependem_de_focus(self):
        self.assertTrue(diagnosticar_compatibilidade_canal_uf("SEFAZ_DIRETA_GO", "GO")["valido"])
        self.assertFalse(diagnosticar_compatibilidade_canal_uf("SEFAZ_DIRETA_GO", "SP")["valido"])
        filial = SimpleNamespace(
            uf="GO",
            configuracao_fiscal=SimpleNamespace(provedor_emissao="SEFAZ_DIRETA_GO"),
        )
        with patch("apps.fiscal.focus_sefaz_adapter.FocusNFeSefazAdapter", side_effect=AssertionError):
            resolvido = resolver_adaptador_operacao(filial=filial, operacao="DFE")
        self.assertIn("SefazDiretaDFeAdapter", resolvido["adaptador"])
