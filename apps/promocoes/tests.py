from decimal import Decimal
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone

from apps.produtos.models import Categoria, Produto

from .models import PromocaoProduto


class PromocaoViewsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser("admin", "admin@example.com", "123")
        self.client = Client(HTTP_HOST="localhost")
        self.client.force_login(self.user)
        self.categoria = Categoria.objects.create(nome="Promocoes")
        self.produto = Produto.objects.create(
            codigo_barras="7893333333333",
            nome="Cafe Promocional",
            categoria=self.categoria,
            preco_custo=Decimal("8.00"),
            preco_venda=Decimal("14.00"),
        )
        agora = timezone.now()
        self.promocao = PromocaoProduto.objects.create(
            produto=self.produto,
            nome="Oferta cafe",
            preco_promocional=Decimal("11.90"),
            inicio=agora,
            fim=agora + timedelta(days=3),
            criado_por=self.user,
        )

    def test_form_promocao_exibe_secoes_operacionais(self):
        response = self.client.get(f"/promocoes/{self.promocao.pk}/editar/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Produto e preço")
        self.assertContains(response, "Vigencia")
        self.assertContains(response, "O PDV aplica automaticamente")
        self.assertContains(response, "select2-field")

    def test_valida_periodo_da_promocao(self):
        inicio = timezone.now()
        response = self.client.post(
            "/promocoes/nova/",
            {
                "produto": self.produto.pk,
                "nome": "Periodo inválido",
                "preco_promocional": "10.00",
                "inicio": inicio.strftime("%Y-%m-%dT%H:%M"),
                "fim": (inicio - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"),
                "ativa": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "A data final deve ser maior que a data inicial.")
