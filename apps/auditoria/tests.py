from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone

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
