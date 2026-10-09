from django.test import TestCase

from apps.empresas.models import Empresa, Filial
from apps.financeiro.models import ContaMovimentoFinanceiro, TipoContaMovimento

from .models import FormaPagamento, FormaPagamentoFilial
from .services import bootstrap_formas_pagamento_filial, formas_pagamento_disponiveis


class BootstrapFormasPagamentoTests(TestCase):
    def setUp(self):
        empresa = Empresa.objects.create(
            razao_social="Mercado Bootstrap Ltda",
            nome_fantasia="Mercado Bootstrap",
            cnpj="11.111.111/0001-11",
        )
        self.filial = Filial.objects.create(empresa=empresa, nome="Matriz")

    def test_filial_nova_recebe_seis_formas_com_somente_dinheiro_operacional(self):
        bootstrap_formas_pagamento_filial(self.filial)

        esperados = {
            "DINHEIRO", "DEBITO", "CREDITO", "PIX",
            "VALE_ALIMENTACAO", "VALE_REFEICAO",
        }
        self.assertEqual(set(FormaPagamento.objects.values_list("tipo", flat=True)), esperados)
        self.assertEqual(FormaPagamento.objects.count(), 6)
        self.assertEqual(FormaPagamentoFilial.objects.filter(filial=self.filial).count(), 6)
        dinheiro = FormaPagamento.objects.get(tipo="DINHEIRO")
        self.assertTrue(dinheiro.ativo)
        self.assertTrue(dinheiro.permite_troco)
        self.assertEqual(
            list(formas_pagamento_disponiveis(self.filial).values_list("tipo", flat=True)),
            ["DINHEIRO"],
        )

    def test_repeticao_preserva_desativacao_e_conta_personalizada(self):
        bootstrap_formas_pagamento_filial(self.filial)
        conta = ContaMovimentoFinanceiro.objects.create(
            filial=self.filial, nome="Conta particular", tipo=TipoContaMovimento.CAIXA,
        )
        dinheiro = FormaPagamento.objects.get(tipo="DINHEIRO")
        dinheiro.ativo = False
        dinheiro.permite_troco = False
        dinheiro.nome = "Dinheiro personalizado"
        dinheiro.conta_movimento_padrao = conta
        dinheiro.save()
        configuracao = FormaPagamentoFilial.objects.get(filial=self.filial, forma_pagamento=dinheiro)
        configuracao.ativo = False
        configuracao.conta_movimento_padrao = conta
        configuracao.save()

        bootstrap_formas_pagamento_filial(self.filial)

        dinheiro.refresh_from_db()
        configuracao.refresh_from_db()
        self.assertEqual(FormaPagamento.objects.count(), 6)
        self.assertEqual(FormaPagamentoFilial.objects.filter(filial=self.filial).count(), 6)
        self.assertEqual(dinheiro.nome, "Dinheiro personalizado")
        self.assertFalse(dinheiro.ativo)
        self.assertFalse(dinheiro.permite_troco)
        self.assertEqual(dinheiro.conta_movimento_padrao, conta)
        self.assertFalse(configuracao.ativo)
        self.assertEqual(configuracao.conta_movimento_padrao, conta)

    def test_forma_existente_do_mesmo_tipo_nao_e_duplicada(self):
        forma = FormaPagamento.objects.create(
            nome="Debito contratado", tipo="DEBITO", ativo=False,
        )

        bootstrap_formas_pagamento_filial(self.filial)

        self.assertEqual(FormaPagamento.objects.filter(tipo="DEBITO").count(), 1)
        forma.refresh_from_db()
        self.assertEqual(forma.nome, "Debito contratado")
        self.assertFalse(forma.ativo)
        self.assertFalse(FormaPagamentoFilial.objects.get(
            filial=self.filial, forma_pagamento=forma,
        ).ativo)

    def test_consulta_sem_dinheiro_nao_cria_forma_global(self):
        self.assertFalse(FormaPagamento.objects.filter(tipo="DINHEIRO").exists())

        self.assertFalse(formas_pagamento_disponiveis(self.filial).exists())

        self.assertFalse(FormaPagamento.objects.filter(tipo="DINHEIRO").exists())

    def test_vale_so_fica_disponivel_apos_habilitacao_da_filial(self):
        vale = FormaPagamento.objects.create(
            nome="Vale Alimentação contratado", tipo="VALE_ALIMENTACAO",
        )

        self.assertNotIn(vale, formas_pagamento_disponiveis(self.filial))
        configuracao = FormaPagamentoFilial.objects.get(
            filial=self.filial, forma_pagamento=vale,
        )
        self.assertFalse(configuracao.ativo)

        configuracao.ativo = True
        configuracao.save(update_fields=["ativo"])

        self.assertIn(vale, formas_pagamento_disponiveis(self.filial))
