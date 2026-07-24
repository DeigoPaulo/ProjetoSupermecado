from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.auditoria.models import LogAuditoria
from apps.empresas.models import Empresa, Filial
from apps.estoque.models import Estoque, MovimentacaoEstoque, TipoMovimentacaoEstoque
from apps.financeiro.models import ContaFinanceira, ContaMovimentoFinanceiro, StatusContaFinanceira, TipoContaFinanceira, TipoContaMovimento
from apps.financeiro.services import baixar_conta
from apps.fornecedores.models import Fornecedor
from apps.produtos.models import Categoria, Produto

from .models import EntradaCompra, ItemEntradaCompra, StatusEntradaCompra
from .services import cancelar_entrada_compra, finalizar_entrada_compra


class ComprasFinanceiroTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(username="compras", password="123")
        self.admin = get_user_model().objects.create_superuser("admin", "admin@example.com", "123")
        self.admin_misto = get_user_model().objects.create_superuser("AdminMaster", "master@example.com", "123")
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

    def test_finalizar_compra_atualiza_estoque_movimentacao_e_custo(self):
        Estoque.objects.create(produto=self.produto, filial=self.filial, quantidade_atual=Decimal("2.000"))
        entrada = EntradaCompra.objects.create(
            fornecedor=self.fornecedor,
            filial=self.filial,
            usuario=self.usuario,
            numero_documento="NF-101",
            gerar_conta_financeira=False,
        )
        ItemEntradaCompra.objects.create(
            entrada=entrada,
            produto=self.produto,
            quantidade=Decimal("7.000"),
            custo_unitario=Decimal("4.75"),
            total=Decimal("33.25"),
            atualizar_preco_custo=True,
        )

        finalizar_entrada_compra(entrada)

        entrada.refresh_from_db()
        self.produto.refresh_from_db()
        estoque = Estoque.objects.get(produto=self.produto, filial=self.filial)
        movimentacao = MovimentacaoEstoque.objects.get(referencia=f"entrada_compra:{entrada.id}")

        self.assertEqual(entrada.status, StatusEntradaCompra.FINALIZADA)
        self.assertEqual(entrada.total_produtos, Decimal("33.25"))
        self.assertEqual(estoque.quantidade_atual, Decimal("9.000"))
        self.assertEqual(self.produto.preco_custo, Decimal("4.75"))
        self.assertEqual(movimentacao.tipo, TipoMovimentacaoEstoque.ENTRADA)
        self.assertEqual(movimentacao.quantidade, Decimal("7.000"))
        self.assertEqual(movimentacao.custo_unitario, Decimal("4.75"))
        self.assertEqual(movimentacao.custo_total, Decimal("33.250"))
        self.assertFalse(ContaFinanceira.objects.filter(entrada_compra=entrada).exists())

    def test_cancelar_compra_finalizada_reverte_estoque_e_cancela_conta_aberta(self):
        entrada = EntradaCompra.objects.create(
            fornecedor=self.fornecedor,
            filial=self.filial,
            usuario=self.usuario,
            numero_documento="NF-CANCELAR",
        )
        ItemEntradaCompra.objects.create(
            entrada=entrada,
            produto=self.produto,
            quantidade=Decimal("5.000"),
            custo_unitario=Decimal("4.25"),
            total=Decimal("21.25"),
        )
        finalizar_entrada_compra(entrada)

        cancelada = cancelar_entrada_compra(
            entrada,
            usuario=self.admin,
            motivo="Lancamento duplicado",
            supervisor=self.admin_misto,
        )

        estoque = Estoque.objects.get(produto=self.produto, filial=self.filial)
        conta = ContaFinanceira.objects.get(entrada_compra=entrada)

        self.assertEqual(cancelada.status, StatusEntradaCompra.CANCELADA)
        self.assertEqual(estoque.quantidade_atual, Decimal("0.000"))
        self.assertEqual(conta.status, StatusContaFinanceira.CANCELADA)
        self.assertTrue(
            MovimentacaoEstoque.objects.filter(
                referencia=f"entrada_compra_cancelamento:{entrada.id}",
                tipo=TipoMovimentacaoEstoque.SAIDA,
                quantidade=Decimal("5.000"),
            ).exists()
        )

    def test_cancelar_compra_bloqueia_conta_paga(self):
        entrada = EntradaCompra.objects.create(
            fornecedor=self.fornecedor,
            filial=self.filial,
            usuario=self.usuario,
            numero_documento="NF-PAGA",
        )
        ItemEntradaCompra.objects.create(
            entrada=entrada,
            produto=self.produto,
            quantidade=Decimal("2.000"),
            custo_unitario=Decimal("4.00"),
            total=Decimal("8.00"),
        )
        finalizar_entrada_compra(entrada)
        conta = ContaFinanceira.objects.get(entrada_compra=entrada)
        conta.status = StatusContaFinanceira.PAGA
        conta.valor_pago = Decimal("8.00")
        conta.save(update_fields=["status", "valor_pago", "atualizado_em"])

        with self.assertRaisesMessage(ValidationError, "Conta paga nao pode ser cancelada."):
            cancelar_entrada_compra(
                entrada,
                usuario=self.admin,
                motivo="Tentativa apos pagamento",
                supervisor=self.admin_misto,
            )

        entrada.refresh_from_db()
        self.assertEqual(entrada.status, StatusEntradaCompra.FINALIZADA)
        self.assertEqual(Estoque.objects.get(produto=self.produto, filial=self.filial).quantidade_atual, Decimal("2.000"))

    def test_cancelar_compra_bloqueia_se_estoque_ja_foi_consumido(self):
        entrada = EntradaCompra.objects.create(
            fornecedor=self.fornecedor,
            filial=self.filial,
            usuario=self.usuario,
            numero_documento="NF-CONSUMIDA",
            gerar_conta_financeira=False,
        )
        ItemEntradaCompra.objects.create(
            entrada=entrada,
            produto=self.produto,
            quantidade=Decimal("3.000"),
            custo_unitario=Decimal("4.00"),
            total=Decimal("12.00"),
        )
        finalizar_entrada_compra(entrada)
        estoque = Estoque.objects.get(produto=self.produto, filial=self.filial)
        estoque.quantidade_atual = Decimal("1.000")
        estoque.save(update_fields=["quantidade_atual"])

        with self.assertRaisesMessage(ValidationError, "Estoque insuficiente."):
            cancelar_entrada_compra(
                entrada,
                usuario=self.admin,
                motivo="Produto ja movimentado",
                supervisor=self.admin_misto,
            )

        entrada.refresh_from_db()
        estoque.refresh_from_db()
        self.assertEqual(entrada.status, StatusEntradaCompra.FINALIZADA)
        self.assertEqual(estoque.quantidade_atual, Decimal("1.000"))
        self.assertFalse(MovimentacaoEstoque.objects.filter(referencia=f"entrada_compra_cancelamento:{entrada.id}").exists())

    def test_detalhe_avisa_bloqueios_de_cancelamento(self):
        self.client.force_login(self.admin)
        entrada = EntradaCompra.objects.create(
            fornecedor=self.fornecedor,
            filial=self.filial,
            usuario=self.usuario,
            numero_documento="NF-BLOQUEIO",
        )
        ItemEntradaCompra.objects.create(
            entrada=entrada,
            produto=self.produto,
            quantidade=Decimal("4.000"),
            custo_unitario=Decimal("4.00"),
            total=Decimal("16.00"),
        )
        finalizar_entrada_compra(entrada)
        conta = ContaFinanceira.objects.get(entrada_compra=entrada)
        conta.status = StatusContaFinanceira.PAGA
        conta.valor_pago = Decimal("16.00")
        conta.save(update_fields=["status", "valor_pago", "atualizado_em"])
        estoque = Estoque.objects.get(produto=self.produto, filial=self.filial)
        estoque.quantidade_atual = Decimal("1.000")
        estoque.save(update_fields=["quantidade_atual"])

        response = self.client.get(f"/compras/{entrada.id}/")

        self.assertContains(response, "Esta entrada nao pode ser cancelada automaticamente")
        self.assertContains(response, "A conta financeira vinculada ja foi paga")
        self.assertContains(response, "Saldo insuficiente para reverter")
        self.assertNotContains(response, "Cancelar e reverter estoque")

    def test_detalhe_exibe_rastreio_de_movimentacoes_de_estoque(self):
        self.client.force_login(self.admin)
        entrada = EntradaCompra.objects.create(
            fornecedor=self.fornecedor,
            filial=self.filial,
            usuario=self.usuario,
            numero_documento="NF-RASTREIO",
            gerar_conta_financeira=False,
        )
        ItemEntradaCompra.objects.create(
            entrada=entrada,
            produto=self.produto,
            quantidade=Decimal("2.000"),
            custo_unitario=Decimal("4.00"),
            total=Decimal("8.00"),
        )
        finalizar_entrada_compra(entrada)
        cancelar_entrada_compra(
            entrada,
            usuario=self.admin,
            motivo="Conferir rastreio",
            supervisor=self.admin_misto,
        )

        response = self.client.get(f"/compras/{entrada.id}/")

        self.assertContains(response, "Rastreio no estoque")
        self.assertContains(response, "Entrada")
        self.assertContains(response, "Saida")
        self.assertContains(response, "Feijao 1kg")
        self.assertContains(response, "R$ 8,00")

    def test_detalhe_compra_permite_baixar_conta_vinculada_e_voltar_para_entrada(self):
        self.client.force_login(self.admin)
        entrada = EntradaCompra.objects.create(
            fornecedor=self.fornecedor,
            filial=self.filial,
            usuario=self.usuario,
            numero_documento="NF-FINANCEIRO",
        )
        ItemEntradaCompra.objects.create(
            entrada=entrada,
            produto=self.produto,
            quantidade=Decimal("2.000"),
            custo_unitario=Decimal("6.00"),
            total=Decimal("12.00"),
        )
        finalizar_entrada_compra(entrada)
        conta = ContaFinanceira.objects.get(entrada_compra=entrada)

        response = self.client.get(f"/compras/{entrada.id}/")

        self.assertContains(response, "Financeiro vinculado")
        self.assertContains(response, "Baixar")
        self.assertContains(response, f"/financeiro/{conta.pk}/baixar/?next=/compras/{entrada.id}/")

    def test_detalhe_compra_exibe_rastreio_financeiro_da_baixa(self):
        self.client.force_login(self.admin)
        entrada = EntradaCompra.objects.create(
            fornecedor=self.fornecedor,
            filial=self.filial,
            usuario=self.usuario,
            numero_documento="NF-LIVRO",
        )
        ItemEntradaCompra.objects.create(
            entrada=entrada,
            produto=self.produto,
            quantidade=Decimal("2.000"),
            custo_unitario=Decimal("6.00"),
            total=Decimal("12.00"),
        )
        finalizar_entrada_compra(entrada)
        conta = ContaFinanceira.objects.get(entrada_compra=entrada)
        caixa = ContaMovimentoFinanceiro.objects.create(
            filial=self.filial,
            nome="Caixa administrativo",
            tipo=TipoContaMovimento.CAIXA,
        )
        baixar_conta(
            conta=conta,
            usuario=self.admin,
            data_pagamento=timezone.localdate(),
            valor_pago=Decimal("12.00"),
            forma_pagamento="Dinheiro",
            conta_movimento=caixa,
        )

        response = self.client.get(f"/compras/{entrada.id}/")

        self.assertContains(response, "Rastreio financeiro")
        self.assertContains(response, "Caixa administrativo")
        self.assertContains(response, "Saida")
        self.assertContains(response, "BAIXA_CONTA")
        self.assertContains(response, "R$ 12,00")

    def test_detalhe_compra_possui_pdf_individual_auditavel(self):
        self.client.force_login(self.admin)
        entrada = EntradaCompra.objects.create(
            fornecedor=self.fornecedor,
            filial=self.filial,
            usuario=self.usuario,
            numero_documento="NF-PDF-INDIVIDUAL",
        )
        ItemEntradaCompra.objects.create(
            entrada=entrada,
            produto=self.produto,
            quantidade=Decimal("2.000"),
            custo_unitario=Decimal("6.00"),
            total=Decimal("12.00"),
        )
        finalizar_entrada_compra(entrada)
        conta = ContaFinanceira.objects.get(entrada_compra=entrada)
        caixa = ContaMovimentoFinanceiro.objects.create(
            filial=self.filial,
            nome="Caixa PDF individual",
            tipo=TipoContaMovimento.CAIXA,
        )
        baixar_conta(
            conta=conta,
            usuario=self.admin,
            data_pagamento=timezone.localdate(),
            valor_pago=Decimal("12.00"),
            forma_pagamento="Dinheiro",
            conta_movimento=caixa,
        )

        detalhe = self.client.get(f"/compras/{entrada.id}/")
        impressao = self.client.get(f"/compras/{entrada.id}/imprimir/")

        self.assertContains(detalhe, f"/compras/{entrada.id}/imprimir/")
        self.assertContains(impressao, "Imprimir / Salvar como PDF")
        self.assertContains(impressao, "NF-PDF-INDIVIDUAL")
        self.assertContains(impressao, "Itens recebidos")
        self.assertContains(impressao, "Financeiro vinculado")
        self.assertContains(impressao, "Rastreio financeiro")
        self.assertContains(impressao, "Caixa PDF individual")
        self.assertContains(impressao, "BAIXA_CONTA")
        self.assertContains(impressao, "Rastreio no estoque")
        self.assertContains(impressao, "Feijao 1kg")

    def test_nova_entrada_pode_finalizar_com_supervisor_caixa_mista_e_atualiza_estoque(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            "/compras/nova/",
            {
                "fornecedor": self.fornecedor.id,
                "filial": self.filial.id,
                "numero_documento": "NF-102",
                "data_emissao": "",
                "vencimento_financeiro": "",
                "observacoes": "Recebimento direto",
                "itens-TOTAL_FORMS": "1",
                "itens-INITIAL_FORMS": "0",
                "itens-MIN_NUM_FORMS": "0",
                "itens-MAX_NUM_FORMS": "1000",
                "itens-0-produto": self.produto.id,
                "itens-0-quantidade": "4.000",
                "itens-0-custo_unitario": "4.50",
                "itens-0-atualizar_preco_custo": "on",
                "acao": "finalizar",
                "supervisor_usuario": "AdminMaster",
                "supervisor_senha": "123",
            },
            follow=True,
        )

        entrada = EntradaCompra.objects.get(numero_documento="NF-102")
        estoque = Estoque.objects.get(produto=self.produto, filial=self.filial)

        self.assertContains(response, "Entrada finalizada e estoque atualizado")
        self.assertEqual(entrada.status, StatusEntradaCompra.FINALIZADA)
        self.assertEqual(estoque.quantidade_atual, Decimal("4.000"))
        self.assertTrue(MovimentacaoEstoque.objects.filter(referencia=f"entrada_compra:{entrada.id}").exists())

    def test_form_entrada_exibe_secoes_operacionais(self):
        self.client.force_login(self.admin)

        response = self.client.get("/compras/nova/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dados da entrada")
        self.assertContains(response, "Itens recebidos")
        self.assertContains(response, "Ao finalizar, o sistema atualiza estoque e financeiro.")
        self.assertContains(response, "Salvar rascunho nao altera estoque")
        self.assertContains(response, 'name="supervisor_usuario" autocomplete="username"')
        self.assertContains(response, 'class="no-upper"')
        self.assertContains(response, "select2-field")
        self.assertContains(response, 'data-ajax-url="/fornecedores/busca.json"')
        self.assertContains(response, 'data-ajax-url="/empresas/filiais/busca.json"')
        self.assertContains(response, 'data-ajax-url="/estoque/produtos/busca.json"')

    def test_lista_compras_destaca_rascunhos_e_filtra_status(self):
        self.client.force_login(self.admin)
        rascunho = EntradaCompra.objects.create(
            fornecedor=self.fornecedor,
            filial=self.filial,
            usuario=self.usuario,
            numero_documento="NF-RASCUNHO",
        )
        finalizada = EntradaCompra.objects.create(
            fornecedor=self.fornecedor,
            filial=self.filial,
            usuario=self.usuario,
            numero_documento="NF-FINAL",
            status=StatusEntradaCompra.FINALIZADA,
            total_produtos=Decimal("20.00"),
        )

        lista = self.client.get("/compras/")
        apenas_rascunhos = self.client.get("/compras/", {"status": StatusEntradaCompra.RASCUNHO})

        self.assertContains(lista, "Rascunhos")
        self.assertContains(lista, "Existem 1 entrada(s) em rascunho")
        self.assertContains(lista, "R$ 20,00")
        self.assertContains(lista, rascunho.numero_documento)
        self.assertContains(lista, finalizada.numero_documento)
        self.assertContains(apenas_rascunhos, rascunho.numero_documento)
        self.assertNotContains(apenas_rascunhos, finalizada.numero_documento)

    def test_excluir_rascunho_de_compra_remove_itens_sem_movimentar_estoque(self):
        self.client.force_login(self.admin)
        entrada = EntradaCompra.objects.create(
            fornecedor=self.fornecedor,
            filial=self.filial,
            usuario=self.usuario,
            numero_documento="NF-RASC-DEL",
        )
        ItemEntradaCompra.objects.create(
            entrada=entrada,
            produto=self.produto,
            quantidade=Decimal("2.000"),
            custo_unitario=Decimal("5.00"),
            total=Decimal("10.00"),
        )

        detalhe = self.client.get(f"/compras/{entrada.id}/")
        self.assertContains(detalhe, "Excluir rascunho")

        response = self.client.post(
            f"/compras/{entrada.id}/excluir-rascunho/",
            {"next": "/compras/?status=RASCUNHO"},
            follow=True,
        )

        self.assertContains(response, "Rascunho de compra excluído com sucesso")
        self.assertFalse(EntradaCompra.objects.filter(pk=entrada.pk).exists())
        self.assertEqual(MovimentacaoEstoque.objects.count(), 0)
        self.assertEqual(ContaFinanceira.objects.count(), 0)
        self.assertTrue(LogAuditoria.objects.filter(acao="ENTRADA_COMPRA_RASCUNHO_EXCLUIDA", objeto_id=str(entrada.id)).exists())

    def test_excluir_rascunho_de_compra_bloqueia_entrada_finalizada(self):
        self.client.force_login(self.admin)
        entrada = EntradaCompra.objects.create(
            fornecedor=self.fornecedor,
            filial=self.filial,
            usuario=self.usuario,
            numero_documento="NF-FINAL-NAO-DEL",
            status=StatusEntradaCompra.FINALIZADA,
        )

        response = self.client.post(f"/compras/{entrada.id}/excluir-rascunho/", follow=True)

        self.assertContains(response, "Somente entradas em rascunho podem ser excluídas")
        self.assertTrue(EntradaCompra.objects.filter(pk=entrada.pk).exists())

    def test_lista_compras_exibe_status_financeiro_da_entrada(self):
        self.client.force_login(self.admin)
        sem_conta = EntradaCompra.objects.create(
            fornecedor=self.fornecedor,
            filial=self.filial,
            usuario=self.usuario,
            numero_documento="NF-SEM-CONTA",
            status=StatusEntradaCompra.FINALIZADA,
            total_produtos=Decimal("10.00"),
        )
        paga = EntradaCompra.objects.create(
            fornecedor=self.fornecedor,
            filial=self.filial,
            usuario=self.usuario,
            numero_documento="NF-PAGA",
            status=StatusEntradaCompra.FINALIZADA,
            total_produtos=Decimal("15.00"),
        )
        ContaFinanceira.objects.create(
            tipo=TipoContaFinanceira.PAGAR,
            status=StatusContaFinanceira.PAGA,
            descricao="Compra paga na lista",
            filial=self.filial,
            fornecedor=self.fornecedor,
            entrada_compra=paga,
            valor=Decimal("15.00"),
            vencimento=timezone.localdate(),
            data_pagamento=timezone.localdate(),
            valor_pago=Decimal("15.00"),
            usuario=self.usuario,
        )

        response = self.client.get("/compras/")

        self.assertContains(response, sem_conta.numero_documento)
        self.assertContains(response, "Financeiro")
        self.assertContains(response, "Sem conta")
        self.assertContains(response, "Paga")
        self.assertContains(response, "pago em")

    def test_lista_compras_filtra_por_status_financeiro(self):
        self.client.force_login(self.admin)
        sem_conta = EntradaCompra.objects.create(
            fornecedor=self.fornecedor,
            filial=self.filial,
            usuario=self.usuario,
            numero_documento="NF-FILTRO-SEM-CONTA",
            status=StatusEntradaCompra.FINALIZADA,
            total_produtos=Decimal("10.00"),
        )
        vencida = EntradaCompra.objects.create(
            fornecedor=self.fornecedor,
            filial=self.filial,
            usuario=self.usuario,
            numero_documento="NF-FILTRO-VENCIDA",
            status=StatusEntradaCompra.FINALIZADA,
            total_produtos=Decimal("15.00"),
        )
        paga = EntradaCompra.objects.create(
            fornecedor=self.fornecedor,
            filial=self.filial,
            usuario=self.usuario,
            numero_documento="NF-FILTRO-PAGA",
            status=StatusEntradaCompra.FINALIZADA,
            total_produtos=Decimal("20.00"),
        )
        ContaFinanceira.objects.create(
            tipo=TipoContaFinanceira.PAGAR,
            status=StatusContaFinanceira.ABERTA,
            descricao="Compra vencida filtro",
            filial=self.filial,
            fornecedor=self.fornecedor,
            entrada_compra=vencida,
            valor=Decimal("15.00"),
            vencimento=timezone.localdate() - timedelta(days=1),
            usuario=self.usuario,
        )
        ContaFinanceira.objects.create(
            tipo=TipoContaFinanceira.PAGAR,
            status=StatusContaFinanceira.PAGA,
            descricao="Compra paga filtro",
            filial=self.filial,
            fornecedor=self.fornecedor,
            entrada_compra=paga,
            valor=Decimal("20.00"),
            vencimento=timezone.localdate(),
            data_pagamento=timezone.localdate(),
            valor_pago=Decimal("20.00"),
            usuario=self.usuario,
        )

        apenas_sem_conta = self.client.get("/compras/", {"financeiro": "SEM_CONTA"})
        apenas_vencidas = self.client.get("/compras/", {"financeiro": "VENCIDA"})
        apenas_pagas = self.client.get("/compras/", {"financeiro": "PAGA"})

        self.assertContains(apenas_sem_conta, sem_conta.numero_documento)
        self.assertNotContains(apenas_sem_conta, vencida.numero_documento)
        self.assertContains(apenas_vencidas, vencida.numero_documento)
        self.assertNotContains(apenas_vencidas, paga.numero_documento)
        self.assertContains(apenas_pagas, paga.numero_documento)
        self.assertNotContains(apenas_pagas, sem_conta.numero_documento)

    def test_lista_compras_exibe_resumo_financeiro_das_contas_vinculadas(self):
        self.client.force_login(self.admin)
        aberta = EntradaCompra.objects.create(
            fornecedor=self.fornecedor,
            filial=self.filial,
            usuario=self.usuario,
            numero_documento="NF-RESUMO-ABERTA",
            status=StatusEntradaCompra.FINALIZADA,
            total_produtos=Decimal("30.00"),
        )
        vencida = EntradaCompra.objects.create(
            fornecedor=self.fornecedor,
            filial=self.filial,
            usuario=self.usuario,
            numero_documento="NF-RESUMO-VENCIDA",
            status=StatusEntradaCompra.FINALIZADA,
            total_produtos=Decimal("40.00"),
        )
        paga = EntradaCompra.objects.create(
            fornecedor=self.fornecedor,
            filial=self.filial,
            usuario=self.usuario,
            numero_documento="NF-RESUMO-PAGA",
            status=StatusEntradaCompra.FINALIZADA,
            total_produtos=Decimal("50.00"),
        )
        ContaFinanceira.objects.create(
            tipo=TipoContaFinanceira.PAGAR,
            status=StatusContaFinanceira.ABERTA,
            descricao="Compra aberta resumo",
            filial=self.filial,
            fornecedor=self.fornecedor,
            entrada_compra=aberta,
            valor=Decimal("30.00"),
            vencimento=timezone.localdate(),
            usuario=self.usuario,
        )
        ContaFinanceira.objects.create(
            tipo=TipoContaFinanceira.PAGAR,
            status=StatusContaFinanceira.ABERTA,
            descricao="Compra vencida resumo",
            filial=self.filial,
            fornecedor=self.fornecedor,
            entrada_compra=vencida,
            valor=Decimal("40.00"),
            vencimento=timezone.localdate() - timedelta(days=1),
            usuario=self.usuario,
        )
        ContaFinanceira.objects.create(
            tipo=TipoContaFinanceira.PAGAR,
            status=StatusContaFinanceira.PAGA,
            descricao="Compra paga resumo",
            filial=self.filial,
            fornecedor=self.fornecedor,
            entrada_compra=paga,
            valor=Decimal("50.00"),
            vencimento=timezone.localdate(),
            valor_pago=Decimal("50.00"),
            data_pagamento=timezone.localdate(),
            usuario=self.usuario,
        )

        response = self.client.get("/compras/")

        self.assertContains(response, "Contas abertas")
        self.assertContains(response, "Vencidas")
        self.assertContains(response, "Pagas")
        self.assertContains(response, 'href="?financeiro=ABERTA"')
        self.assertContains(response, 'href="?financeiro=VENCIDA"')
        self.assertContains(response, 'href="?financeiro=PAGA"')
        self.assertContains(response, "R$ 70,00")
        self.assertContains(response, "R$ 40,00")
        self.assertContains(response, "R$ 50,00")

    def test_cards_financeiros_preservam_filtros_atuais(self):
        self.client.force_login(self.admin)

        response = self.client.get(
            "/compras/",
            {"q": "Fornecedor", "status": StatusEntradaCompra.FINALIZADA, "financeiro": "PAGA"},
        )

        self.assertContains(response, 'href="?q=Fornecedor&amp;status=FINALIZADA&amp;financeiro=ABERTA"')
        self.assertContains(response, 'href="?q=Fornecedor&amp;status=FINALIZADA&amp;financeiro=VENCIDA"')
        self.assertContains(response, 'href="?q=Fornecedor&amp;status=FINALIZADA&amp;financeiro=PAGA"')

    def test_lista_compras_exibe_limpar_filtros_apenas_quando_necessario(self):
        self.client.force_login(self.admin)

        sem_filtro = self.client.get("/compras/")
        com_filtro = self.client.get("/compras/", {"financeiro": "VENCIDA"})

        self.assertNotContains(sem_filtro, "Limpar filtros")
        self.assertContains(com_filtro, "Limpar filtros")
        self.assertContains(com_filtro, 'href="/compras/"')

    def test_lista_compras_exibe_chips_de_filtros_aplicados(self):
        self.client.force_login(self.admin)

        sem_filtro = self.client.get("/compras/")
        com_filtro = self.client.get(
            "/compras/",
            {"q": "NF", "status": StatusEntradaCompra.RASCUNHO, "financeiro": "SEM_CONTA"},
        )

        self.assertNotContains(sem_filtro, "active-filters")
        self.assertContains(com_filtro, "active-filters")
        self.assertContains(com_filtro, "<strong>Busca:</strong> NF", html=True)
        self.assertContains(com_filtro, "<strong>Status:</strong> Rascunho", html=True)
        self.assertContains(com_filtro, "<strong>Financeiro:</strong> Sem conta financeira", html=True)

    def test_detalhe_compra_preserva_retorno_para_lista_filtrada(self):
        self.client.force_login(self.admin)
        entrada = EntradaCompra.objects.create(
            fornecedor=self.fornecedor,
            filial=self.filial,
            usuario=self.usuario,
            numero_documento="NF-RETORNO",
            status=StatusEntradaCompra.FINALIZADA,
            total_produtos=Decimal("10.00"),
        )

        lista = self.client.get("/compras/", {"financeiro": "SEM_CONTA", "status": StatusEntradaCompra.FINALIZADA})
        detalhe = self.client.get(
            f"/compras/{entrada.id}/",
            {"next": "/compras/?financeiro=SEM_CONTA&status=FINALIZADA"},
        )
        detalhe_next_externo = self.client.get(
            f"/compras/{entrada.id}/",
            {"next": "https://exemplo.invalid/compras/"},
        )

        self.assertContains(lista, f"/compras/{entrada.id}/?next=/compras/%3Ffinanceiro%3DSEM_CONTA%26status%3DFINALIZADA")
        self.assertContains(detalhe, 'href="/compras/?financeiro=SEM_CONTA&amp;status=FINALIZADA"')
        self.assertContains(detalhe_next_externo, 'href="/compras/"')

    def test_edicao_rascunho_preserva_retorno_para_lista_filtrada(self):
        self.client.force_login(self.admin)
        entrada = EntradaCompra.objects.create(
            fornecedor=self.fornecedor,
            filial=self.filial,
            usuario=self.usuario,
            numero_documento="NF-EDIT-RETORNO",
        )
        item = ItemEntradaCompra.objects.create(
            entrada=entrada,
            produto=self.produto,
            quantidade=Decimal("2.000"),
            custo_unitario=Decimal("5.00"),
            total=Decimal("10.00"),
        )
        retorno = "/compras/?financeiro=SEM_CONTA&status=RASCUNHO"

        detalhe = self.client.get(f"/compras/{entrada.id}/", {"next": retorno})
        form = self.client.get(f"/compras/{entrada.id}/editar/", {"next": retorno})
        response = self.client.post(
            f"/compras/{entrada.id}/editar/?next={retorno}",
            {
                "fornecedor": self.fornecedor.id,
                "filial": self.filial.id,
                "numero_documento": "NF-EDIT-RETORNO-OK",
                "data_emissao": "",
                "vencimento_financeiro": "",
                "gerar_conta_financeira": "on",
                "observacoes": "",
                "itens-TOTAL_FORMS": "1",
                "itens-INITIAL_FORMS": "1",
                "itens-MIN_NUM_FORMS": "0",
                "itens-MAX_NUM_FORMS": "1000",
                "itens-0-id": item.id,
                "itens-0-produto": self.produto.id,
                "itens-0-quantidade": "2.000",
                "itens-0-custo_unitario": "5.00",
                "itens-0-atualizar_preco_custo": "on",
                "acao": "rascunho",
                "next": retorno,
            },
        )

        self.assertContains(detalhe, f"/compras/{entrada.id}/editar/?next=/compras/%3Ffinanceiro%3DSEM_CONTA%26status%3DRASCUNHO")
        self.assertContains(form, 'name="next" value="/compras/?financeiro=SEM_CONTA&amp;status=RASCUNHO"')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], f"/compras/{entrada.id}/?next=%2Fcompras%2F%3Ffinanceiro%3DSEM_CONTA%26status%3DRASCUNHO")

    def test_exporta_compras_csv_com_filtros_operacionais(self):
        self.client.force_login(self.admin)
        aberta = EntradaCompra.objects.create(
            fornecedor=self.fornecedor,
            filial=self.filial,
            usuario=self.usuario,
            numero_documento="NF-CSV-ABERTA",
            status=StatusEntradaCompra.FINALIZADA,
            total_produtos=Decimal("30.00"),
        )
        paga = EntradaCompra.objects.create(
            fornecedor=self.fornecedor,
            filial=self.filial,
            usuario=self.usuario,
            numero_documento="NF-CSV-PAGA",
            status=StatusEntradaCompra.FINALIZADA,
            total_produtos=Decimal("20.00"),
        )
        ContaFinanceira.objects.create(
            tipo=TipoContaFinanceira.PAGAR,
            status=StatusContaFinanceira.ABERTA,
            descricao="Compra aberta csv",
            filial=self.filial,
            fornecedor=self.fornecedor,
            entrada_compra=aberta,
            valor=Decimal("30.00"),
            vencimento=timezone.localdate(),
            usuario=self.usuario,
        )
        ContaFinanceira.objects.create(
            tipo=TipoContaFinanceira.PAGAR,
            status=StatusContaFinanceira.PAGA,
            descricao="Compra paga csv",
            filial=self.filial,
            fornecedor=self.fornecedor,
            entrada_compra=paga,
            valor=Decimal("20.00"),
            vencimento=timezone.localdate(),
            data_pagamento=timezone.localdate(),
            valor_pago=Decimal("20.00"),
            usuario=self.usuario,
        )

        response = self.client.get("/compras/exportar.csv", {"financeiro": "PAGA"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("compras_operacionais.csv", response["Content-Disposition"])
        self.assertIn(b"Status financeiro", response.content)
        self.assertIn(b"NF-CSV-PAGA", response.content)
        self.assertNotIn(b"NF-CSV-ABERTA", response.content)

    def test_impressao_compras_respeita_filtros_operacionais(self):
        self.client.force_login(self.admin)
        aberta = EntradaCompra.objects.create(
            fornecedor=self.fornecedor,
            filial=self.filial,
            usuario=self.usuario,
            numero_documento="NF-PRINT-ABERTA",
            status=StatusEntradaCompra.FINALIZADA,
            total_produtos=Decimal("30.00"),
        )
        paga = EntradaCompra.objects.create(
            fornecedor=self.fornecedor,
            filial=self.filial,
            usuario=self.usuario,
            numero_documento="NF-PRINT-PAGA",
            status=StatusEntradaCompra.FINALIZADA,
            total_produtos=Decimal("20.00"),
        )
        ContaFinanceira.objects.create(
            tipo=TipoContaFinanceira.PAGAR,
            status=StatusContaFinanceira.ABERTA,
            descricao="Compra aberta print",
            filial=self.filial,
            fornecedor=self.fornecedor,
            entrada_compra=aberta,
            valor=Decimal("30.00"),
            vencimento=timezone.localdate(),
            usuario=self.usuario,
        )
        ContaFinanceira.objects.create(
            tipo=TipoContaFinanceira.PAGAR,
            status=StatusContaFinanceira.PAGA,
            descricao="Compra paga print",
            filial=self.filial,
            fornecedor=self.fornecedor,
            entrada_compra=paga,
            valor=Decimal("20.00"),
            vencimento=timezone.localdate(),
            data_pagamento=timezone.localdate(),
            valor_pago=Decimal("20.00"),
            usuario=self.usuario,
        )

        response = self.client.get("/compras/imprimir/", {"financeiro": "PAGA"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Compras operacionais")
        self.assertContains(response, "Imprimir / Salvar como PDF")
        self.assertContains(response, "NF-PRINT-PAGA")
        self.assertContains(response, "Total pago")
        self.assertContains(response, "R$ 20,00")
        self.assertNotContains(response, "NF-PRINT-ABERTA")

# Create your tests here.
