from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipIf
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection, connections
from django.test import TestCase, TransactionTestCase

from apps.empresas.models import Empresa, Filial
from apps.estoque.models import Estoque, MovimentacaoEstoque
from apps.financeiro.models import LancamentoFinanceiro
from apps.pdv.models import Caixa
from apps.produtos.models import Categoria, Produto

from .models import CheckoutIntent, FormaPagamento, PagamentoVenda, Venda
from .services import finalizar_venda_idempotente


class CheckoutIdempotencyTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(username="checkout", password="teste")
        empresa = Empresa.objects.create(
            razao_social="Mercado Checkout", nome_fantasia="Checkout", cnpj="12.345.678/0001-95",
        )
        self.filial = Filial.objects.create(empresa=empresa, nome="Matriz", cnpj=empresa.cnpj)
        categoria = Categoria.all_objects.create(nome="Checkout")
        self.produto = Produto.objects.create(
            codigo_barras="7890000000199", nome="Item", categoria=categoria,
            preco_custo=Decimal("5"), preco_venda=Decimal("10"),
        )
        Estoque.objects.create(produto=self.produto, filial=self.filial, quantidade_atual=Decimal("10"))
        self.caixa = Caixa.objects.create(filial=self.filial, usuario_abertura=self.usuario)
        self.dinheiro = FormaPagamento.objects.create(nome="Dinheiro checkout", tipo="DINHEIRO")

    def finalizar(self, chave, assinatura="mesmo-post", assinatura_carrinho="mesmo-carrinho", **kwargs):
        return finalizar_venda_idempotente(
            chave=chave, assinatura_requisicao=assinatura, assinatura_carrinho=assinatura_carrinho,
            terminal_identificador="",
            caixa=self.caixa, usuario=self.usuario,
            itens=[{"produto": self.produto, "quantidade": Decimal("1.000")}],
            pagamentos=[{"forma_pagamento": self.dinheiro, "valor": Decimal("10.00")}],
            preparar_fiscal=False, **kwargs,
        )

    def test_mesma_chave_retorna_a_mesma_venda_sem_repetir_efeitos(self):
        chave = uuid4()
        primeira, criada = self.finalizar(chave)
        segunda, repetida = self.finalizar(chave)

        self.assertTrue(criada)
        self.assertFalse(repetida)
        self.assertEqual(primeira.pk, segunda.pk)
        self.assertEqual(Venda.objects.count(), 1)
        self.assertEqual(PagamentoVenda.objects.count(), 1)
        self.assertEqual(MovimentacaoEstoque.objects.filter(tipo="VENDA").count(), 1)
        self.assertEqual(LancamentoFinanceiro.objects.filter(pagamento_venda__venda=primeira).count(), 1)
        self.assertEqual(CheckoutIntent.objects.get(chave=chave).venda_id, primeira.pk)

    def test_chave_diferente_permite_nova_venda(self):
        primeira, _ = self.finalizar(uuid4())
        segunda, _ = self.finalizar(uuid4())
        self.assertNotEqual(primeira.pk, segunda.pk)
        self.assertEqual(Venda.objects.count(), 2)

    def test_retry_nao_repete_preparacao_fiscal_local(self):
        chave = uuid4()
        with patch("apps.vendas.services._preparar_documento_fiscal_pos_venda") as preparar:
            dados = {
                "chave": chave, "assinatura_requisicao": "mesmo-post", "assinatura_carrinho": "mesmo-carrinho",
                "terminal_identificador": "", "caixa": self.caixa, "usuario": self.usuario,
                "itens": [{"produto": self.produto, "quantidade": Decimal("1.000")}],
                "pagamentos": [{"forma_pagamento": self.dinheiro, "valor": Decimal("10.00")}],
            }
            finalizar_venda_idempotente(**dados)
            finalizar_venda_idempotente(**dados)
        preparar.assert_called_once()

    def test_mesma_chave_com_requisicao_diferente_e_rejeitada(self):
        chave = uuid4()
        self.finalizar(chave)
        with self.assertRaisesMessage(ValidationError, "outra tentativa"):
            self.finalizar(chave, assinatura="post-alterado")
        self.assertEqual(Venda.objects.count(), 1)

    def test_mesma_chave_com_carrinho_alterado_e_rejeitada(self):
        chave = uuid4()
        self.finalizar(chave)
        with self.assertRaisesMessage(ValidationError, "outra tentativa"):
            self.finalizar(chave, assinatura_carrinho="outro-carrinho")

    def test_falha_na_venda_nao_consome_chave_e_permite_retry(self):
        chave = uuid4()
        with self.assertRaises(ValidationError):
            finalizar_venda_idempotente(
                chave=chave, assinatura_requisicao="mesmo-post", assinatura_carrinho="mesmo-carrinho",
                terminal_identificador="",
                caixa=self.caixa, usuario=self.usuario,
                itens=[{"produto": self.produto, "quantidade": Decimal("1.000")}],
                pagamentos=[{"forma_pagamento": self.dinheiro, "valor": Decimal("1.00")}],
                preparar_fiscal=False,
            )
        self.assertFalse(CheckoutIntent.objects.filter(chave=chave).exists())
        venda, criada = self.finalizar(chave)
        self.assertTrue(criada)
        self.assertEqual(Venda.objects.count(), 1)
        self.assertEqual(CheckoutIntent.objects.get(chave=chave).venda_id, venda.pk)


@skipIf(connection.vendor == "sqlite", "SQLite nao implementa SELECT FOR UPDATE por linha")
class CheckoutConcurrencyTests(TransactionTestCase):
    setUp = CheckoutIdempotencyTests.setUp
    finalizar = CheckoutIdempotencyTests.finalizar

    def test_dois_posts_concorrentes_criam_uma_venda(self):
        chave = uuid4()
        inicio = Barrier(2)

        def executar():
            try:
                inicio.wait(timeout=10)
                venda, criada = self.finalizar(chave)
                return venda.pk, criada
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            resultados = list(executor.map(lambda _: executar(), range(2)))

        self.assertEqual(resultados[0][0], resultados[1][0])
        self.assertEqual(sorted(criada for _, criada in resultados), [False, True])
        self.assertEqual(Venda.objects.count(), 1)
        self.assertEqual(PagamentoVenda.objects.count(), 1)
