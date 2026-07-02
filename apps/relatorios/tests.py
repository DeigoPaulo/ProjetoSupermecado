from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.accounts.models import PerfilUsuario, TipoPerfil
from apps.empresas.models import Empresa, Filial
from apps.pdv.models import Caixa
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
