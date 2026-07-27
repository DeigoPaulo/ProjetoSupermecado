from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

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

        lista = self.client.get("/usuarios/")
        self.assertContains(lista, "Diagnóstico de e-mail")

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


class RecuperacaoSenhaDiagnosticoTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser("admin", "admin@example.com", "123")
        self.client = Client(HTTP_HOST="localhost")
        self.client.force_login(self.user)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend",
        EMAIL_HOST="",
        DEFAULT_FROM_EMAIL="nao-responda@teste.local",
    )
    def test_diagnostico_recuperacao_senha_alerta_backend_desenvolvimento(self):
        response = self.client.get("/usuarios/recuperacao-senha/diagnostico.json")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["contrato"], "password_reset_email_v1")
        self.assertEqual(payload["status"], "needs_configuration")
        self.assertTrue(payload["backend"]["console"])
        self.assertFalse(payload["smtp"]["host_configurado"])
        self.assertTrue(payload["seguranca"]["nao_expoe_credenciais"])
        self.assertEqual(payload["prontidao"]["contrato"], "password_reset_readiness_v1")
        self.assertEqual(payload["prontidao"]["status"], "development_only")
        self.assertFalse(payload["prontidao"]["configuracao_smtp_completa"])
        self.assertTrue(payload["prontidao"]["bloqueios"])
        self.assertIn("Backend de desenvolvimento", payload["alertas"][0])

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
        EMAIL_HOST="smtp.example.com",
        EMAIL_PORT=587,
        EMAIL_HOST_USER="usuario@example.com",
        EMAIL_HOST_PASSWORD="segredo",
        EMAIL_USE_TLS=True,
        EMAIL_USE_SSL=False,
        EMAIL_TIMEOUT=8,
        DEFAULT_FROM_EMAIL="nao-responda@example.com",
    )
    def test_diagnostico_recuperacao_senha_pronto_para_producao_sem_expor_credenciais(self):
        response = self.client.get("/usuarios/recuperacao-senha/diagnostico.json")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ready_for_production")
        self.assertTrue(payload["backend"]["smtp"])
        self.assertTrue(payload["smtp"]["host_configurado"])
        self.assertTrue(payload["smtp"]["usuario_configurado"])
        self.assertTrue(payload["smtp"]["senha_configurada"])
        self.assertEqual(payload["smtp"]["porta"], 587)
        self.assertEqual(payload["smtp"]["timeout_segundos"], 8)
        self.assertEqual(payload["prontidao"]["contrato"], "password_reset_readiness_v1")
        self.assertEqual(payload["prontidao"]["status"], "ready_for_homologation")
        self.assertTrue(payload["prontidao"]["configuracao_smtp_completa"])
        self.assertTrue(payload["prontidao"]["homologacao_real_pendente"])
        self.assertTrue(payload["prontidao"]["recomendacoes"])
        self.assertEqual(payload["alertas"], [])
        self.assertNotContains(response, "smtp.example.com")
        self.assertNotContains(response, "segredo")



@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="nao-responda@teste.local",
)
class RecuperacaoSenhaTests(TestCase):
    def setUp(self):
        self.client = Client(HTTP_HOST="localhost")
        self.user = get_user_model().objects.create_user(
            username="operador",
            email="operador@example.com",
            password="Senha-antiga-123",
            is_active=True,
        )

    def test_login_exibe_acesso_para_recuperacao(self):
        response = self.client.get(reverse("login"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Esqueci minha senha")
        self.assertContains(response, reverse("password_reset"))

    def test_solicitacao_envia_link_apenas_para_conta_ativa_sem_revelar_cadastro(self):
        response = self.client.post(reverse("password_reset"), {"email": self.user.email})

        self.assertRedirects(response, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.user.email])
        self.assertIn("/redefinir-senha/", mail.outbox[0].body)
        self.assertNotIn("Senha-antiga-123", mail.outbox[0].body)

        mail.outbox.clear()
        response_desconhecido = self.client.post(
            reverse("password_reset"),
            {"email": "nao-cadastrado@example.com"},
        )

        self.assertRedirects(response_desconhecido, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)

        pagina_neutra = self.client.get(reverse("password_reset_done"))
        self.assertContains(pagina_neutra, "Se existir uma conta ativa")
        self.assertContains(pagina_neutra, "não confirma se o e-mail está cadastrado")

    def test_link_valido_altera_senha_e_nao_pode_ser_reutilizado(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        url = reverse("password_reset_confirm", kwargs={"uidb64": uid, "token": token})

        abertura = self.client.get(url)
        self.assertEqual(abertura.status_code, 302)
        self.assertIn("/redefinir-senha/", abertura.url)

        conclusao = self.client.post(
            abertura.url,
            {
                "new_password1": "Senha-nova-segura-456",
                "new_password2": "Senha-nova-segura-456",
            },
            follow=True,
        )

        self.assertRedirects(conclusao, reverse("password_reset_complete"))
        self.assertContains(conclusao, "Senha alterada")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Senha-nova-segura-456"))

        reutilizacao = self.client.get(url, follow=True)
        self.assertContains(reutilizacao, "Link inválido ou expirado")
