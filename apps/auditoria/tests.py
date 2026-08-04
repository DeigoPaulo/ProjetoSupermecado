from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone

from apps.accounts.models import PerfilUsuario, TipoPerfil
from apps.empresas.models import Empresa, Filial

from .models import LogAuditoria


class AuditoriaViewsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser("admin", "admin@example.com", "123")
        self.client = Client(HTTP_HOST="localhost")
        self.client.force_login(self.user)
        LogAuditoria.objects.create(
            usuario=self.user,
            modulo="estoque",
            acao="AJUSTE_ESTOQUE",
            descricao="Ajuste manual autorizado pelo supervisor.",
            objeto_tipo="MovimentacaoEstoque",
            objeto_id="10",
            ip="127.0.0.1",
        )
        LogAuditoria.objects.create(
            usuario=self.user,
            modulo="vendas",
            acao="CANCELAMENTO_VENDA",
            descricao="Cancelamento de venda autorizado.",
            objeto_tipo="Venda",
            objeto_id="20",
            ip="127.0.0.1",
        )

    def test_lista_logs_com_filtros(self):
        hoje = timezone.localdate()
        response = self.client.get(
            "/auditoria/",
            {
                "data_inicio": hoje.isoformat(),
                "data_fim": hoje.isoformat(),
                "modulo": "estoque",
                "q": "manual",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Auditoria")
        self.assertContains(response, "AJUSTE_ESTOQUE")
        self.assertNotContains(response, "Cancelamento de venda autorizado.")

    def test_exporta_logs_csv(self):
        hoje = timezone.localdate()
        response = self.client.get(
            "/auditoria/exportar.csv",
            {"data_inicio": hoje.isoformat(), "data_fim": hoje.isoformat(), "modulo": "vendas"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("auditoria_", response["Content-Disposition"])
        self.assertIn(b"CANCELAMENTO_VENDA", response.content)
        self.assertNotIn(b"AJUSTE_ESTOQUE", response.content)

# Create your tests here.

class AuditoriaEscopoEPaginacaoTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.empresa = Empresa.objects.create(razao_social="Empresa Auditada", nome_fantasia="Empresa Auditada", cnpj="30123456000110")
        self.filial = Filial.objects.create(empresa=self.empresa, nome="Matriz Auditada")
        outra = Empresa.objects.create(razao_social="Outra Empresa", nome_fantasia="Outra Empresa", cnpj="40123456000110")
        outra_filial = Filial.objects.create(empresa=outra, nome="Outra Matriz")
        self.admin = User.objects.create_user("admin_auditoria", password="123")
        PerfilUsuario.objects.create(usuario=self.admin, filial=self.filial, tipo=TipoPerfil.ADMINISTRADOR)
        self.outro_admin = User.objects.create_user("outro_admin_auditoria", password="123")
        PerfilUsuario.objects.create(usuario=self.outro_admin, filial=outra_filial, tipo=TipoPerfil.ADMINISTRADOR)
        self.gerente = User.objects.create_user("gerente_auditoria", password="123")
        PerfilUsuario.objects.create(usuario=self.gerente, filial=self.filial, tipo=TipoPerfil.GERENTE)
        LogAuditoria.objects.bulk_create([
            LogAuditoria(usuario=self.admin, modulo="teste", acao=f"ACAO_PROPRIA_{i:02d}", descricao="Registro da empresa pr?pria")
            for i in range(55)
        ])
        LogAuditoria.objects.create(usuario=self.outro_admin, modulo="teste", acao="ACAO_ESTRANGEIRA", descricao="Registro de outra empresa")

    def test_admin_ve_so_a_propria_empresa_e_cinquenta_por_pagina(self):
        self.client.force_login(self.admin)
        primeira = self.client.get("/auditoria/")
        segunda = self.client.get("/auditoria/", {"page": 2})

        self.assertEqual(primeira.status_code, 200)
        self.assertEqual(len(primeira.context["pagina"]), 50)
        self.assertEqual(primeira.context["pagina"].paginator.count, 55)
        self.assertEqual(len(segunda.context["pagina"]), 5)
        self.assertNotContains(primeira, "ACAO_ESTRANGEIRA")
        csv = self.client.get("/auditoria/exportar.csv")
        self.assertNotIn(b"ACAO_ESTRANGEIRA", csv.content)

    def test_gerente_nao_acessa_auditoria_administrativa(self):
        self.client.force_login(self.gerente)
        self.assertEqual(self.client.get("/auditoria/").status_code, 403)
        self.assertEqual(self.client.get("/auditoria/exportar.csv").status_code, 403)