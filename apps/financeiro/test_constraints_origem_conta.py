from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from apps.compras.models import DuplicataNFeEntrada, EntradaCompra, FaturaNFeEntrada
from apps.empresas.models import Empresa, Filial
from apps.fornecedores.models import Fornecedor
from apps.pdv.models import Caixa
from apps.vendas.models import Venda

from .models import ContaFinanceira, TipoContaFinanceira


class ContaFinanceiraOrigemConstraintTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user("origem-financeira")
        self.empresa = Empresa.objects.create(
            razao_social="Mercado Origem Ltda",
            nome_fantasia="Mercado Origem",
            cnpj="12345678000195",
        )
        self.filial = Filial.objects.create(
            empresa=self.empresa,
            nome="Matriz",
            cnpj="12345678000195",
        )
        self.fornecedor = Fornecedor.objects.create(
            empresa=self.empresa,
            razao_social="Fornecedor Origem Ltda",
            cnpj="98765432000198",
        )
        self.caixa = Caixa.objects.create(
            filial=self.filial,
            usuario_abertura=self.usuario,
        )
        self.venda = Venda.objects.create(
            filial=self.filial,
            caixa=self.caixa,
            usuario=self.usuario,
            total_bruto=Decimal("10.00"),
            total_liquido=Decimal("10.00"),
        )
        self.entrada = EntradaCompra.objects.create(
            fornecedor=self.fornecedor,
            filial=self.filial,
            usuario=self.usuario,
            total_produtos=Decimal("10.00"),
        )

    def _conta(self, **alteracoes):
        dados = {
            "tipo": TipoContaFinanceira.PAGAR,
            "descricao": "Conta de teste",
            "filial": self.filial,
            "valor": Decimal("10.00"),
            "vencimento": timezone.localdate(),
            "usuario": self.usuario,
        }
        dados.update(alteracoes)
        return ContaFinanceira(**dados)

    def _assert_integrity_error(self, conta):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                conta.save()

    def test_conta_manual_sem_origem_permanece_valida(self):
        conta_pagar = self._conta()
        conta_pagar.save()
        conta_receber = self._conta(
            tipo=TipoContaFinanceira.RECEBER,
            descricao="Conta manual a receber",
        )
        conta_receber.save()

        self.assertEqual(ContaFinanceira.objects.filter(venda=None, entrada_compra=None).count(), 2)

    def test_banco_rejeita_origens_simultaneas_e_tipos_incompativeis(self):
        self._assert_integrity_error(
            self._conta(
                tipo=TipoContaFinanceira.RECEBER,
                venda=self.venda,
                entrada_compra=self.entrada,
            )
        )
        self._assert_integrity_error(
            self._conta(tipo=TipoContaFinanceira.PAGAR, venda=self.venda)
        )
        self._assert_integrity_error(
            self._conta(tipo=TipoContaFinanceira.RECEBER, entrada_compra=self.entrada)
        )

    def test_banco_exige_compra_quando_existe_duplicata(self):
        fatura = FaturaNFeEntrada.objects.create(entrada=self.entrada)
        duplicata = DuplicataNFeEntrada.objects.create(
            fatura=fatura,
            sequencia=1,
            numero="001",
            vencimento=timezone.localdate(),
            valor=Decimal("10.00"),
        )

        self._assert_integrity_error(
            self._conta(duplicata_nfe_entrada=duplicata)
        )

    def test_banco_garante_uma_conta_por_venda(self):
        self._conta(tipo=TipoContaFinanceira.RECEBER, venda=self.venda).save()

        self._assert_integrity_error(
            self._conta(
                tipo=TipoContaFinanceira.RECEBER,
                venda=self.venda,
                descricao="Segunda conta da mesma venda",
            )
        )

    def test_banco_garante_uma_conta_unica_por_compra_sem_duplicatas(self):
        self._conta(entrada_compra=self.entrada).save()

        self._assert_integrity_error(
            self._conta(
                entrada_compra=self.entrada,
                descricao="Segunda conta única da mesma compra",
            )
        )

    def test_banco_permite_varias_parcelas_da_mesma_compra(self):
        fatura = FaturaNFeEntrada.objects.create(
            entrada=self.entrada,
            valor_liquido=Decimal("10.00"),
        )
        duplicatas = [
            DuplicataNFeEntrada.objects.create(
                fatura=fatura,
                sequencia=sequencia,
                numero=f"{sequencia:03d}",
                vencimento=timezone.localdate(),
                valor=Decimal("5.00"),
            )
            for sequencia in (1, 2)
        ]

        for duplicata in duplicatas:
            self._conta(
                entrada_compra=self.entrada,
                duplicata_nfe_entrada=duplicata,
                descricao=f"Parcela {duplicata.numero}",
                valor=duplicata.valor,
            ).save()

        self.assertEqual(ContaFinanceira.objects.filter(entrada_compra=self.entrada).count(), 2)

    def test_modelo_rejeita_duplicata_de_outra_compra(self):
        outra_entrada = EntradaCompra.objects.create(
            fornecedor=self.fornecedor,
            filial=self.filial,
            usuario=self.usuario,
            total_produtos=Decimal("5.00"),
        )
        fatura = FaturaNFeEntrada.objects.create(entrada=outra_entrada)
        duplicata = DuplicataNFeEntrada.objects.create(
            fatura=fatura,
            sequencia=1,
            numero="001",
            vencimento=timezone.localdate(),
            valor=Decimal("5.00"),
        )
        conta = self._conta(
            entrada_compra=self.entrada,
            duplicata_nfe_entrada=duplicata,
        )

        with self.assertRaisesMessage(ValidationError, "outra entrada de compra"):
            conta.full_clean()
