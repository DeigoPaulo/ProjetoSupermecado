from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.utils import timezone

from apps.auditoria.models import LogAuditoria
from apps.empresas.models import Empresa, Filial
from apps.pdv.models import Caixa
from apps.vendas.models import FormaPagamento, PagamentoVenda, StatusVenda, Venda

from .models import CategoriaFinanceira, ContaFinanceira, ContaMovimentoFinanceiro, LancamentoFinanceiro, StatusContaFinanceira, TipoContaFinanceira, TipoContaMovimento, TipoLancamentoFinanceiro, TransferenciaFinanceira
from .services import baixar_conta, cancelar_conta, estornar_lancamento, realizar_transferencia


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
        self.assertContains(response, "Vencimentos")
        self.assertContains(response, "Conferencia e exportacao")

    def test_formularios_financeiros_exibem_secoes_operacionais(self):
        conta_form = self.client.get(f"/financeiro/{self.conta.pk}/editar/")
        categoria_form = self.client.get(f"/financeiro/categorias/{self.categoria.pk}/editar/")
        baixa_form = self.client.get(f"/financeiro/{self.conta.pk}/baixar/")

        self.assertEqual(conta_form.status_code, 200)
        self.assertContains(conta_form, "Classificacao")
        self.assertContains(conta_form, "Origem e parceiro")
        self.assertContains(conta_form, "Valores e vencimento")
        self.assertContains(conta_form, "select2-field")
        self.assertEqual(categoria_form.status_code, 200)
        self.assertContains(categoria_form, "Categoria")
        self.assertEqual(baixa_form.status_code, 200)
        self.assertContains(baixa_form, "Pagamento / recebimento")

    def test_baixa_conta_respeita_retorno_seguro_para_origem(self):
        response = self.client.post(
            f"/financeiro/{self.conta.pk}/baixar/",
            {
                "data_pagamento": timezone.localdate().isoformat(),
                "valor_pago": "150.00",
                "forma_pagamento": "Pix",
                "conta_movimento": "",
                "next": "/compras/10/",
            },
        )

        self.conta.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/compras/10/")
        self.assertEqual(self.conta.status, StatusContaFinanceira.PAGA)

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
        self.assertContains(response, "Previsao por vencimento")
        self.assertContains(response, "Realizado por baixa")
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
        self.assertContains(response, "Conciliacao financeira")
        self.assertContains(response, "Entradas PDV")
        self.assertContains(response, "PDV x financeiro")
        self.assertContains(response, "Conferencia diaria")
        self.assertContains(response, "130,00")
        self.assertEqual(response_csv.status_code, 200)
        self.assertEqual(response_csv["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn(b"Saldo operacional", response_csv.content)

    def test_resultado_financeiro_ignora_transferencias_e_exporta_csv(self):
        caixa = ContaMovimentoFinanceiro.objects.create(
            filial=self.filial,
            nome="Caixa resultado",
            tipo=TipoContaMovimento.CAIXA,
            saldo_inicial=Decimal("500.00"),
        )
        banco = ContaMovimentoFinanceiro.objects.create(
            filial=self.filial,
            nome="Banco resultado",
            tipo=TipoContaMovimento.BANCO,
            saldo_inicial=Decimal("0.00"),
        )
        baixar_conta(
            conta=self.conta_receber,
            usuario=self.user,
            data_pagamento=timezone.localdate(),
            valor_pago=Decimal("210.00"),
            forma_pagamento="PIX",
            conta_movimento=caixa,
        )
        baixar_conta(
            conta=self.conta,
            usuario=self.user,
            data_pagamento=timezone.localdate(),
            valor_pago=Decimal("150.00"),
            forma_pagamento="PIX",
            conta_movimento=caixa,
        )
        realizar_transferencia(
            conta_origem=caixa,
            conta_destino=banco,
            valor=Decimal("50.00"),
            data=timezone.localdate(),
            usuario=self.user,
            descricao="Deposito interno",
        )

        response = self.client.get("/financeiro/resultado/")
        response_csv = self.client.get("/financeiro/resultado/exportar.csv")
        csv_texto = response_csv.content.decode("utf-8-sig")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Resultado financeiro")
        self.assertContains(response, "Receitas realizadas")
        self.assertContains(response, "Despesas realizadas")
        self.assertContains(response, "Resultado por categoria")
        self.assertContains(response, "Saldos por conta de movimento")
        self.assertContains(response, "Balancete gerencial")
        self.assertContains(response, "Mercadorias")
        self.assertContains(response, "Caixa resultado")
        self.assertContains(response, "Banco resultado")
        self.assertContains(response, "60,00")
        self.assertNotContains(response, "TRANSFERENCIA")
        self.assertEqual(response_csv["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("resultado_financeiro_", response_csv["Content-Disposition"])
        self.assertIn("Periodo;210,00;150,00;60,00", csv_texto)
        self.assertIn("Categoria;Tipo;Receitas;Despesas;Resultado", csv_texto)
        self.assertIn("Mercadorias;Conta a pagar;0,00;150,00;-150,00", csv_texto)
        self.assertIn("Filial;Conta movimento;Tipo;Saldo inicial;Entradas periodo;Saidas periodo;Saldo atual", csv_texto)
        self.assertIn("Matriz;Caixa resultado;Caixa fisico;500,00;210,00;150,00;510,00", csv_texto)
        self.assertIn("Balancete gerencial por conta", csv_texto)
        self.assertIn("Filial;Conta movimento;Tipo;Saldo anterior;Entradas;Saidas;Saldo final", csv_texto)
        self.assertIn("Matriz;Caixa resultado;Caixa fisico;500,00;210,00;200,00;510,00", csv_texto)
        self.assertIn("Matriz;Banco resultado;Conta bancaria;0,00;50,00;0,00;50,00", csv_texto)
        self.assertNotIn("TRANSFERENCIA", csv_texto)

    def test_baixa_em_conta_movimento_registra_livro_imutavel(self):
        conta_pix = ContaMovimentoFinanceiro.objects.create(
            filial=self.filial,
            nome="PIX Matriz",
            tipo=TipoContaMovimento.PIX,
            saldo_inicial=Decimal("50.00"),
        )

        baixar_conta(
            conta=self.conta_receber,
            usuario=self.user,
            data_pagamento=timezone.localdate(),
            valor_pago=Decimal("210.00"),
            forma_pagamento="PIX",
            conta_movimento=conta_pix,
        )

        lancamento = LancamentoFinanceiro.objects.get(conta_financeira=self.conta_receber)
        self.conta_receber.refresh_from_db()
        self.assertEqual(self.conta_receber.conta_movimento, conta_pix)
        self.assertEqual(lancamento.tipo, TipoLancamentoFinanceiro.ENTRADA)
        self.assertEqual(lancamento.valor, Decimal("210.00"))
        self.assertEqual(conta_pix.saldo_atual, Decimal("260.00"))
        with self.assertRaises(ValidationError):
            lancamento.save()
        with self.assertRaises(ValidationError):
            lancamento.delete()

        contas = self.client.get("/financeiro/contas-movimento/")
        livro = self.client.get("/financeiro/livro/")
        livro_csv = self.client.get("/financeiro/livro/exportar.csv")
        self.assertContains(contas, "PIX Matriz")
        self.assertContains(contas, "260,00")
        self.assertContains(livro, "Livro financeiro")
        self.assertContains(livro, "Crediario cliente")
        self.assertContains(livro, "R$ 210,00")
        self.assertEqual(livro_csv["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("livro_financeiro_", livro_csv["Content-Disposition"])
        self.assertIn(b"PIX Matriz", livro_csv.content)

    def test_cadastra_conta_movimento_e_filtra_na_baixa(self):
        response = self.client.post(
            "/financeiro/contas-movimento/nova/",
            {
                "filial": self.filial.pk,
                "nome": "Caixa administrativo",
                "tipo": TipoContaMovimento.CAIXA,
                "saldo_inicial": "100.00",
                "ativa": "on",
            },
            follow=True,
        )

        self.assertRedirects(response, "/financeiro/contas-movimento/")
        self.assertContains(response, "Caixa administrativo")
        baixa = self.client.get(f"/financeiro/{self.conta.pk}/baixar/")
        self.assertContains(baixa, "Conta de movimento")
        self.assertContains(baixa, "Caixa administrativo")

    def test_transferencia_entre_contas_gera_lancamentos_espelhados(self):
        caixa = ContaMovimentoFinanceiro.objects.create(
            filial=self.filial,
            nome="Caixa loja",
            tipo=TipoContaMovimento.CAIXA,
            saldo_inicial=Decimal("300.00"),
        )
        banco = ContaMovimentoFinanceiro.objects.create(
            filial=self.filial,
            nome="Banco operacional",
            tipo=TipoContaMovimento.BANCO,
            saldo_inicial=Decimal("20.00"),
        )

        transferencia = realizar_transferencia(
            conta_origem=caixa,
            conta_destino=banco,
            valor=Decimal("120.00"),
            data=timezone.localdate(),
            usuario=self.user,
            descricao="Deposito no banco",
        )

        self.assertEqual(TransferenciaFinanceira.objects.count(), 1)
        self.assertEqual(transferencia.lancamentos.count(), 2)
        self.assertEqual(caixa.saldo_atual, Decimal("180.00"))
        self.assertEqual(banco.saldo_atual, Decimal("140.00"))
        self.assertTrue(LogAuditoria.objects.filter(modulo="financeiro", acao="TRANSFERENCIA").exists())
        self.assertEqual(
            LancamentoFinanceiro.objects.filter(transferencia=transferencia, tipo=TipoLancamentoFinanceiro.SAIDA).count(),
            1,
        )
        self.assertEqual(
            LancamentoFinanceiro.objects.filter(transferencia=transferencia, tipo=TipoLancamentoFinanceiro.ENTRADA).count(),
            1,
        )
        with self.assertRaises(ValidationError):
            transferencia.save()
        with self.assertRaises(ValidationError):
            transferencia.delete()

    def test_transferencia_bloqueia_saldo_insuficiente(self):
        caixa = ContaMovimentoFinanceiro.objects.create(
            filial=self.filial,
            nome="Caixa pequeno",
            tipo=TipoContaMovimento.CAIXA,
            saldo_inicial=Decimal("30.00"),
        )
        banco = ContaMovimentoFinanceiro.objects.create(
            filial=self.filial,
            nome="Banco",
            tipo=TipoContaMovimento.BANCO,
            saldo_inicial=Decimal("0.00"),
        )

        with self.assertRaisesMessage(ValidationError, "Saldo insuficiente"):
            realizar_transferencia(
                conta_origem=caixa,
                conta_destino=banco,
                valor=Decimal("31.00"),
                data=timezone.localdate(),
                usuario=self.user,
            )

        self.assertFalse(TransferenciaFinanceira.objects.exists())
        self.assertFalse(LancamentoFinanceiro.objects.filter(origem="TRANSFERENCIA").exists())

    def test_tela_de_transferencia_financeira(self):
        caixa = ContaMovimentoFinanceiro.objects.create(
            filial=self.filial,
            nome="Caixa financeiro",
            tipo=TipoContaMovimento.CAIXA,
            saldo_inicial=Decimal("200.00"),
        )
        banco = ContaMovimentoFinanceiro.objects.create(
            filial=self.filial,
            nome="Banco caixa",
            tipo=TipoContaMovimento.BANCO,
            saldo_inicial=Decimal("0.00"),
        )

        formulario = self.client.get("/financeiro/transferencias/nova/")
        response = self.client.post(
            "/financeiro/transferencias/nova/",
            {
                "conta_origem": caixa.pk,
                "conta_destino": banco.pk,
                "valor": "75.00",
                "data": timezone.localdate().isoformat(),
                "descricao": "Sangria para banco",
            },
            follow=True,
        )

        self.assertContains(formulario, "Transferencia entre contas")
        self.assertContains(formulario, "Transferencias recentes")
        self.assertRedirects(response, "/financeiro/livro/")
        self.assertContains(response, "Transferencia #")
        self.assertContains(response, "Sangria para banco")

    def test_estorno_cria_lancamento_inverso_e_bloqueia_duplicidade(self):
        conta_pix = ContaMovimentoFinanceiro.objects.create(
            filial=self.filial,
            nome="PIX estorno",
            tipo=TipoContaMovimento.PIX,
            saldo_inicial=Decimal("10.00"),
        )
        baixar_conta(
            conta=self.conta_receber,
            usuario=self.user,
            data_pagamento=timezone.localdate(),
            valor_pago=Decimal("210.00"),
            forma_pagamento="PIX",
            conta_movimento=conta_pix,
        )
        lancamento = LancamentoFinanceiro.objects.get(conta_financeira=self.conta_receber)

        estorno = estornar_lancamento(
            lancamento=lancamento,
            usuario=self.user,
            motivo="Recebimento duplicado",
            data=timezone.localdate(),
        )

        self.assertEqual(estorno.tipo, TipoLancamentoFinanceiro.SAIDA)
        self.assertEqual(estorno.valor, lancamento.valor)
        self.assertEqual(estorno.estorno_de, lancamento)
        self.assertEqual(conta_pix.saldo_atual, Decimal("10.00"))
        self.assertTrue(LogAuditoria.objects.filter(modulo="financeiro", acao="ESTORNO_LANCAMENTO").exists())
        with self.assertRaisesMessage(ValidationError, "ja possui estorno"):
            estornar_lancamento(lancamento=lancamento, usuario=self.user, motivo="Repetido")
        with self.assertRaisesMessage(ValidationError, "nao pode ser estornado novamente"):
            estornar_lancamento(lancamento=estorno, usuario=self.user, motivo="Reversao indevida")

    def test_tela_livro_estorna_lancamento_com_motivo(self):
        conta_pix = ContaMovimentoFinanceiro.objects.create(
            filial=self.filial,
            nome="PIX livro",
            tipo=TipoContaMovimento.PIX,
            saldo_inicial=Decimal("0.00"),
        )
        baixar_conta(
            conta=self.conta_receber,
            usuario=self.user,
            data_pagamento=timezone.localdate(),
            valor_pago=Decimal("210.00"),
            forma_pagamento="PIX",
            conta_movimento=conta_pix,
        )
        lancamento = LancamentoFinanceiro.objects.get(conta_financeira=self.conta_receber)

        response = self.client.post(
            f"/financeiro/livro/{lancamento.pk}/estornar/",
            {"motivo": "Erro de baixa"},
            follow=True,
        )

        self.assertRedirects(response, "/financeiro/livro/")
        self.assertContains(response, "Estorno registrado")
        self.assertContains(response, "Estorno do lancamento")
        self.assertContains(response, "Fechado")
        self.assertEqual(LancamentoFinanceiro.objects.filter(estorno_de=lancamento).count(), 1)
