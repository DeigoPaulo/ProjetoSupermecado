from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import PerfilUsuario, TipoPerfil
from apps.empresas.models import Empresa, Filial
from apps.estoque.models import LoteEstoque, PerdaEstoque, TipoPerdaEstoque
from apps.produtos.models import Categoria, Produto


class RelatorioPerdasLoteTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(razao_social="Mercado Relatório Perdas", nome_fantasia="Mercado Relatório Perdas", cnpj="12345678000190")
        self.filial = Filial.objects.create(empresa=self.empresa, nome="Matriz Perdas")
        self.usuario = get_user_model().objects.create_user("gerente_perdas", password="senha")
        PerfilUsuario.objects.create(usuario=self.usuario, filial=self.filial, tipo=TipoPerfil.GERENTE)
        categoria = Categoria.objects.create(nome="Relatório perdas")
        self.produto = Produto.objects.create(codigo_barras="7891000066661", nome="Produto relatório", categoria=categoria, preco_custo=Decimal("4"), preco_venda=Decimal("8"))
        self.lote = LoteEstoque.objects.create(produto=self.produto, filial=self.filial, codigo="LOT-REL-01", quantidade_inicial=Decimal("5"), quantidade_atual=Decimal("3"), custo_unitario=Decimal("4"))
        self.com_lote = self._perda(TipoPerdaEstoque.VENCIMENTO, Decimal("2"), "Vencimento lote", lote=self.lote)
        self.sem_lote = self._perda(TipoPerdaEstoque.AVARIA, Decimal("1"), "Avaria genérica")
        self.client.force_login(self.usuario)

    def _perda(self, tipo, quantidade, motivo, lote=None, filial=None):
        return PerdaEstoque.objects.create(produto=self.produto, filial=filial or self.filial, usuario=self.usuario, lote=lote, tipo=tipo, quantidade=quantidade, motivo=motivo, custo_unitario_no_momento=Decimal("4"), preco_venda_no_momento=Decimal("8"), valor_custo_estimado=Decimal("4")*quantidade, valor_venda_estimado=Decimal("8")*quantidade)

    def test_consolida_lote_causa_quantidade_e_valores(self):
        response = self.client.get(reverse("relatorios:perdas"), {"filial": self.filial.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_perdas"], 2)
        self.assertEqual(response.context["quantidade_total"], Decimal("3"))
        self.assertEqual(response.context["valor_custo_total"], Decimal("12"))
        self.assertEqual(len(response.context["perdas_por_lote"]), 2)
        self.assertContains(response, "LOT-REL-01")
        self.assertContains(response, "Sem lote")

    def test_filtros_valem_na_tela_csv_e_impressao(self):
        params = {"filial": self.filial.pk, "tipo": TipoPerdaEstoque.VENCIMENTO, "com_lote": "SIM"}
        tela = self.client.get(reverse("relatorios:perdas"), params)
        self.assertEqual(tela.context["total_perdas"], 1)
        self.assertContains(tela, "Vencimento lote")
        self.assertNotContains(tela, "Avaria genérica")
        csv = self.client.get(reverse("relatorios:perdas_csv"), params).content.decode("utf-8-sig")
        self.assertIn("LOT-REL-01", csv)
        self.assertIn("Vencimento lote", csv)
        self.assertNotIn("Avaria genérica", csv)
        impresso = self.client.get(reverse("relatorios:perdas_imprimir"), params)
        self.assertContains(impresso, "LOT-REL-01")

    def test_isola_perda_de_outra_empresa(self):
        externa = Empresa.objects.create(razao_social="Externa", nome_fantasia="Externa", cnpj="11222333000144")
        filial_externa = Filial.objects.create(empresa=externa, nome="Filial externa")
        self._perda(TipoPerdaEstoque.OUTROS, Decimal("9"), "PERDA EXTERNA", filial=filial_externa)
        response = self.client.get(reverse("relatorios:perdas"))
        self.assertEqual(response.context["total_perdas"], 2)
        self.assertNotContains(response, "PERDA EXTERNA")
