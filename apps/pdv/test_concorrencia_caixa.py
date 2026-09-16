from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Event
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import close_old_connections, connection, transaction
from django.test import TestCase, TransactionTestCase

from apps.empresas.models import Empresa, Filial
from apps.estoque.models import Estoque, MovimentacaoEstoque
from apps.financeiro.models import ContaMovimentoFinanceiro, LancamentoFinanceiro, TipoContaMovimento
from apps.produtos.models import Categoria, Produto
from apps.vendas.models import FormaPagamento, FormaPagamentoFilial, Venda
from apps.vendas.services import finalizar_venda

from .models import Caixa, Sangria, StatusCaixa, Suprimento
from .services_caixa import fechar_caixa_operacional, registrar_sangria_caixa, registrar_suprimento_caixa


class CaixaConcorrenciaFixtureMixin:
    def criar_dados(self):
        self.usuario = get_user_model().objects.create_user(username="caixa-concorrencia")
        self.empresa = Empresa.objects.create(
            razao_social="Mercado Caixa Concorrencia LTDA",
            nome_fantasia="Mercado Caixa Concorrencia",
            cnpj="56.789.012/0001-34",
        )
        self.filial = Filial.objects.create(
            empresa=self.empresa,
            nome="Matriz concorrencia caixa",
            cnpj=self.empresa.cnpj,
        )
        categoria = Categoria.all_objects.create(nome="Concorrencia caixa")
        self.produto = Produto.objects.create(
            codigo_barras="7895678901234",
            nome="Produto concorrencia caixa",
            categoria=categoria,
            preco_custo=Decimal("6.00"),
            preco_venda=Decimal("10.00"),
        )
        Estoque.objects.create(
            produto=self.produto,
            filial=self.filial,
            quantidade_atual=Decimal("10.000"),
        )
        self.caixa = Caixa.objects.create(
            filial=self.filial,
            usuario_abertura=self.usuario,
            valor_inicial=Decimal("100.00"),
        )
        self.dinheiro = FormaPagamento.objects.filter(tipo="DINHEIRO").first()
        if self.dinheiro is None:
            self.dinheiro = FormaPagamento.objects.create(
                nome="Dinheiro concorrencia caixa",
                tipo="DINHEIRO",
            )
        FormaPagamentoFilial.objects.get_or_create(
            filial=self.filial,
            forma_pagamento=self.dinheiro,
            defaults={"ativo": True},
        )
        ContaMovimentoFinanceiro.objects.create(
            filial=self.filial,
            nome="Caixa PDV",
            tipo=TipoContaMovimento.CAIXA,
        )


class CaixaFechadoServicesTests(CaixaConcorrenciaFixtureMixin, TestCase):
    def setUp(self):
        self.criar_dados()
        fechar_caixa_operacional(
            caixa=self.caixa,
            usuario=self.usuario,
            valor_final=Decimal("100.00"),
        )

    def test_caixa_fechado_recusa_venda_sem_efeitos_parciais(self):
        with self.assertRaisesMessage(ValidationError, "Este caixa não está aberto"):
            finalizar_venda(
                caixa=self.caixa,
                usuario=self.usuario,
                itens=[{"produto": self.produto, "quantidade": Decimal("1.000")}],
                pagamentos=[{"forma_pagamento": self.dinheiro, "valor": Decimal("10.00")}],
                preparar_fiscal=False,
            )

        self.assertFalse(Venda.objects.exists())
        self.assertFalse(MovimentacaoEstoque.objects.exists())
        estoque = Estoque.objects.get(produto=self.produto, filial=self.filial)
        self.assertEqual(estoque.quantidade_atual, Decimal("10.000"))

    def test_caixa_fechado_recusa_movimentos_e_novo_fechamento(self):
        operacoes = (
            lambda: registrar_sangria_caixa(
                caixa=self.caixa, usuario=self.usuario, valor=Decimal("5.00"), motivo="Teste"
            ),
            lambda: registrar_suprimento_caixa(
                caixa=self.caixa, usuario=self.usuario, valor=Decimal("7.00"), motivo="Teste"
            ),
            lambda: fechar_caixa_operacional(
                caixa=self.caixa, usuario=self.usuario, valor_final=Decimal("100.00")
            ),
        )

        for operacao in operacoes:
            with self.assertRaisesMessage(ValidationError, "Este caixa não está aberto"):
                operacao()

        self.assertFalse(Sangria.objects.exists())
        self.assertFalse(Suprimento.objects.exists())
        self.assertFalse(LancamentoFinanceiro.objects.exists())


