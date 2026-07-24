from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.accounts.models import PerfilUsuario, TipoPerfil
from apps.empresas.models import Empresa, Filial
from apps.estoque.models import MovimentacaoEstoque, TipoMovimentacaoEstoque
from apps.pdv.models import Caixa, Sangria, StatusCaixa, Suprimento
from apps.produtos.models import Categoria, Produto
from apps.vendas.models import FormaPagamento, PagamentoVenda, StatusVenda, Venda


class DashboardTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.empresa = Empresa.objects.create(razao_social="Mercado Teste", nome_fantasia="Mercado Teste", cnpj="12345678000190")
        self.filial = Filial.objects.create(empresa=self.empresa, nome="Matriz")
        self.usuario = User.objects.create_user(username="gerente", password="senha")
        PerfilUsuario.objects.create(usuario=self.usuario, filial=self.filial, tipo=TipoPerfil.GERENTE)

    def test_dashboard_renderiza_graficos_gerenciais(self):
        categoria = Categoria.objects.create(nome="Mercearia")
        Produto.objects.create(codigo_barras="789100000001", nome="Arroz", categoria=categoria, preco_custo=Decimal("10"), preco_venda=Decimal("15"))
        caixa = Caixa.objects.create(filial=self.filial, usuario_abertura=self.usuario, valor_inicial=Decimal("100"))
        forma = FormaPagamento.objects.create(nome="Pix", tipo="PIX")
        venda = Venda.objects.create(
            filial=self.filial,
            caixa=caixa,
            usuario=self.usuario,
            total_bruto=Decimal("15"),
            total_liquido=Decimal("15"),
            status=StatusVenda.FINALIZADA,
        )
        PagamentoVenda.objects.create(venda=venda, forma_pagamento=forma, valor=Decimal("15"))
        self.client.force_login(self.usuario)

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "dashboard-chart-data")
        self.assertContains(response, "dashboard-payments-chart")
        self.assertContains(response, "dashboard-categories-chart")
        self.assertContains(response, "dashboard-boxes-chart")

    def test_relatorio_caixas_filtra_e_resume_por_operador(self):
        User = get_user_model()
        operador_a = User.objects.create_user(username="caixa_maria", password="senha")
        operador_b = User.objects.create_user(username="caixa_joao", password="senha")
        caixa_a = Caixa.objects.create(
            filial=self.filial,
            usuario_abertura=operador_a,
            valor_inicial=Decimal("100"),
            valor_final=Decimal("180"),
            valor_conferido=Decimal("180"),
            status=StatusCaixa.CONFERIDO,
        )
        Caixa.objects.create(filial=self.filial, usuario_abertura=operador_b, valor_inicial=Decimal("50"))
        venda = Venda.objects.create(
            filial=self.filial,
            caixa=caixa_a,
            usuario=operador_a,
            total_bruto=Decimal("80"),
            total_liquido=Decimal("80"),
            status=StatusVenda.FINALIZADA,
        )
        forma = FormaPagamento.objects.create(nome="Dinheiro", tipo="DINHEIRO")
        PagamentoVenda.objects.create(venda=venda, forma_pagamento=forma, valor=Decimal("80"))
        Sangria.objects.create(caixa=caixa_a, usuario=operador_a, valor=Decimal("20"), motivo="Retirada parcial")
        Suprimento.objects.create(caixa=caixa_a, usuario=operador_a, valor=Decimal("15"), motivo="Troco inicial extra")
        self.client.force_login(self.usuario)

        url = f"/caixas/?operador={operador_a.pk}"
        response = self.client.get(url)
        csv_response = self.client.get(f"/caixas/exportar.csv?operador={operador_a.pk}")
        imprimir = self.client.get(f"/caixas/imprimir/?operador={operador_a.pk}")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Resumo por operador/funcionario")
        self.assertContains(response, "caixa_maria")
        self.assertContains(response, "R$ 80,00")
        self.assertContains(response, "R$ 100,00")
        self.assertContains(response, "Diferença conferida")
        self.assertContains(response, "R$ 0,00")
        self.assertNotContains(response, "R$ 50,00")
        self.assertContains(csv_response, "Filtro operador;caixa_maria")
        self.assertContains(csv_response, "Resumo por operador")
        self.assertContains(csv_response, "Total vendas;Sangrias;Suprimentos;Saldo operacional")
        self.assertContains(csv_response, "80,00;20,00;15,00;75,00")
        self.assertContains(imprimir, "Operador: caixa_maria")
        self.assertContains(imprimir, "Saldo operacional")
        self.assertContains(imprimir, "R$ 75,00")
        self.assertContains(imprimir, "Forma de pagamento")

    def test_relatorio_movimentacoes_formata_quantidades_no_padrao_brasileiro(self):
        categoria = Categoria.objects.create(nome="Hortifruti")
        produto = Produto.objects.create(
            codigo_barras="789100000002",
            nome="Maca",
            categoria=categoria,
            preco_custo=Decimal("2.00"),
            preco_venda=Decimal("5.00"),
        )
        MovimentacaoEstoque.objects.create(
            produto=produto,
            filial=self.filial,
            tipo=TipoMovimentacaoEstoque.ENTRADA,
            quantidade=Decimal("20.000"),
            usuario=self.usuario,
        )
        MovimentacaoEstoque.objects.create(
            produto=produto,
            filial=self.filial,
            tipo=TipoMovimentacaoEstoque.VENDA,
            quantidade=Decimal("1.250"),
            usuario=self.usuario,
        )
        self.client.force_login(self.usuario)

        response = self.client.get("/movimentacoes-estoque/")

        self.assertContains(response, "<strong>20</strong>", html=True)
        self.assertContains(response, "<strong>1,250</strong>", html=True)
        self.assertNotContains(response, "20,000")
