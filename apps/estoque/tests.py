from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from apps.empresas.models import Empresa, Filial
from apps.produtos.models import Categoria, Produto


class EstoqueViewsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser("admin", "admin@example.com", "123")
        self.client = Client(HTTP_HOST="localhost")
        self.client.force_login(self.user)
        self.empresa = Empresa.objects.create(
            razao_social="Mercado Estoque",
            nome_fantasia="Mercado Estoque",
            cnpj="22.222.222/0001-22",
        )
        self.filial = Filial.objects.create(empresa=self.empresa, nome="Matriz", cnpj=self.empresa.cnpj)
        self.categoria = Categoria.all_objects.create(nome="Estoque Teste")
        self.produto = Produto.objects.create(
            codigo_barras="7892222222222",
            nome="Produto Estoque",
            categoria=self.categoria,
            preco_custo="3.00",
            preco_venda="5.00",
        )

    def test_form_movimentacao_exibe_operacao_e_autorizacao(self):
        response = self.client.get("/estoque/movimentar/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Operacao")
        self.assertContains(response, "Autorizacao")
        self.assertContains(response, "Movimentacoes manuais ficam registradas")
        self.assertContains(response, "select2-field")

    def test_form_perda_exibe_rastreabilidade_e_autorizacao(self):
        response = self.client.get("/estoque/perdas/nova/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Perda")
        self.assertContains(response, "Registre avaria")
        self.assertContains(response, "A baixa reduz estoque")
        self.assertContains(response, "select2-field")

    def test_form_inventario_exibe_abertura_da_contagem(self):
        response = self.client.get("/estoque/inventarios/novo/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Abertura da contagem")
        self.assertContains(response, "antes de adicionar os produtos contados")