@skipUnless(connection.vendor == "postgresql", "Concorrência real exige PostgreSQL.")
class CaixaConcorrenciaPostgreSQLTests(CaixaConcorrenciaFixtureMixin, TransactionTestCase):
    def setUp(self):
        self.criar_dados()

    def _fechar_mantendo_lock(self, lock_adquirido, liberar):
        close_old_connections()
        try:
            with transaction.atomic():
                caixa = Caixa.objects.select_for_update().get(pk=self.caixa.pk)
                lock_adquirido.set()
                if not liberar.wait(timeout=15):
                    raise TimeoutError("Teste não liberou o fechamento.")
                fechar_caixa_operacional(
                    caixa=caixa,
                    usuario=get_user_model().objects.get(pk=self.usuario.pk),
                    valor_final=Decimal("100.00"),
                )
            return "fechado"
        finally:
            close_old_connections()

    def test_fechamento_vence_corrida_e_venda_nao_produz_efeito_parcial(self):
        lock_adquirido = Event()
        liberar = Event()

        def vender():
            close_old_connections()
            try:
                try:
                    finalizar_venda(
                        caixa=Caixa.objects.get(pk=self.caixa.pk),
                        usuario=get_user_model().objects.get(pk=self.usuario.pk),
                        itens=[
                            {
                                "produto": Produto.objects.get(pk=self.produto.pk),
                                "quantidade": Decimal("1.000"),
                            }
                        ],
                        pagamentos=[
                            {
                                "forma_pagamento": FormaPagamento.objects.get(pk=self.dinheiro.pk),
                                "valor": Decimal("10.00"),
                            }
                        ],
                        preparar_fiscal=False,
                    )
                    return "vendida"
                except ValidationError as exc:
                    return f"rejeitada:{' '.join(exc.messages)}"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            fechamento = executor.submit(self._fechar_mantendo_lock, lock_adquirido, liberar)
            self.assertTrue(lock_adquirido.wait(timeout=15))
            venda = executor.submit(vender)
            liberar.set()
            self.assertEqual(fechamento.result(timeout=30), "fechado")
            resultado_venda = venda.result(timeout=30)

        self.assertIn("Este caixa não está aberto", resultado_venda)
        self.assertFalse(Venda.objects.exists())
        self.assertFalse(MovimentacaoEstoque.objects.exists())
        estoque = Estoque.objects.get(produto=self.produto, filial=self.filial)
        self.assertEqual(estoque.quantidade_atual, Decimal("10.000"))

    def test_fechamento_vence_corrida_e_sangria_suprimento_sao_rejeitados(self):
        lock_adquirido = Event()
        liberar = Event()

        def movimentar(tipo):
            close_old_connections()
            try:
                caixa = Caixa.objects.get(pk=self.caixa.pk)
                usuario = get_user_model().objects.get(pk=self.usuario.pk)
                try:
                    if tipo == "sangria":
                        registrar_sangria_caixa(
                            caixa=caixa, usuario=usuario, valor=Decimal("5.00"), motivo="Corrida"
                        )
                    else:
                        registrar_suprimento_caixa(
                            caixa=caixa, usuario=usuario, valor=Decimal("7.00"), motivo="Corrida"
                        )
                    return "registrado"
                except ValidationError as exc:
                    return f"rejeitado:{' '.join(exc.messages)}"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=3) as executor:
            fechamento = executor.submit(self._fechar_mantendo_lock, lock_adquirido, liberar)
            self.assertTrue(lock_adquirido.wait(timeout=15))
            sangria = executor.submit(movimentar, "sangria")
            suprimento = executor.submit(movimentar, "suprimento")
            liberar.set()
            self.assertEqual(fechamento.result(timeout=30), "fechado")
            resultados = [sangria.result(timeout=30), suprimento.result(timeout=30)]

        self.assertTrue(all("Este caixa não está aberto" in resultado for resultado in resultados))
        self.assertFalse(Sangria.objects.exists())
        self.assertFalse(Suprimento.objects.exists())
        self.assertFalse(LancamentoFinanceiro.objects.exists())

    def test_suprimento_que_obtem_lock_primeiro_termina_antes_do_fechamento(self):
        lock_adquirido = Event()
        liberar = Event()

        def movimentar_primeiro():
            close_old_connections()
            try:
                with transaction.atomic():
                    caixa = Caixa.objects.select_for_update().get(pk=self.caixa.pk)
                    lock_adquirido.set()
                    if not liberar.wait(timeout=15):
                        raise TimeoutError("Teste não liberou o suprimento.")
                    registrar_suprimento_caixa(
                        caixa=caixa,
                        usuario=get_user_model().objects.get(pk=self.usuario.pk),
                        valor=Decimal("7.00"),
                        motivo="Antes do fechamento",
                    )
                return "registrado"
            finally:
                close_old_connections()

        def fechar():
            close_old_connections()
            try:
                caixa = fechar_caixa_operacional(
                    caixa=Caixa.objects.get(pk=self.caixa.pk),
                    usuario=get_user_model().objects.get(pk=self.usuario.pk),
                    valor_final=Decimal("107.00"),
                )
                return caixa.status
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            movimento = executor.submit(movimentar_primeiro)
            self.assertTrue(lock_adquirido.wait(timeout=15))
            fechamento = executor.submit(fechar)
            liberar.set()
            self.assertEqual(movimento.result(timeout=30), "registrado")
            self.assertEqual(fechamento.result(timeout=30), StatusCaixa.FECHADO)

        self.caixa.refresh_from_db()
        self.assertEqual(self.caixa.status, StatusCaixa.FECHADO)
        self.assertEqual(Suprimento.objects.filter(caixa=self.caixa).count(), 1)
        self.assertEqual(
            LancamentoFinanceiro.objects.filter(suprimento__caixa=self.caixa).count(),
            1,
        )
