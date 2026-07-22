from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from .models import Cliente


class ClienteViewsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser("admin", "admin@example.com", "123")
        self.client = Client(HTTP_HOST="localhost")
        self.client.force_login(self.user)
        self.cliente = Cliente.objects.create(nome="Cliente Teste", cpf_cnpj="123.456.789-09", telefone="11999999999")

    def test_form_cliente_exibe_secoes_operacionais(self):
        response = self.client.get(f"/clientes/{self.cliente.pk}/editar/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Identificacao")
        self.assertContains(response, "Contato e endereco")
        self.assertContains(response, "Opcional para venda presencial avulsa.")
        self.assertContains(response, "busca de CEP")

    def test_busca_json_retorna_cliente_para_select2(self):
        response = self.client.get("/clientes/busca.json", {"q": "Teste"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["results"][0]["id"], self.cliente.id)
        self.assertIn("Cliente Teste", payload["results"][0]["text"])
