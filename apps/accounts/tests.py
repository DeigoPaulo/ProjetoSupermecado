from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from apps.empresas.models import Empresa, Filial

from .models import PerfilUsuario, TipoPerfil


class UsuariosViewsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser("admin", "admin@example.com", "123")
        self.client = Client(HTTP_HOST="localhost")
        self.client.force_login(self.user)
        self.empresa = Empresa.objects.create(
            razao_social="Mercado Teste Ltda",
            nome_fantasia="Mercado Teste",
            cnpj="44.444.444/0001-44",
        )
        self.filial = Filial.objects.create(empresa=self.empresa, nome="Matriz", cnpj=self.empresa.cnpj, is_active=True)

    def test_form_usuario_exibe_secoes_administrativas(self):
        response = self.client.get("/usuarios/novo/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Acesso")
        self.assertContains(response, "Dados pessoais")
        self.assertContains(response, "Perfil operacional")
        self.assertContains(response, "Use a filial para vincular operadores")
        self.assertContains(response, 'name="username"')
        self.assertContains(response, "no-upper")
        self.assertContains(response, "select2-field")

    def test_cria_usuario_com_perfil_operacional(self):
        response = self.client.post(
            "/usuarios/novo/",
            {
                "username": "CaixaOperador01",
                "password": "senha-segura-123",
                "first_name": "Caixa",
                "last_name": "Um",
                "email": "caixa@example.com",
                "tipo": TipoPerfil.OPERADOR_CAIXA,
                "filial": self.filial.pk,
                "telefone": "(11) 99999-9999",
                "is_active": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        usuario = get_user_model().objects.get(username="CaixaOperador01")
        self.assertTrue(usuario.check_password("senha-segura-123"))
        self.assertEqual(usuario.perfil_supermercado.tipo, TipoPerfil.OPERADOR_CAIXA)
        self.assertEqual(usuario.perfil_supermercado.filial, self.filial)
