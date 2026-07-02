from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone

from apps.auditoria.models import LogAuditoria
from apps.empresas.models import Empresa, Filial
from apps.pdv.models import Caixa
from apps.vendas.models import FormaPagamento, PagamentoVenda, StatusVenda, Venda

from .models import CategoriaFinanceira, ContaFinanceira, StatusContaFinanceira, TipoContaFinanceira
from .services import baixar_conta, cancelar_conta


class FinanceiroTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser("admin", "admin@example.com", "123")
        self.client = Client(HTTP_HOST="localhost")
        self.client.force_login(self.user)
        self.empresa = Empresa.objects.create(razao_social="Mercado Teste", nome_fantasia="Mercado", cnpj="33.333.333/0001-33")
        self.filial = Filial.objects.create(empresa=self.empresa, nome="Matriz", cnpj=self.empresa.cnpj)
        self.categoria = CategoriaFinanceira.objects.create(nome="Mercadorias", tipo=TipoContaFinanceira.PAGAR)
        self.conta = ContaFinanceira.objects.create(
            tipo=TipoContaFinanceira.PAGAR,
            descricao="Compra de mercadorias",
            categoria=self.categoria,
            filial=self.filial,
            valor=Decimal("150.00"),
            vencimento=timezone.localdate(),
            usuario=self.user,
        )
        self.conta_receber = ContaFinanceira.objects.create(
            tipo=TipoContaFinanceira.RECEBER,
            descricao="Crediario cliente",
            filial=self.filial,
            valor=Decimal("210.00"),
            vencimento=timezone.localdate(),
            usuario=self.user,
        )

    def test_baixa_conta_e_registra_auditoria(self):
        baixar_conta(
            conta=self.conta,
            usuario=self.user,
            data_pagamento=timezone.localdate(),
            valor_pago=Decimal("150.00"),
            forma_pagamento="Pix",
        )

        self.conta.refresh_from_db()
        self.assertEqual(self.conta.status, StatusContaFinanceira.PAGA)
        self.assertEqual(self.conta.valor_pago, Decimal("150.00"))
        self.assertTrue(LogAuditoria.objects.filter(modulo="financeiro", acao="BAIXA_CONTA").exists())

    def test_cancelar_conta_aberta(self):
        cancelar_conta(conta=self.conta, usuario=self.user, motivo="Duplicidade")

        self.conta.refresh_from_db()
        self.assertEqual(self.conta.status, StatusContaFinanceira.CANCELADA)
        self.assertIn("Duplicidade", self.conta.observacoes)

    def test_tela_financeiro_lista_contas(self):
        response = self.client.get("/financeiro/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Financeiro")
        self.assertContains(response, "Compra de mercadorias")
        self.assertContains(response, "Saldo previsto")

    def test_exporta_financeiro_csv_e_pdf(self):
        response_csv = self.client.get("/financeiro/exportar.csv")
        response_pdf = self.client.get("/financeiro/imprimir/")

        self.assertEqual(response_csv.status_code, 200)
        self.assertEqual(response_csv["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("financeiro_", response_csv["Content-Disposition"])
        self.assertIn(b"Compra de mercadorias", response_csv.content)
        self.assertEqual(response_pdf.status_code, 200)
        self.assertContains(response_pdf, "Imprimir / Salvar como PDF")
        self.assertContains(response_pdf, "Compra de mercadorias")

    def test_fluxo_caixa_e_exportacao(self):
        response = self.client.get("/financeiro/fluxo-caixa/")
        response_csv = self.client.get("/financeiro/fluxo-caixa/exportar.csv")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Fluxo de caixa")
        self.assertContains(response, "Saldo previsto")
        self.assertContains(response, "210,00")
        self.assertEqual(response_csv.status_code, 200)
        self.assertEqual(response_csv["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn(b"Saldo previsto", response_csv.content)

    def test_conciliacao_soma_pdv_recebimentos_e_saidas(self):
        caixa = Caixa.objects.create(filial=self.filial, usuario_abertura=self.user, valor_inicial=Decimal("100.00"))
        forma = FormaPagamento.objects.create(nome="Dinheiro", tipo="DINHEIRO", permite_troco=True)
        venda = Venda.objects.create(
            filial=self.filial,
            caixa=caixa,
            usuario=self.user,
            total_bruto=Decimal("70.00"),
            total_liquido=Decimal("70.00"),
            status=StatusVenda.FINALIZADA,
        )
        PagamentoVenda.objects.create(venda=venda, forma_pagamento=forma, valor=Decimal("70.00"))
        baixar_conta(
            conta=self.conta_receber,
            usuario=self.user,
            data_pagamento=timezone.localdate(),
            valor_pago=Decimal("210.00"),
            forma_pagamento="Pix",
        )
        baixar_conta(
            conta=self.conta,
            usuario=self.user,
            data_pagamento=timezone.localdate(),
            valor_pago=Decimal("150.00"),
            forma_pagamento="Pix",
        )

        response = self.client.get("/financeiro/conciliacao/")
        response_csv = self.client.get("/financeiro/conciliacao/exportar.csv")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Conciliação financeira")
        self.assertContains(response, "Entradas PDV")
        self.assertContains(response, "130,00")
        self.assertEqual(response_csv.status_code, 200)
        self.assertEqual(response_csv["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn(b"Saldo operacional", response_csv.content)
