from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from apps.accounts.models import PerfilUsuario, TipoPerfil
from apps.empresas.models import Empresa, Filial
from apps.financeiro.forms import ContaFinanceiraForm
from apps.marketplace.forms import PedidoOnlineForm
from apps.pdv.forms import FinalizarVendaForm, PreVendaForm

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

class ClienteIsolamentoEmpresaTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.empresa_a = Empresa.objects.create(
            razao_social="Mercado A Ltda",
            nome_fantasia="Mercado A",
            cnpj="11.111.111/0001-11",
        )
        self.empresa_b = Empresa.objects.create(
            razao_social="Mercado B Ltda",
            nome_fantasia="Mercado B",
            cnpj="22.222.222/0001-22",
        )
        self.filial_a = Filial.objects.create(empresa=self.empresa_a, nome="Matriz A", cnpj=self.empresa_a.cnpj)
        self.filial_b = Filial.objects.create(empresa=self.empresa_b, nome="Matriz B", cnpj=self.empresa_b.cnpj)
        self.usuario_a = User.objects.create_user("gerente_a", password="123")
        self.super_admin = User.objects.create_superuser("master", "master@example.com", "123")
        PerfilUsuario.objects.create(usuario=self.usuario_a, filial=self.filial_a, tipo=TipoPerfil.GERENTE)
        self.cliente_a = Cliente.objects.create(empresa=self.empresa_a, nome="Cliente da empresa A", cpf_cnpj="11111111111")
        self.cliente_b = Cliente.objects.create(empresa=self.empresa_b, nome="Cliente da empresa B", cpf_cnpj="22222222222")
        self.client = Client(HTTP_HOST="localhost")

    def test_lista_busca_e_edicao_respeitam_empresa_do_usuario(self):
        self.client.force_login(self.usuario_a)

        lista = self.client.get("/clientes/")
        busca = self.client.get("/clientes/busca.json", {"q": "Cliente da empresa"})
        edicao_estrangeira = self.client.get(f"/clientes/{self.cliente_b.pk}/editar/")

        self.assertContains(lista, self.cliente_a.nome)
        self.assertNotContains(lista, self.cliente_b.nome)
        self.assertEqual([item["id"] for item in busca.json()["results"]], [self.cliente_a.pk])
        self.assertEqual(edicao_estrangeira.status_code, 404)

    def test_usuario_nao_consegue_forcar_empresa_de_outro_cliente(self):
        self.client.force_login(self.usuario_a)

        resposta = self.client.post(
            "/clientes/novo/",
            {
                "empresa": self.empresa_b.pk,
                "nome": "Cliente forjado",
                "cpf_cnpj": "33333333333",
                "telefone": "",
                "email": "",
                "endereco": "",
                "is_active": "on",
            },
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(Cliente.objects.filter(nome="Cliente forjado").exists())

    def test_formularios_operacionais_oferecem_somente_clientes_da_empresa(self):
        formularios = [
            FinalizarVendaForm(user=self.usuario_a),
            PreVendaForm(user=self.usuario_a),
            PedidoOnlineForm(user=self.usuario_a),
            ContaFinanceiraForm(user=self.usuario_a),
        ]

        for formulario in formularios:
            with self.subTest(formulario=formulario.__class__.__name__):
                self.assertEqual(list(formulario.fields["cliente"].queryset), [self.cliente_a])

    def test_super_admin_mantem_visao_global(self):
        self.client.force_login(self.super_admin)

        lista = self.client.get("/clientes/")

        self.assertContains(lista, self.cliente_a.nome)
        self.assertContains(lista, self.cliente_b.nome)
