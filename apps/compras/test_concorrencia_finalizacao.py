from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import close_old_connections, connection
from django.test import TransactionTestCase

from apps.empresas.models import Empresa, Filial
from apps.estoque.models import Estoque, MovimentacaoEstoque
from apps.financeiro.models import ContaFinanceira
from apps.fornecedores.models import Fornecedor
from apps.produtos.models import Categoria, Produto

from .models import EntradaCompra, ItemEntradaCompra, PedidoCompra, StatusEntradaCompra, StatusPedidoCompra
from .services import finalizar_entrada_compra


@skipUnless(
    connection.vendor == "postgresql",
    "Este teste exige PostgreSQL real; SQLite não comprova select_for_update.",
)
class FinalizacaoEntradaCompraConcorrenciaPostgreSQLTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.usuario = get_user_model().objects.create_user(username="compras-concorrencia")
        self.empresa = Empresa.objects.create(
            razao_social="Mercado Concorrencia LTDA",
            nome_fantasia="Mercado Concorrencia",
            cnpj="45.678.901/0001-23",
        )
        self.filial = Filial.objects.create(
            empresa=self.empresa,
            nome="Matriz concorrencia",
            cnpj=self.empresa.cnpj,
        )
        self.fornecedor = Fornecedor.objects.create(
            razao_social="Fornecedor Concorrencia LTDA",
            nome_fantasia="Fornecedor Concorrencia",
        )
        categoria = Categoria.all_objects.create(nome="Concorrencia compras")
        self.produto = Produto.objects.create(
            codigo_barras="7894567890123",
            nome="Produto concorrente",
            categoria=categoria,
            preco_custo=Decimal("8.00"),
            preco_venda=Decimal("12.00"),
        )
        Estoque.objects.create(
            produto=self.produto,
            filial=self.filial,
            quantidade_atual=Decimal("4.000"),
            custo_medio=Decimal("8.000000"),
        )
        self.pedido = PedidoCompra.objects.create(
            fornecedor=self.fornecedor,
            filial=self.filial,
            usuario=self.usuario,
            referencia="PED-CONCORRENCIA",
            status=StatusPedidoCompra.CONVERTIDO,
            total_previsto=Decimal("30.00"),
        )
        self.entrada = EntradaCompra.objects.create(
            pedido_origem=self.pedido,
            fornecedor=self.fornecedor,
            filial=self.filial,
            usuario=self.usuario,
            numero_documento="NF-CONCORRENCIA",
            status=StatusEntradaCompra.RASCUNHO,
        )
        ItemEntradaCompra.objects.create(
            entrada=self.entrada,
            produto=self.produto,
            quantidade=Decimal("3.000"),
            custo_unitario=Decimal("10.00"),
            total=Decimal("30.00"),
        )

    def test_duas_conexoes_finalizam_entrada_uma_unica_vez(self):
        inicio_simultaneo = Barrier(3)

        def tentar_finalizar():
            close_old_connections()
            try:
                entrada = EntradaCompra.objects.get(pk=self.entrada.pk)
                inicio_simultaneo.wait(timeout=10)
                finalizar_entrada_compra(entrada)
                return "finalizada"
            except ValidationError as exc:
                return f"rejeitada:{' '.join(exc.messages)}"
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            tentativas = [executor.submit(tentar_finalizar) for _ in range(2)]
            inicio_simultaneo.wait(timeout=10)
            resultados = [tentativa.result(timeout=30) for tentativa in tentativas]

        self.assertEqual(resultados.count("finalizada"), 1)
        rejeicoes = [resultado for resultado in resultados if resultado.startswith("rejeitada:")]
        self.assertEqual(len(rejeicoes), 1)
        self.assertIn("Apenas entradas em rascunho", rejeicoes[0])

        self.entrada.refresh_from_db()
        self.pedido.refresh_from_db()
        estoque = Estoque.objects.get(produto=self.produto, filial=self.filial)
        movimentos = MovimentacaoEstoque.objects.filter(referencia=f"entrada_compra:{self.entrada.pk}")

        self.assertEqual(self.entrada.status, StatusEntradaCompra.FINALIZADA)
        self.assertEqual(self.entrada.total_produtos, Decimal("30.00"))
        self.assertEqual(estoque.quantidade_atual, Decimal("7.000"))
        self.assertEqual(movimentos.count(), 1)
        self.assertEqual(movimentos.get().quantidade, Decimal("3.000"))
        self.assertEqual(ContaFinanceira.objects.filter(entrada_compra=self.entrada).count(), 1)
        self.assertEqual(self.pedido.status, StatusPedidoCompra.CONVERTIDO)
