from django.test import SimpleTestCase

from .cenarios_tributarios import (
    BLOQUEADO,
    CONTRATO_CENARIOS_TRIBUTARIOS,
    DEPENDENCIA_EXTERNA,
    PARCIAL,
    STATUS_VALIDOS,
    avaliar_cenario_fiscal_go,
    pendencias_cenario_fiscal_go,
    catalogo_cenarios_tributarios_go,
    perfil_fiscal_provisorio_go,
    resumo_cenarios_tributarios_go,
)
from .sefaz_direta.capacidades import (
    PARCIAL as CAPACIDADE_PARCIAL,
    resumo_capacidades,
)
from .services import capacidade_tributaria_fiscal


class CenariosTributariosGoTests(SimpleTestCase):
    def test_perfil_provisorio_nao_inventa_identidade_nem_libera_rede(self):
        perfil = perfil_fiscal_provisorio_go()

        self.assertEqual(perfil["codigo"], "go_dev_sem_credenciais_v1")
        self.assertEqual(perfil["regime_tributario"], "PENDENTE_DEFINICAO_CONTADOR")
        self.assertFalse(perfil["permite_comunicacao_externa"])
        self.assertFalse(perfil["permite_producao"])
        self.assertFalse(perfil["exige_cnpj_ie_a1_csc_reais"])

    def test_catalogo_tem_codigos_unicos_status_validos_e_proxima_evidencia(self):
        itens = catalogo_cenarios_tributarios_go()
        codigos = [item["codigo"] for item in itens]

        self.assertEqual(len(codigos), len(set(codigos)))
        self.assertTrue(all(item["status"] in STATUS_VALIDOS for item in itens))
        self.assertTrue(all(item["proxima_evidencia"] for item in itens))

    def test_nenhum_cenario_e_declarado_totalmente_suportado_antes_da_homologacao(self):
        itens = catalogo_cenarios_tributarios_go()

        self.assertTrue(all(item["status"] in {PARCIAL, BLOQUEADO, DEPENDENCIA_EXTERNA} for item in itens))

    def test_cenarios_criticos_ficam_explicitamente_bloqueados(self):
        por_codigo = {item["codigo"]: item for item in catalogo_cenarios_tributarios_go()}

        for codigo in {
            "venda_interestadual",
            "venda_contribuinte_b2b",
            "icms_st_retido",
            "tributacao_monofasica",
            "devolucao_fornecedor",
            "transferencia_bonificacao_remessa",
            "frete_entrega",
        }:
            self.assertEqual(por_codigo[codigo]["status"], BLOQUEADO)

    def test_resumo_publica_contrato_e_total_coerentes(self):
        resumo = resumo_cenarios_tributarios_go()

        self.assertEqual(resumo["contrato"], CONTRATO_CENARIOS_TRIBUTARIOS)
        self.assertEqual(sum(resumo["contagem"].values()), resumo["total"])
        self.assertEqual(len(resumo["itens"]), resumo["total"])

    def test_matriz_existente_preserva_limites_reais_de_icms(self):
        capacidade = capacidade_tributaria_fiscal()

        self.assertEqual(capacidade["regime_normal"]["cst_suportados"], ["00", "20", "40", "41", "50"])
        self.assertEqual(capacidade["simples_nacional"]["csosn_suportados"], ["102", "103", "300", "400"])
        self.assertFalse(capacidade["ibs_cbs"]["emissao_xml_habilitada"])

    def test_sefaz_direta_nao_declara_emissao_completa(self):
        itens = {item["codigo"]: item for item in resumo_capacidades()["itens"]}

        self.assertEqual(itens["emissao_nfe_nfce"]["status"], CAPACIDADE_PARCIAL)
        self.assertEqual(itens["ibs_cbs"]["status"], CAPACIDADE_PARCIAL)

    def test_validador_aceita_somente_as_premissas_da_venda_interna_atual(self):
        resultado = avaliar_cenario_fiscal_go(
            uf_emitente="GO",
            modelo="65",
            cfop="5102",
            finalidade="1",
            destinatario_contribuinte=False,
            possui_frete=False,
        )

        self.assertTrue(resultado["aplicavel"])
        self.assertTrue(resultado["permitido"])
        self.assertEqual(resultado["status"], PARCIAL)
        self.assertEqual(resultado["cenario"], "venda_interna_consumidor_final")

    def test_validador_bloqueia_interestadual_contribuinte_frete_e_finalidade(self):
        pendencias = pendencias_cenario_fiscal_go(
            uf_emitente="GO",
            modelo="65",
            cfop="6102",
            finalidade="4",
            destinatario_contribuinte=True,
            possui_frete=True,
        )
        mensagem = " ".join(pendencias)

        self.assertIn("venda interna", mensagem)
        self.assertIn("finalidade normal", mensagem)
        self.assertIn("destinatário contribuinte", mensagem)
        self.assertIn("frete", mensagem)

    def test_validador_go_nao_se_aplica_automaticamente_a_outra_uf(self):
        resultado = avaliar_cenario_fiscal_go(
            uf_emitente="SP",
            modelo="65",
            cfop="6102",
            possui_frete=True,
        )

        self.assertFalse(resultado["aplicavel"])
        self.assertTrue(resultado["permitido"])
        self.assertEqual(resultado["pendencias"], [])
