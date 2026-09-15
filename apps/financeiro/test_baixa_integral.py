from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from apps.auditoria.models import LogAuditoria
from apps.empresas.models import Empresa, Filial

from .forms import BaixaContaForm
from .models import (
    ContaFinanceira,
    LancamentoFinanceiro,
    StatusContaFinanceira,
    TipoContaFinanceira,
)
from .services import baixar_conta


class BaixaIntegralContaTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user("baixa-integral", password="teste")
        self.empresa = Empresa.objects.create(
            razao_social="Mercado Baixa Integral",
            nome_fantasia="Mercado Baixa",
            cnpj="12.345.678/0001-95",
        )
        self.filial = Filial.objects.create(
            empresa=self.empresa,
            nome="Matriz Baixa",
            cnpj=self.empresa.cnpj,
        )
        self.conta = ContaFinanceira.objects.create(
            tipo=TipoContaFinanceira.PAGAR,
            descricao="Conta integral",
            filial=self.filial,
            valor=Decimal("150.00"),
            vencimento=timezone.localdate(),
            usuario=self.usuario,
        )

    def test_baixa_integral_permanece_permitida(self):
        resultado = baixar_conta(
            conta=self.conta,
            usuario=self.usuario,
            data_pagamento=timezone.localdate(),
            valor_pago=Decimal("150.00"),
            forma_pagamento="PIX",
        )

        self.assertEqual(resultado.status, StatusContaFinanceira.PAGA)
        self.assertEqual(resultado.valor_pago, resultado.valor)
        self.assertIsNotNone(resultado.data_pagamento)
        self.assertTrue(
            LogAuditoria.objects.filter(acao="BAIXA_CONTA", objeto_id=str(self.conta.pk)).exists()
        )

    def test_servico_recusa_baixa_parcial_sem_efeitos_colaterais(self):
        with self.assertRaisesMessage(ValidationError, "valor integral"):
            baixar_conta(
                conta=self.conta,
                usuario=self.usuario,
                data_pagamento=timezone.localdate(),
                valor_pago=Decimal("100.00"),
            )

        self.conta.refresh_from_db()
        self.assertEqual(self.conta.status, StatusContaFinanceira.ABERTA)
        self.assertIsNone(self.conta.valor_pago)
        self.assertIsNone(self.conta.data_pagamento)
        self.assertFalse(LancamentoFinanceiro.objects.filter(conta_financeira=self.conta).exists())
        self.assertFalse(LogAuditoria.objects.filter(objeto_id=str(self.conta.pk), acao="BAIXA_CONTA").exists())

    def test_servico_recusa_pagamento_acima_do_total(self):
        with self.assertRaisesMessage(ValidationError, "acima do total"):
            baixar_conta(
                conta=self.conta,
                usuario=self.usuario,
                data_pagamento=timezone.localdate(),
                valor_pago=Decimal("151.00"),
            )

    def test_formulario_explica_e_recusa_valor_divergente(self):
        form = BaixaContaForm(
            data={
                "data_pagamento": timezone.localdate().isoformat(),
                "valor_pago": "100.00",
                "forma_pagamento": "PIX",
                "conta_movimento": "",
            },
            filial=self.filial,
            conta=self.conta,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("valor integral", form.errors["valor_pago"][0])
        self.assertIn("Pagamentos parciais ainda não são suportados", form.fields["valor_pago"].help_text)

    def test_banco_recusa_conta_paga_com_valor_divergente(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ContaFinanceira.objects.filter(pk=self.conta.pk).update(
                status=StatusContaFinanceira.PAGA,
                data_pagamento=timezone.localdate(),
                valor_pago=Decimal("100.00"),
            )

    def test_banco_recusa_conta_aberta_com_dados_de_pagamento(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ContaFinanceira.objects.filter(pk=self.conta.pk).update(
                data_pagamento=timezone.localdate(),
                valor_pago=Decimal("150.00"),
            )
