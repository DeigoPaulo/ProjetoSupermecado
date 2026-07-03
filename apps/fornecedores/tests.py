from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from .models import Fornecedor


class FornecedorViewsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser("admin", "admin@example.com", "123")
        self.client = Client(HTTP_HOST="localhost")
        self.client.force_login(self.user)
        self.fornecedor = Fornecedor.objects.create(
            razao_social="Fornecedor Teste Ltda",
            nome_fantasia="Fornecedor Teste",
            cnpj="11.111.111/0001-11",
            prazo_entrega_dias=3,
        )

    def test_form_fornecedor_exibe_secoes_operacionais(self):
        response = self.client.get(f"/fornecedores/{self.fornecedor.pk}/editar/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Identificacao")
        self.assertContains(response, "Contato e entrega")
        self.assertContains(response, "consultar CNPJ automaticamente")
        self.assertContains(response, "previsao de recebimento")
