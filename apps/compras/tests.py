from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.empresas.models import Empresa, Filial
from apps.financeiro.models import ContaFinanceira, StatusContaFinanceira, TipoContaFinanceira
from apps.fornecedores.models import Fornecedor
from apps.produtos.models import Categoria, Produto

from .models import EntradaCompra, ItemEntradaCompra, StatusEntradaCompra
from .services import finalizar_entrada_compra


class ComprasFinanceiroTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(username="compras", password="123")
        self.admin = get_user_model().objects.create_superuser("admin", "admin@example.com", "123")
        self.empresa = Empresa.objects.create(razao_social="Mercado Compra", nome_fantasia="Mercado Compra", cnpj="55.555.555/0001-55")
        self.filial = Filial.objects.create(empresa=self.empresa, nome="Matriz", cnpj=self.empresa.cnpj)
        self.fornecedor = Fornecedor.objects.create(razao_social="Fornecedor Teste Ltda", nome_fantasia="Fornecedor Teste")
        self.categoria = Categoria.all_objects.create(nome="Mercearia Compra")
        self.produto = Produto.objects.create(
            codigo_barras="7895555555555",
            nome="Feijao 1kg",
            categoria=self.categoria,
            preco_custo=Decimal("4.00"),
            preco_venda=Decimal("8.00"),
        )

    def test_finalizar_compra_cria_conta_a_pagar(self):
        vencimento = timezone.localdate()
        entrada = EntradaCompra.objects.create(
            fornecedor=self.fornecedor,
            filial=self.filial,
            usuario=self.usuario,
            numero_documento="NF-100",
            vencimento_financeiro=vencimento,
        )
        ItemEntradaCompra.objects.create(
            entrada=entrada,
            produto=self.produto,
            quantidade=Decimal("3.000"),
            custo_unitario=Decimal("5.00"),
            total=Decimal("15.00"),
        )

        finalizar_entrada_compra(entrada)

        entrada.refresh_from_db()
        self.assertEqual(entrada.status, StatusEntradaCompra.FINALIZADA)
        conta = ContaFinanceira.objects.get(entrada_compra=entrada)
        self.assertEqual(conta.tipo, TipoContaFinanceira.PAGAR)
        self.assertEqual(conta.status, StatusContaFinanceira.ABERTA)
        self.assertEqual(conta.valor, Decimal("15.00"))
        self.assertEqual(conta.vencimento, vencimento)
        self.assertEqual(conta.fornecedor, self.fornecedor)

    def test_form_entrada_exibe_secoes_operacionais(self):
        self.client.force_login(self.admin)

        response = self.client.get("/compras/nova/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dados da entrada")
        self.assertContains(response, "Itens recebidos")
        self.assertContains(response, "Ao finalizar, o sistema atualiza estoque e financeiro.")
        self.assertContains(response, "select2-field")

# Create your tests here.
