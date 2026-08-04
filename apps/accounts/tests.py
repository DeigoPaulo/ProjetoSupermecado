from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.core.exceptions import ValidationError
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.utils import timezone
from datetime import timedelta
from io import StringIO

from apps.auditoria.models import LogAuditoria
from apps.empresas.models import AcaoPinSupervisor, Empresa, Filial

from .models import CredencialAutorizacao, PerfilUsuario, TipoCredencialAutorizacao, TipoPerfil, UsoCredencialAutorizacao
from .permissions import supervisor_from_request


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


class CredenciaisAutorizacaoTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.empresa = Empresa.objects.create(
            razao_social="Mercado Credencial Ltda", nome_fantasia="Mercado Credencial", cnpj="31.111.111/0001-31"
        )
        self.filial = Filial.objects.create(empresa=self.empresa, nome="Matriz", cnpj=self.empresa.cnpj)
        self.admin = User.objects.create_user("admin_credencial", password="123")
        PerfilUsuario.objects.create(usuario=self.admin, filial=self.filial, tipo=TipoPerfil.ADMINISTRADOR)
        self.supervisor = User.objects.create_user("supervisor_credencial", password="123")
        PerfilUsuario.objects.create(usuario=self.supervisor, filial=self.filial, tipo=TipoPerfil.GERENTE)
        self.operador = User.objects.create_user("operador_credencial", password="123")
        PerfilUsuario.objects.create(usuario=self.operador, filial=self.filial, tipo=TipoPerfil.OPERADOR_CAIXA)
        outra_empresa = Empresa.objects.create(
            razao_social="Outro Mercado Ltda", nome_fantasia="Outro Mercado", cnpj="32.222.222/0001-32"
        )
        outra_filial = Filial.objects.create(empresa=outra_empresa, nome="Matriz", cnpj=outra_empresa.cnpj)
        self.supervisor_externo = User.objects.create_user("supervisor_externo", password="123")
        PerfilUsuario.objects.create(usuario=self.supervisor_externo, filial=outra_filial, tipo=TipoPerfil.GERENTE)
        self.client = Client(HTTP_HOST="localhost")
        self.client.force_login(self.admin)
        self.factory = RequestFactory()

    def criar_credencial(self, usuario=None, token="CARD-SEGREDO-001", pin=""):
        credencial = CredencialAutorizacao(
            usuario=usuario or self.supervisor,
            tipo=TipoCredencialAutorizacao.NFC,
            nome="Crachá do supervisor",
            criada_por=self.admin,
        )
        credencial.definir_identificador(token)
        credencial.definir_pin(pin)
        credencial.save()
        return credencial

    def test_admin_cadastra_sem_armazenar_identificador_e_pode_revogar(self):
        response = self.client.post(
            "/usuarios/credenciais-autorizacao/",
            {
                "usuario": self.supervisor.pk,
                "tipo": TipoCredencialAutorizacao.NFC,
                "nome": "Cartão azul",
                "identificador": "UID-NUNCA-GRAVAR-123",
                "pin": "4321",
            },
        )

        self.assertRedirects(response, "/usuarios/credenciais-autorizacao/")
        credencial = CredencialAutorizacao.objects.get()
        self.assertNotEqual(credencial.identificador_hash, "UID-NUNCA-GRAVAR-123")
        self.assertTrue(credencial.validar_pin("4321"))
        pagina = self.client.get("/usuarios/credenciais-autorizacao/")
        self.assertContains(pagina, "Cartão azul")
        self.assertNotContains(pagina, "UID-NUNCA-GRAVAR-123")

        revogada = self.client.post(f"/usuarios/credenciais-autorizacao/{credencial.pk}/revogar/")
        self.assertRedirects(revogada, "/usuarios/credenciais-autorizacao/")
        credencial.refresh_from_db()
        self.assertFalse(credencial.ativa)
        self.assertIsNotNone(credencial.revogada_em)

    def test_helper_aceita_cartao_com_pin_e_registra_uso(self):
        credencial = self.criar_credencial(pin="2468")
        request = self.factory.post(
            "/pdv/operacao-protegida/",
            {"supervisor_credencial": "CARD-SEGREDO-001", "supervisor_pin": "2468"},
        )
        request.user = self.operador
        request.META["REMOTE_ADDR"] = "127.0.0.1"

        usuario = supervisor_from_request(request)

        self.assertEqual(usuario, self.supervisor)
        uso = UsoCredencialAutorizacao.objects.get(credencial=credencial)
        self.assertEqual(uso.operador, self.operador)
        self.assertEqual(uso.supervisor, self.supervisor)
        self.assertEqual(uso.caminho, "/pdv/operacao-protegida/")
        credencial.refresh_from_db()
        self.assertIsNotNone(credencial.ultimo_uso_em)

    def test_helper_rejeita_pin_invalido_expirada_revogada_e_outra_empresa(self):
        self.criar_credencial(token="COM-PIN", pin="1234")
        expirada = self.criar_credencial(token="EXPIRADA")
        expirada.valida_ate = timezone.now() - timedelta(minutes=1)
        expirada.save(update_fields=["valida_ate"])
        revogada = self.criar_credencial(token="REVOGADA")
        revogada.revogar()
        self.criar_credencial(usuario=self.supervisor_externo, token="OUTRA-EMPRESA")

        for dados in (
            {"supervisor_credencial": "COM-PIN", "supervisor_pin": "errado"},
            {"supervisor_credencial": "EXPIRADA"},
            {"supervisor_credencial": "REVOGADA"},
            {"supervisor_credencial": "OUTRA-EMPRESA"},
        ):
            request = self.factory.post("/pdv/protegido/", dados)
            request.user = self.operador
            with self.assertRaises(ValidationError):
                supervisor_from_request(request)
        self.assertFalse(UsoCredencialAutorizacao.objects.exists())

    def test_admin_nao_cadastra_credencial_para_usuario_de_outra_empresa(self):
        response = self.client.post(
            "/usuarios/credenciais-autorizacao/",
            {
                "usuario": self.supervisor_externo.pk,
                "tipo": TipoCredencialAutorizacao.CODIGO_BARRAS,
                "nome": "Tentativa externa",
                "identificador": "EXTERNO-001",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(CredencialAutorizacao.objects.exists())
        self.assertIn("usuario", response.context["form"].errors)


    def test_politica_padrao_exige_pin_em_estorno_e_registra_acao(self):
        credencial_sem_pin = self.criar_credencial(token="SEM-PIN")
        request = self.factory.post(
            "/pdv/estorno/",
            {"supervisor_credencial": "SEM-PIN"},
        )
        request.user = self.operador
        with self.assertRaisesMessage(ValidationError, "credencial cadastrada com PIN"):
            supervisor_from_request(request, acao=AcaoPinSupervisor.PDV_ESTORNO)
        self.assertFalse(UsoCredencialAutorizacao.objects.filter(credencial=credencial_sem_pin).exists())

        credencial_com_pin = self.criar_credencial(token="COM-PIN-ESTORNO", pin="7788")
        request = self.factory.post(
            "/pdv/estorno/",
            {"supervisor_credencial": "COM-PIN-ESTORNO", "supervisor_pin": "7788"},
        )
        request.user = self.operador
        usuario = supervisor_from_request(request, acao=AcaoPinSupervisor.PDV_ESTORNO)

        self.assertEqual(usuario, self.supervisor)
        uso = UsoCredencialAutorizacao.objects.get(credencial=credencial_com_pin)
        self.assertEqual(uso.acao, AcaoPinSupervisor.PDV_ESTORNO)

    def test_login_e_senha_continuam_como_contingencia_em_acao_com_pin(self):
        request = self.factory.post(
            "/pdv/estorno/",
            {"supervisor_usuario": self.supervisor.username, "supervisor_senha": "123"},
        )
        request.user = self.operador

        usuario = supervisor_from_request(request, acao=AcaoPinSupervisor.PDV_ESTORNO)

        self.assertEqual(usuario, self.supervisor)
        self.assertFalse(UsoCredencialAutorizacao.objects.exists())

    def test_admin_configura_acoes_que_exigem_pin_na_propria_empresa(self):
        pagina = self.client.get("/usuarios/credenciais-autorizacao/")
        self.assertContains(pagina, "Política de cartão e PIN")

        resposta = self.client.post(
            "/usuarios/credenciais-autorizacao/",
            {
                "acao_form": "politica_pin",
                "acoes_credencial_exigem_pin": [
                    AcaoPinSupervisor.PDV_ESTORNO,
                    AcaoPinSupervisor.PDV_DESCONTO,
                ],
            },
        )

        self.assertRedirects(resposta, "/usuarios/credenciais-autorizacao/")
        self.empresa.refresh_from_db()
        self.assertEqual(
            self.empresa.acoes_credencial_exigem_pin,
            [AcaoPinSupervisor.PDV_DESCONTO, AcaoPinSupervisor.PDV_ESTORNO],
        )
        self.assertTrue(
            LogAuditoria.objects.filter(
                acao="ALTERA_POLITICA_PIN_SUPERVISOR",
                objeto_tipo="Empresa",
                objeto_id=str(self.empresa.pk),
            ).exists()
        )


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
        EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend",
        EMAIL_HOST="",
        DEFAULT_FROM_EMAIL="nao-responda@teste.local",
    )
    def test_comando_estrito_bloqueia_backend_de_desenvolvimento(self):
        with self.assertRaises(CommandError):
            call_command("verificar_prontidao_recuperacao_senha", "--estrito", stdout=StringIO())

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
    def test_comando_estrito_aceita_smtp_sem_expor_credenciais(self):
        saida = StringIO()
        call_command("verificar_prontidao_recuperacao_senha", "--estrito", "--json", stdout=saida)
        conteudo = saida.getvalue()
        self.assertIn("password_reset_readiness_v1", conteudo)
        self.assertNotIn("smtp.example.com", conteudo)
        self.assertNotIn("usuario@example.com", conteudo)
        self.assertNotIn("segredo", conteudo)



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

class UsuariosEscopoEmpresaTests(TestCase):
    def setUp(self):
        self.client = Client(HTTP_HOST="localhost")
        self.empresa = Empresa.objects.create(
            razao_social="Empresa Um Ltda",
            nome_fantasia="Empresa Um",
            cnpj="11.111.111/0001-11",
        )
        self.filial = Filial.objects.create(empresa=self.empresa, nome="Matriz Um", cnpj=self.empresa.cnpj)
        self.outra_empresa = Empresa.objects.create(
            razao_social="Empresa Dois Ltda",
            nome_fantasia="Empresa Dois",
            cnpj="22.222.222/0001-22",
        )
        self.outra_filial = Filial.objects.create(
            empresa=self.outra_empresa,
            nome="Matriz Dois",
            cnpj=self.outra_empresa.cnpj,
        )
        self.admin_empresa = get_user_model().objects.create_user("admin_empresa", password="123")
        PerfilUsuario.objects.create(
            usuario=self.admin_empresa,
            filial=self.filial,
            tipo=TipoPerfil.ADMINISTRADOR,
        )
        self.usuario_proprio = get_user_model().objects.create_user("caixa_empresa_um", password="123")
        PerfilUsuario.objects.create(
            usuario=self.usuario_proprio,
            filial=self.filial,
            tipo=TipoPerfil.OPERADOR_CAIXA,
        )
        self.usuario_estrangeiro = get_user_model().objects.create_user("caixa_empresa_dois", password="123")
        PerfilUsuario.objects.create(
            usuario=self.usuario_estrangeiro,
            filial=self.outra_filial,
            tipo=TipoPerfil.OPERADOR_CAIXA,
        )
        self.super_admin = get_user_model().objects.create_superuser("software_owner", password="123")
        self.client.force_login(self.admin_empresa)

    def test_admin_empresa_lista_e_edita_somente_sua_equipe(self):
        response = self.client.get("/usuarios/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "caixa_empresa_um")
        self.assertNotContains(response, "caixa_empresa_dois")
        self.assertNotContains(response, "software_owner")
        self.assertEqual(self.client.get(f"/usuarios/{self.usuario_proprio.pk}/editar/").status_code, 200)
        self.assertEqual(self.client.get(f"/usuarios/{self.usuario_estrangeiro.pk}/editar/").status_code, 404)
        self.assertEqual(self.client.get(f"/usuarios/{self.super_admin.pk}/editar/").status_code, 404)

    def test_admin_empresa_so_pode_vincular_usuario_a_filial_propria(self):
        form = self.client.get("/usuarios/novo/")
        self.assertContains(form, "Matriz Um")
        self.assertNotContains(form, "Matriz Dois")
        self.assertNotContains(form, 'name="is_staff"')

        response = self.client.post(
            "/usuarios/novo/",
            {
                "username": "tentativa_outra_empresa",
                "password": "Senha-segura-123",
                "tipo": TipoPerfil.OPERADOR_CAIXA,
                "filial": self.outra_filial.pk,
                "is_active": "on",
                "is_staff": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Faça uma escolha válida")
        self.assertFalse(get_user_model().objects.filter(username="tentativa_outra_empresa").exists())

    def test_admin_empresa_cria_usuario_proprio_sem_acesso_staff(self):
        response = self.client.post(
            "/usuarios/novo/",
            {
                "username": "novo_caixa_local",
                "password": "Senha-segura-123",
                "tipo": TipoPerfil.OPERADOR_CAIXA,
                "filial": self.filial.pk,
                "is_active": "on",
                "is_staff": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        usuario = get_user_model().objects.get(username="novo_caixa_local")
        self.assertEqual(usuario.perfil_supermercado.filial, self.filial)
        self.assertFalse(usuario.is_staff)

    def test_super_admin_mantem_visao_global(self):
        self.client.force_login(self.super_admin)

        lista = self.client.get("/usuarios/")
        form = self.client.get("/usuarios/novo/")

        self.assertContains(lista, "caixa_empresa_um")
        self.assertContains(lista, "caixa_empresa_dois")
        self.assertContains(form, "Matriz Um")
        self.assertContains(form, "Matriz Dois")
        self.assertContains(form, 'name="is_staff"')

class GovernancaCadastroUsuarioTests(TestCase):
    def setUp(self):
        User = get_user_model()
        empresa = Empresa.objects.create(razao_social="Empresa Governada", nome_fantasia="Empresa Governada", cnpj="50123456000110")
        self.filial = Filial.objects.create(empresa=empresa, nome="Matriz Governada")
        self.admin = User.objects.create_user("admin_governanca", password="123")
        PerfilUsuario.objects.create(usuario=self.admin, filial=self.filial, tipo=TipoPerfil.ADMINISTRADOR)
        self.gerente = User.objects.create_user("gerente_governanca", password="123")
        PerfilUsuario.objects.create(usuario=self.gerente, filial=self.filial, tipo=TipoPerfil.GERENTE)

    def test_admin_nao_cria_usuario_sem_filial(self):
        self.client.force_login(self.admin)
        response = self.client.post("/usuarios/novo/", {
            "username": "usuario_sem_filial", "password": "Senha-123-forte",
            "tipo": TipoPerfil.OPERADOR_CAIXA, "is_active": "on",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(get_user_model().objects.filter(username="usuario_sem_filial").exists())
        self.assertIn("filial", response.context["form"].errors)

    def test_gerente_nao_gerencia_usuarios(self):
        self.client.force_login(self.gerente)
        self.assertEqual(self.client.get("/usuarios/").status_code, 403)
        self.assertEqual(self.client.get("/usuarios/novo/").status_code, 403)