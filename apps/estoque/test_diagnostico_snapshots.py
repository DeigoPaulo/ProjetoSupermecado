from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.empresas.models import Empresa, Filial
from apps.produtos.models import Categoria, Produto

from .diagnostico_snapshots import (
    diagnostico_cobertura_snapshots_lote,
    diagnostico_prontidao_piloto_real,
)
from .models import (
    LoteEstoque,
    MovimentacaoEstoque,
    MovimentacaoLoteEstoque,
    StatusTratamentoValidade,
    TipoMovimentacaoEstoque,
)


class DiagnosticoCoberturaSnapshotsLoteTests(TestCase):
    def setUp(self):
        empresa = Empresa.objects.create(
            razao_social="Mercado Diagnóstico Snapshot Ltda",
            nome_fantasia="Mercado Diagnóstico Snapshot",
            cnpj="93.333.333/0001-93",
        )
        self.filial = Filial.objects.create(
            empresa=empresa, nome="Matriz", cnpj=empresa.cnpj
        )
        self.filial_sem_vendas = Filial.objects.create(
            empresa=empresa, nome="Filial sem vendas", cnpj="93.333.333/0002-74"
        )
        categoria = Categoria.all_objects.create(nome="Diagnóstico snapshots")
        self.produto = Produto.objects.create(
            codigo_barras="7899933333333",
            nome="Produto diagnóstico snapshot",
            categoria=categoria,
            preco_custo=Decimal("2.00"),
            preco_venda=Decimal("5.00"),
        )

    def criar_alocacao(self, codigo, status=StatusTratamentoValidade.NAO_INICIADO):
        movimento = MovimentacaoEstoque.objects.create(
            produto=self.produto,
            filial=self.filial,
            tipo=TipoMovimentacaoEstoque.VENDA,
            quantidade=Decimal("1.000"),
            referencia=f"venda:diagnostico:{codigo}",
        )
        lote = LoteEstoque.objects.create(
            produto=self.produto,
            filial=self.filial,
            codigo=codigo,
            validade=timezone.localdate() + timedelta(days=10),
            quantidade_inicial=Decimal("1.000"),
            quantidade_atual=Decimal("0.000"),
            custo_unitario=Decimal("2.00"),
            tratamento_validade_status=status,
        )
        return MovimentacaoLoteEstoque.objects.create(
            movimentacao=movimento,
            lote=lote,
            quantidade=Decimal("1.000"),
            custo_unitario=Decimal("2.00"),
        )

    def test_classifica_integras_legadas_e_inconsistentes_por_filial(self):
        integra = self.criar_alocacao("INTEGRA")
        legada = self.criar_alocacao("LEGADA")
        hash_divergente = self.criar_alocacao("HASH-DIVERGENTE")
        tratamento_bloqueado = self.criar_alocacao(
            "TRATAMENTO-BLOQUEADO", StatusTratamentoValidade.SEPARADO
        )
        MovimentacaoLoteEstoque.objects.filter(pk=legada.pk).update(
            lote_codigo_snapshot="", tratamento_status_snapshot="", snapshot_sha256=""
        )
        MovimentacaoLoteEstoque.objects.filter(pk=hash_divergente.pk).update(
            lote_codigo_snapshot="ALTERADO"
        )
        antes = list(
            MovimentacaoLoteEstoque.objects.order_by("pk").values_list(
                "pk", "lote_codigo_snapshot", "tratamento_status_snapshot", "snapshot_sha256"
            )
        )

        with self.assertNumQueries(2):
            diagnostico = diagnostico_cobertura_snapshots_lote()

        depois = list(
            MovimentacaoLoteEstoque.objects.order_by("pk").values_list(
                "pk", "lote_codigo_snapshot", "tratamento_status_snapshot", "snapshot_sha256"
            )
        )
        self.assertEqual(antes, depois)
        self.assertEqual(diagnostico["contrato"], "inventory_lot_snapshot_coverage_v1")
        self.assertTrue(diagnostico["somente_leitura"])
        self.assertFalse(diagnostico["corrige_automaticamente"])
        self.assertEqual(
            diagnostico["totais"],
            {
                "total": 4,
                "integras": 1,
                "legadas": 1,
                "inconsistentes": 2,
                "estado": "INCONSISTENTE",
                "estado_display": "Requer investigação",
                "nivel": "danger",
                "cobertura_percentual": 25.0,
                "cobertura_display": "25.0%",
            },
        )
        por_filial = {item["filial_id"]: item for item in diagnostico["filiais"]}
        self.assertEqual(por_filial[self.filial.pk]["integras"], 1)
        self.assertEqual(por_filial[self.filial.pk]["legadas"], 1)
        self.assertEqual(por_filial[self.filial.pk]["inconsistentes"], 2)
        self.assertEqual(por_filial[self.filial_sem_vendas.pk]["estado"], "SEM_VENDAS")
        self.assertIsNone(por_filial[self.filial_sem_vendas.pk]["cobertura_percentual"])
        self.assertEqual(por_filial[self.filial_sem_vendas.pk]["cobertura_display"], "Sem base")
        self.assertTrue(integra.snapshot_integro)
        self.assertTrue(tratamento_bloqueado.snapshot_integro)

        prontidao = diagnostico_prontidao_piloto_real(
            filial_id=self.filial.pk, diagnostico=diagnostico
        )
        self.assertEqual(prontidao["contrato"], "inventory_real_pilot_readiness_v1")
        self.assertEqual(prontidao["estado"], "BLOQUEADA_INCONSISTENCIA")
        self.assertFalse(prontidao["pronta_para_aceite"])
        self.assertTrue(prontidao["somente_leitura"])
        self.assertEqual(
            diagnostico_prontidao_piloto_real(
                filial_id=self.filial_sem_vendas.pk, diagnostico=diagnostico
            )["estado"],
            "SEM_BASE",
        )

    def test_prontidao_exige_base_integra_e_bloqueia_legado(self):
        self.assertEqual(
            diagnostico_prontidao_piloto_real(filial_id=self.filial.pk)["estado"],
            "SEM_BASE",
        )

        alocacao = self.criar_alocacao("PRONTA")
        prontidao = diagnostico_prontidao_piloto_real(filial_id=self.filial.pk)
        self.assertEqual(prontidao["estado"], "PRONTA_ESTRUTURAL")
        self.assertTrue(prontidao["pronta_para_aceite"])
        self.assertTrue(all(prontidao["criterios"].values()))

        MovimentacaoLoteEstoque.objects.filter(pk=alocacao.pk).update(
            lote_codigo_snapshot="", tratamento_status_snapshot="", snapshot_sha256=""
        )
        prontidao = diagnostico_prontidao_piloto_real(filial_id=self.filial.pk)
        self.assertEqual(prontidao["estado"], "BLOQUEADA_LEGADO")
        self.assertFalse(prontidao["pronta_para_aceite"])
