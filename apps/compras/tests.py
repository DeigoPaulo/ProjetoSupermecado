from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import PerfilUsuario, TipoPerfil
from apps.auditoria.models import LogAuditoria
from apps.empresas.models import Empresa, Filial
from apps.estoque.models import Estoque, LoteEstoque, MovimentacaoEstoque, TipoMovimentacaoEstoque
from apps.financeiro.models import ContaFinanceira, ContaMovimentoFinanceiro, StatusContaFinanceira, TipoContaFinanceira, TipoContaMovimento
from apps.financeiro.services import baixar_conta
from apps.fornecedores.models import Fornecedor
from apps.produtos.models import Categoria, Produto

from .models import (
    CotacaoCompra,
    EntradaCompra,
    ItemCotacaoCompra,
    ItemEntradaCompra,
    ItemPedidoCompra,
    PedidoCompra,
    PrecoRespostaCotacao,
    RespostaCotacaoFornecedor,
    StatusCotacaoCompra,
    StatusEntradaCompra,
    StatusPedidoCompra,
)
from .services import (
    abrir_cotacao_compra,
    cancelar_entrada_compra,
    cancelar_pedido_compra,
    converter_pedido_em_entrada,
    enviar_pedido_compra,
    finalizar_entrada_compra,
    gerar_pedido_da_resposta,
)
from .services_xml import importar_xml_entrada, ler_xml_nfe


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


class PedidosCompraTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_superuser("gestor_compras", "compras@example.com", "123")
        self.empresa = Empresa.objects.create(
            razao_social="Mercado Pedido",
            nome_fantasia="Mercado Pedido",
            cnpj="66.666.666/0001-66",
        )
        self.filial = Filial.objects.create(
            empresa=self.empresa,
            nome="Matriz Pedido",
            cnpj=self.empresa.cnpj,
        )
        self.fornecedor = Fornecedor.objects.create(
            razao_social="Fornecedor Pedido Ltda",
            nome_fantasia="Fornecedor Pedido",
        )
        self.categoria = Categoria.all_objects.create(nome="Categoria Pedido")
        self.produto = Produto.objects.create(
            codigo_barras="7896666666666",
            nome="Produto para pedido",
            categoria=self.categoria,
            preco_custo=Decimal("4.00"),
            preco_venda=Decimal("8.00"),
        )
        self.client.force_login(self.usuario)

    def _pedido(self, *, com_item=True):
        pedido = PedidoCompra.objects.create(
            fornecedor=self.fornecedor,
            filial=self.filial,
            usuario=self.usuario,
            referencia="PC-TESTE",
        )
        if com_item:
            ItemPedidoCompra.objects.create(
                pedido=pedido,
                produto=self.produto,
                quantidade=Decimal("3.000"),
                custo_unitario_previsto=Decimal("5.00"),
                total_previsto=Decimal("15.00"),
            )
            pedido.total_previsto = Decimal("15.00")
            pedido.save(update_fields=["total_previsto", "updated_at"])
        return pedido

    def test_cria_rascunho_sem_movimentar_estoque_ou_financeiro(self):
        response = self.client.post(
            "/compras/pedidos/novo/",
            {
                "fornecedor": self.fornecedor.pk,
                "filial": self.filial.pk,
                "referencia": "PC-001",
                "previsao_entrega": "",
                "observacoes": "Primeiro pedido",
                "itens-TOTAL_FORMS": "1",
                "itens-INITIAL_FORMS": "0",
                "itens-MIN_NUM_FORMS": "0",
                "itens-MAX_NUM_FORMS": "1000",
                "itens-0-produto": self.produto.pk,
                "itens-0-quantidade": "3.000",
                "itens-0-custo_unitario_previsto": "5.00",
            },
            follow=True,
        )

        pedido = PedidoCompra.objects.get(referencia="PC-001")
        self.assertContains(response, "Pedido de compra salvo como rascunho")
        self.assertEqual(pedido.status, StatusPedidoCompra.RASCUNHO)
        self.assertEqual(pedido.total_previsto, Decimal("15.00"))
        self.assertEqual(pedido.itens.get().total_previsto, Decimal("15.00"))
        self.assertEqual(Estoque.objects.count(), 0)
        self.assertEqual(MovimentacaoEstoque.objects.count(), 0)
        self.assertEqual(ContaFinanceira.objects.count(), 0)
        self.assertTrue(
            LogAuditoria.objects.filter(
                acao="CRIACAO_PEDIDO_COMPRA",
                objeto_id=str(pedido.id),
            ).exists()
        )

    def test_enviar_pedido_calcula_total_e_mantem_estoque_financeiro_intactos(self):
        pedido = self._pedido()
        pedido.itens.update(total_previsto=0)

        response = self.client.post(f"/compras/pedidos/{pedido.pk}/enviar/", follow=True)

        pedido.refresh_from_db()
        self.assertContains(response, "Pedido marcado como enviado")
        self.assertEqual(pedido.status, StatusPedidoCompra.ENVIADO)
        self.assertEqual(pedido.total_previsto, Decimal("15.00"))
        self.assertIsNotNone(pedido.enviado_em)
        self.assertEqual(Estoque.objects.count(), 0)
        self.assertEqual(MovimentacaoEstoque.objects.count(), 0)
        self.assertEqual(ContaFinanceira.objects.count(), 0)
        self.assertTrue(LogAuditoria.objects.filter(acao="ENVIO_PEDIDO_COMPRA", objeto_id=str(pedido.id)).exists())

    def test_pedido_sem_itens_nao_pode_ser_enviado(self):
        pedido = self._pedido(com_item=False)

        response = self.client.post(f"/compras/pedidos/{pedido.pk}/enviar/", follow=True)

        pedido.refresh_from_db()
        self.assertContains(response, "Inclua ao menos um item")
        self.assertEqual(pedido.status, StatusPedidoCompra.RASCUNHO)
        self.assertIsNone(pedido.enviado_em)

    def test_pedido_enviado_nao_pode_ser_editado(self):
        pedido = self._pedido()
        enviar_pedido_compra(pedido, usuario=self.usuario)

        response = self.client.get(f"/compras/pedidos/{pedido.pk}/editar/", follow=True)

        self.assertContains(response, "Somente pedidos em rascunho podem ser editados")
        self.assertContains(response, "Enviado ao fornecedor")

    def test_cancelamento_exige_motivo_e_nao_movimenta_outros_modulos(self):
        pedido = self._pedido()

        sem_motivo = self.client.post(f"/compras/pedidos/{pedido.pk}/cancelar/", {"motivo": ""}, follow=True)
        self.assertContains(sem_motivo, "Informe o motivo")
        pedido.refresh_from_db()
        self.assertEqual(pedido.status, StatusPedidoCompra.RASCUNHO)

        cancelar_pedido_compra(
            pedido,
            usuario=self.usuario,
            motivo="Fornecedor indisponivel",
        )
        pedido.refresh_from_db()

        self.assertEqual(pedido.status, StatusPedidoCompra.CANCELADO)
        self.assertIsNotNone(pedido.cancelado_em)
        self.assertEqual(Estoque.objects.count(), 0)
        self.assertEqual(ContaFinanceira.objects.count(), 0)
        self.assertTrue(
            LogAuditoria.objects.filter(
                acao="CANCELAMENTO_PEDIDO_COMPRA",
                objeto_id=str(pedido.id),
            ).exists()
        )

    def test_telas_separam_pedido_de_entrada_recebida(self):
        pedido = self._pedido()

        lista = self.client.get("/compras/pedidos/")
        detalhe = self.client.get(f"/compras/pedidos/{pedido.pk}/")
        entradas = self.client.get("/compras/")

        self.assertContains(lista, "Pedidos de compra")
        self.assertContains(lista, "não movimentam estoque")
        self.assertContains(detalhe, "não cria conta a pagar")
        self.assertContains(detalhe, "Marcar como enviado")
        self.assertContains(entradas, "Pedidos de compra")

    def test_conversao_cria_entrada_rascunho_sem_estoque_ou_financeiro(self):
        pedido = self._pedido()
        enviar_pedido_compra(pedido, usuario=self.usuario)

        response = self.client.post(f"/compras/pedidos/{pedido.pk}/gerar-entrada/", follow=True)

        pedido.refresh_from_db()
        entrada = EntradaCompra.objects.get(pedido_origem=pedido)
        item = entrada.itens.get()
        self.assertContains(response, "Entrada criada como rascunho")
        self.assertContains(response, f"pedido de compra")
        self.assertEqual(pedido.status, StatusPedidoCompra.CONVERTIDO)
        self.assertEqual(entrada.status, StatusEntradaCompra.RASCUNHO)
        self.assertEqual(entrada.fornecedor, pedido.fornecedor)
        self.assertEqual(entrada.filial, pedido.filial)
        self.assertEqual(item.produto, self.produto)
        self.assertEqual(item.quantidade, Decimal("3.000"))
        self.assertEqual(item.custo_unitario, Decimal("5.00"))
        self.assertEqual(Estoque.objects.count(), 0)
        self.assertEqual(MovimentacaoEstoque.objects.count(), 0)
        self.assertEqual(ContaFinanceira.objects.count(), 0)
        self.assertTrue(
            LogAuditoria.objects.filter(
                acao="CONVERSAO_PEDIDO_EM_ENTRADA",
                objeto_id=str(pedido.id),
            ).exists()
        )

    def test_pedido_so_pode_gerar_uma_entrada(self):
        pedido = self._pedido()
        enviar_pedido_compra(pedido, usuario=self.usuario)
        entrada = converter_pedido_em_entrada(pedido, usuario=self.usuario)

        with self.assertRaisesMessage(ValidationError, "Apenas pedidos enviados"):
            converter_pedido_em_entrada(pedido, usuario=self.usuario)

        self.assertEqual(EntradaCompra.objects.filter(pedido_origem=pedido).count(), 1)
        self.assertEqual(entrada.status, StatusEntradaCompra.RASCUNHO)

    def test_excluir_entrada_convertida_reabre_pedido_enviado(self):
        pedido = self._pedido()
        enviar_pedido_compra(pedido, usuario=self.usuario)
        entrada = converter_pedido_em_entrada(pedido, usuario=self.usuario)

        response = self.client.post(
            f"/compras/{entrada.pk}/excluir-rascunho/",
            {"next": "/compras/pedidos/"},
            follow=True,
        )

        pedido.refresh_from_db()
        self.assertContains(response, "Pedidos de compra")
        self.assertFalse(EntradaCompra.objects.filter(pk=entrada.pk).exists())
        self.assertEqual(pedido.status, StatusPedidoCompra.ENVIADO)
        self.assertTrue(
            LogAuditoria.objects.filter(
                acao="REABERTURA_PEDIDO_APOS_EXCLUSAO_ENTRADA",
                objeto_id=str(pedido.id),
            ).exists()
        )

    def test_finalizar_entrada_convertida_usa_fluxo_existente(self):
        pedido = self._pedido()
        enviar_pedido_compra(pedido, usuario=self.usuario)
        entrada = converter_pedido_em_entrada(pedido, usuario=self.usuario)

        finalizar_entrada_compra(entrada)

        entrada.refresh_from_db()
        pedido.refresh_from_db()
        self.assertEqual(entrada.status, StatusEntradaCompra.FINALIZADA)
        self.assertEqual(pedido.status, StatusPedidoCompra.CONVERTIDO)
        self.assertEqual(
            Estoque.objects.get(produto=self.produto, filial=self.filial).quantidade_atual,
            Decimal("3.000"),
        )
        self.assertTrue(ContaFinanceira.objects.filter(entrada_compra=entrada).exists())


class CotacoesCompraTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_superuser("cotador", "cotador@example.com", "123")
        self.empresa = Empresa.objects.create(
            razao_social="Mercado Cotacao",
            nome_fantasia="Mercado Cotacao",
            cnpj="77.777.777/0001-77",
        )
        self.filial = Filial.objects.create(
            empresa=self.empresa,
            nome="Matriz Cotacao",
            cnpj=self.empresa.cnpj,
        )
        self.fornecedor_a = Fornecedor.objects.create(
            empresa=self.empresa,
            razao_social="Fornecedor Cotacao A",
            nome_fantasia="Fornecedor A",
        )
        self.fornecedor_b = Fornecedor.objects.create(
            empresa=self.empresa,
            razao_social="Fornecedor Cotacao B",
            nome_fantasia="Fornecedor B",
        )
        self.categoria = Categoria.all_objects.create(nome="Categoria Cotacao")
        self.produto_a = Produto.objects.create(
            codigo_barras="7897777777771",
            nome="Produto Cotado A",
            categoria=self.categoria,
            preco_custo=Decimal("4.00"),
            preco_venda=Decimal("8.00"),
        )
        self.produto_b = Produto.objects.create(
            codigo_barras="7897777777772",
            nome="Produto Cotado B",
            categoria=self.categoria,
            preco_custo=Decimal("6.00"),
            preco_venda=Decimal("12.00"),
        )
        self.client.force_login(self.usuario)

    def _cotacao(self, *, aberta=True):
        cotacao = CotacaoCompra.objects.create(
            filial=self.filial,
            usuario=self.usuario,
            referencia="COT-TESTE",
        )
        ItemCotacaoCompra.objects.create(
            cotacao=cotacao,
            produto=self.produto_a,
            quantidade=Decimal("2.000"),
        )
        ItemCotacaoCompra.objects.create(
            cotacao=cotacao,
            produto=self.produto_b,
            quantidade=Decimal("3.000"),
        )
        if aberta:
            cotacao = abrir_cotacao_compra(cotacao, usuario=self.usuario)
        return cotacao

    def _resposta(self, cotacao, fornecedor, custo_a, custo_b, *, disponivel_b=True):
        resposta = RespostaCotacaoFornecedor.objects.create(
            cotacao=cotacao,
            fornecedor=fornecedor,
            prazo_entrega_dias=3,
            usuario=self.usuario,
        )
        itens = list(cotacao.itens.order_by("id"))
        PrecoRespostaCotacao.objects.create(
            resposta=resposta,
            item=itens[0],
            disponivel=True,
            custo_unitario=Decimal(custo_a),
        )
        PrecoRespostaCotacao.objects.create(
            resposta=resposta,
            item=itens[1],
            disponivel=disponivel_b,
            custo_unitario=Decimal(custo_b) if disponivel_b else None,
        )
        return resposta

    def test_cria_e_abre_cotacao_sem_impacto_operacional(self):
        response = self.client.post(
            "/compras/cotacoes/nova/",
            {
                "filial": self.filial.pk,
                "referencia": "COT-001",
                "validade": "",
                "observacoes": "Comparar fornecedores",
                "itens-TOTAL_FORMS": "1",
                "itens-INITIAL_FORMS": "0",
                "itens-MIN_NUM_FORMS": "0",
                "itens-MAX_NUM_FORMS": "1000",
                "itens-0-produto": self.produto_a.pk,
                "itens-0-quantidade": "2.000",
            },
            follow=True,
        )

        cotacao = CotacaoCompra.objects.get(referencia="COT-001")
        self.assertContains(response, "Cotacao salva como rascunho")
        self.assertEqual(cotacao.status, StatusCotacaoCompra.RASCUNHO)
        abertura = self.client.post(f"/compras/cotacoes/{cotacao.pk}/abrir/", follow=True)
        cotacao.refresh_from_db()
        self.assertContains(abertura, "Cotacao aberta")
        self.assertEqual(cotacao.status, StatusCotacaoCompra.ABERTA)
        self.assertEqual(Estoque.objects.count(), 0)
        self.assertEqual(ContaFinanceira.objects.count(), 0)

    def test_registra_proposta_com_precos_para_todos_os_itens(self):
        cotacao = self._cotacao()
        itens = list(cotacao.itens.order_by("id"))

        response = self.client.post(
            f"/compras/cotacoes/{cotacao.pk}/proposta/",
            {
                "fornecedor": self.fornecedor_a.pk,
                "prazo_entrega_dias": "4",
                "observacoes": "Entrega semanal",
                "precos-TOTAL_FORMS": "2",
                "precos-INITIAL_FORMS": "0",
                "precos-MIN_NUM_FORMS": "0",
                "precos-MAX_NUM_FORMS": "1000",
                "precos-0-item": itens[0].pk,
                "precos-0-disponivel": "on",
                "precos-0-custo_unitario": "5.00",
                "precos-1-item": itens[1].pk,
                "precos-1-disponivel": "on",
                "precos-1-custo_unitario": "7.00",
            },
            follow=True,
        )

        resposta = RespostaCotacaoFornecedor.objects.get(cotacao=cotacao, fornecedor=self.fornecedor_a)
        self.assertContains(response, "Proposta registrada para comparacao")
        self.assertContains(response, "Fornecedor A")
        self.assertContains(response, "R$ 31,00")
        self.assertEqual(resposta.precos.count(), 2)
        self.assertTrue(LogAuditoria.objects.filter(acao="REGISTRO_PROPOSTA_COTACAO").exists())

    def test_seleciona_melhor_proposta_e_gera_pedido_rascunho(self):
        cotacao = self._cotacao()
        resposta_a = self._resposta(cotacao, self.fornecedor_a, "5.00", "7.00")
        resposta_b = self._resposta(cotacao, self.fornecedor_b, "4.50", "6.50")

        pedido = gerar_pedido_da_resposta(resposta_b, usuario=self.usuario)

        cotacao.refresh_from_db()
        resposta_a.refresh_from_db()
        resposta_b.refresh_from_db()
        self.assertEqual(cotacao.status, StatusCotacaoCompra.ENCERRADA)
        self.assertFalse(resposta_a.selecionada)
        self.assertTrue(resposta_b.selecionada)
        self.assertEqual(pedido.status, StatusPedidoCompra.RASCUNHO)
        self.assertEqual(pedido.cotacao_origem, cotacao)
        self.assertEqual(pedido.fornecedor, self.fornecedor_b)
        self.assertEqual(pedido.total_previsto, Decimal("28.50"))
        self.assertEqual(pedido.itens.count(), 2)
        self.assertEqual(Estoque.objects.count(), 0)
        self.assertEqual(ContaFinanceira.objects.count(), 0)
        self.assertTrue(LogAuditoria.objects.filter(acao="SELECAO_PROPOSTA_COTACAO").exists())

    def test_proposta_incompleta_nao_pode_gerar_pedido(self):
        cotacao = self._cotacao()
        resposta = self._resposta(
            cotacao,
            self.fornecedor_a,
            "5.00",
            "0.00",
            disponivel_b=False,
        )

        with self.assertRaisesMessage(ValidationError, "deve atender todos os itens"):
            gerar_pedido_da_resposta(resposta, usuario=self.usuario)

        cotacao.refresh_from_db()
        self.assertEqual(cotacao.status, StatusCotacaoCompra.ABERTA)
        self.assertEqual(PedidoCompra.objects.count(), 0)

    def test_cotacao_aberta_nao_pode_ser_editada(self):
        cotacao = self._cotacao()

        response = self.client.get(f"/compras/cotacoes/{cotacao.pk}/editar/", follow=True)

        self.assertContains(response, "Somente cotacoes em rascunho podem ser editadas")
        self.assertContains(response, "Registrar proposta")

    def test_fornecedor_nao_pode_ter_proposta_duplicada(self):
        cotacao = self._cotacao()
        self._resposta(cotacao, self.fornecedor_a, "5.00", "7.00")
        itens = list(cotacao.itens.order_by("id"))

        response = self.client.post(
            f"/compras/cotacoes/{cotacao.pk}/proposta/",
            {
                "fornecedor": self.fornecedor_a.pk,
                "prazo_entrega_dias": "2",
                "observacoes": "",
                "precos-TOTAL_FORMS": "2",
                "precos-INITIAL_FORMS": "0",
                "precos-MIN_NUM_FORMS": "0",
                "precos-MAX_NUM_FORMS": "1000",
                "precos-0-item": itens[0].pk,
                "precos-0-disponivel": "on",
                "precos-0-custo_unitario": "4.00",
                "precos-1-item": itens[1].pk,
                "precos-1-disponivel": "on",
                "precos-1-custo_unitario": "6.00",
            },
        )

        self.assertContains(response, "Este fornecedor ja possui proposta")
        self.assertEqual(cotacao.respostas.filter(fornecedor=self.fornecedor_a).count(), 1)


class ImportacaoXMLEntradaTests(TestCase):
    CHAVE = "35260712345678000199550010000001231000001234"

    def setUp(self):
        self.usuario = get_user_model().objects.create_superuser(
            "importador_xml",
            "xml@example.com",
            "123",
        )
        self.empresa = Empresa.objects.create(
            razao_social="Mercado XML",
            nome_fantasia="Mercado XML",
            cnpj="98.765.432/0001-10",
        )
        self.filial = Filial.objects.create(
            empresa=self.empresa,
            nome="Matriz XML",
            cnpj="98.765.432/0001-10",
        )
        self.fornecedor = Fornecedor.objects.create(
            razao_social="Fornecedor XML Ltda",
            nome_fantasia="Fornecedor XML",
            cnpj="12.345.678/0001-99",
        )
        self.categoria = Categoria.all_objects.create(nome="Categoria XML")
        self.produto = Produto.objects.create(
            codigo_barras="7891234567890",
            codigo_interno="FORN-001",
            nome="Produto XML",
            categoria=self.categoria,
            preco_custo=Decimal("4.00"),
            preco_venda=Decimal("8.00"),
        )
        self.client.force_login(self.usuario)

    def _xml(self, *, chave=None, cstat="100", ean=None, codigo="FORN-001", destinatario=None):
        chave = chave or self.CHAVE
        ean = self.produto.codigo_barras if ean is None else ean
        destinatario = destinatario or "98765432000110"
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">
  <NFe>
    <infNFe Id="NFe{chave}" versao="4.00">
      <ide><nNF>123</nNF><dhEmi>2026-07-25T10:30:00-03:00</dhEmi></ide>
      <emit><CNPJ>12345678000199</CNPJ><xNome>Fornecedor XML Ltda</xNome></emit>
      <dest><CNPJ>{destinatario}</CNPJ><xNome>Mercado XML</xNome></dest>
      <det nItem="1">
        <prod>
          <cProd>{codigo}</cProd><cEAN>{ean}</cEAN><xProd>Produto XML</xProd>
          <qCom>3.000</qCom><vUnCom>5.50</vUnCom><vProd>16.50</vProd>
          <cEANTrib>{ean}</cEANTrib>
        </prod>
      </det>
      <total><ICMSTot><vProd>16.50</vProd><vNF>18.00</vNF></ICMSTot></total>
      <cobr><dup><nDup>001</nDup><dVenc>2026-08-15</dVenc><vDup>16.50</vDup></dup></cobr>
    </infNFe>
  </NFe>
  <protNFe><infProt><chNFe>{chave}</chNFe><cStat>{cstat}</cStat></infProt></protNFe>
</nfeProc>""".encode()

    def test_importacao_cria_somente_rascunho_revisavel(self):
        entrada = importar_xml_entrada(self._xml(), usuario=self.usuario)

        entrada.refresh_from_db()
        item = entrada.itens.get()
        self.assertEqual(entrada.status, StatusEntradaCompra.RASCUNHO)
        self.assertEqual(entrada.fornecedor, self.fornecedor)
        self.assertEqual(entrada.filial, self.filial)
        self.assertEqual(entrada.numero_documento, "123")
        self.assertEqual(entrada.chave_acesso_xml, self.CHAVE)
        self.assertEqual(entrada.vencimento_financeiro.isoformat(), "2026-08-15")
        self.assertEqual(entrada.total_produtos, Decimal("16.50"))
        self.assertEqual(entrada.total_documento, Decimal("18.00"))
        self.assertEqual(item.produto, self.produto)
        self.assertEqual(item.quantidade, Decimal("3.000"))
        self.assertEqual(item.custo_unitario, Decimal("5.50"))
        self.assertEqual(Estoque.objects.count(), 0)
        self.assertEqual(ContaFinanceira.objects.count(), 0)
        self.assertTrue(LogAuditoria.objects.filter(acao="IMPORTACAO_XML_ENTRADA").exists())

    def test_tela_importa_e_redireciona_para_revisao(self):
        response = self.client.post(
            "/compras/importar-xml/",
            {
                "arquivo_xml": SimpleUploadedFile("nfe.xml", self._xml(), content_type="application/xml"),
                "gerar_conta_financeira": "on",
            },
        )

        entrada = EntradaCompra.objects.get()
        self.assertRedirects(response, f"/compras/{entrada.pk}/editar/")
        revisao = self.client.get(response["Location"])
        self.assertContains(revisao, "Rascunho importado da NF-e")
        self.assertContains(revisao, self.CHAVE)

    def test_bloqueia_importacao_duplicada_pela_chave(self):
        importar_xml_entrada(self._xml(), usuario=self.usuario)

        with self.assertRaisesMessage(ValidationError, "ja foi importada"):
            importar_xml_entrada(self._xml(), usuario=self.usuario)

        self.assertEqual(EntradaCompra.objects.count(), 1)

    def test_item_sem_correspondencia_rejeita_toda_importacao(self):
        with self.assertRaisesMessage(ValidationError, "Nenhuma entrada foi criada"):
            importar_xml_entrada(
                self._xml(ean="SEM GTIN", codigo="INEXISTENTE"),
                usuario=self.usuario,
            )

        self.assertEqual(EntradaCompra.objects.count(), 0)
        self.assertEqual(ItemEntradaCompra.objects.count(), 0)

    def test_rejeita_nfe_nao_autorizada_e_xml_com_dtd(self):
        with self.assertRaisesMessage(ValidationError, "nao esta autorizada"):
            ler_xml_nfe(self._xml(cstat="110"))

        chave_divergente = self._xml().replace(
            f"<chNFe>{self.CHAVE}</chNFe>".encode(),
            f"<chNFe>{'0' * 44}</chNFe>".encode(),
        )
        with self.assertRaisesMessage(ValidationError, "difere da chave do protocolo"):
            ler_xml_nfe(chave_divergente)

        xml_com_dtd = b'<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><foo>&xxe;</foo>'
        with self.assertRaisesMessage(ValidationError, "DTD ou entidades externas"):
            ler_xml_nfe(xml_com_dtd)

    def test_finalizacao_posterior_reutiliza_fluxo_operacional_existente(self):
        entrada = importar_xml_entrada(self._xml(), usuario=self.usuario)

        finalizar_entrada_compra(entrada)

        entrada.refresh_from_db()
        self.assertEqual(entrada.status, StatusEntradaCompra.FINALIZADA)
        self.assertEqual(
            Estoque.objects.get(produto=self.produto, filial=self.filial).quantidade_atual,
            Decimal("3.000"),
        )
        conta = ContaFinanceira.objects.get(entrada_compra=entrada)
        self.assertEqual(conta.valor, Decimal("18.00"))

    def test_xml_sem_rastro_rejeita_produto_com_lote_obrigatorio_sem_criar_rascunho(self):
        self.produto.exige_lote = True
        self.produto.save(update_fields=["exige_lote", "updated_at"])

        with self.assertRaisesMessage(ValidationError, "nao informou rastro"):
            importar_xml_entrada(self._xml(), usuario=self.usuario)

        self.assertEqual(EntradaCompra.objects.count(), 0)

    def test_xml_com_rastro_importa_lote_e_finalizacao_cria_camada_fefo(self):
        self.produto.exige_lote = True
        self.produto.save(update_fields=["exige_lote", "updated_at"])
        marcador = f"<cEANTrib>{self.produto.codigo_barras}</cEANTrib>".encode()
        rastro = marcador + (
            b"<rastro><nLote>XML-LOTE-01</nLote><qLote>3.000</qLote>"
            b"<dFab>2026-07-01</dFab><dVal>2026-12-31</dVal></rastro>"
        )
        entrada = importar_xml_entrada(self._xml().replace(marcador, rastro), usuario=self.usuario)
        item = entrada.itens.get()

        self.assertEqual(item.codigo_lote, "XML-LOTE-01")
        self.assertEqual(item.fabricacao.isoformat(), "2026-07-01")
        self.assertEqual(item.validade.isoformat(), "2026-12-31")
        self.assertEqual(LoteEstoque.objects.count(), 0)

        finalizar_entrada_compra(entrada)

        lote = LoteEstoque.objects.get()
        self.assertEqual(lote.codigo, "XML-LOTE-01")
        self.assertEqual(lote.quantidade_atual, Decimal("3.000"))
        self.assertEqual(lote.custo_unitario, Decimal("5.50"))
        self.assertEqual(lote.origem_referencia, f"entrada_compra:{entrada.id}")


class ComprasIsolamentoEmpresaTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.empresa_a = Empresa.objects.create(
            razao_social="Mercado Isolado A", nome_fantasia="Mercado Isolado A", cnpj="41.111.111/0001-11"
        )
        self.empresa_b = Empresa.objects.create(
            razao_social="Mercado Isolado B", nome_fantasia="Mercado Isolado B", cnpj="42.222.222/0001-22"
        )
        self.filial_a = Filial.objects.create(empresa=self.empresa_a, nome="Matriz Isolada A")
        self.filial_b = Filial.objects.create(empresa=self.empresa_b, nome="Matriz Isolada B")
        self.usuario_a = User.objects.create_user("compras_isolado_a", password="123")
        self.super_admin = User.objects.create_superuser("compras_global", "global@example.com", "123")
        PerfilUsuario.objects.create(usuario=self.usuario_a, filial=self.filial_a, tipo=TipoPerfil.COMPRAS)
        self.fornecedor_a = Fornecedor.objects.create(empresa=self.empresa_a, razao_social="Fornecedor Isolado A")
        self.fornecedor_b = Fornecedor.objects.create(empresa=self.empresa_b, razao_social="Fornecedor Isolado B")
        self.cotacao_a = CotacaoCompra.objects.create(
            filial=self.filial_a, usuario=self.usuario_a, referencia="COT-EMPRESA-A"
        )
        self.cotacao_b = CotacaoCompra.objects.create(
            filial=self.filial_b, usuario=self.super_admin, referencia="COT-EMPRESA-B"
        )
        self.resposta_b = RespostaCotacaoFornecedor.objects.create(
            cotacao=self.cotacao_b, fornecedor=self.fornecedor_b, usuario=self.super_admin
        )
        self.pedido_a = PedidoCompra.objects.create(
            fornecedor=self.fornecedor_a, filial=self.filial_a, usuario=self.usuario_a, referencia="PED-EMPRESA-A"
        )
        self.pedido_b = PedidoCompra.objects.create(
            fornecedor=self.fornecedor_b, filial=self.filial_b, usuario=self.super_admin, referencia="PED-EMPRESA-B"
        )
        self.entrada_a = EntradaCompra.objects.create(
            fornecedor=self.fornecedor_a, filial=self.filial_a, usuario=self.usuario_a, numero_documento="NF-EMPRESA-A"
        )
        self.entrada_b = EntradaCompra.objects.create(
            fornecedor=self.fornecedor_b, filial=self.filial_b, usuario=self.super_admin, numero_documento="NF-EMPRESA-B"
        )
        self.client.force_login(self.usuario_a)

    def test_listagens_e_resumos_exibem_somente_empresa_do_usuario(self):
        cenarios = [
            ("/compras/cotacoes/", "COT-EMPRESA-A", "COT-EMPRESA-B"),
            ("/compras/pedidos/", "PED-EMPRESA-A", "PED-EMPRESA-B"),
            ("/compras/", "NF-EMPRESA-A", "NF-EMPRESA-B"),
        ]

        for url, proprio, estrangeiro in cenarios:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, proprio)
                self.assertNotContains(response, estrangeiro)

    def test_urls_de_cotacao_e_proposta_estrangeiras_retornam_404(self):
        requisicoes = [
            ("get", f"/compras/cotacoes/{self.cotacao_b.pk}/", {}),
            ("get", f"/compras/cotacoes/{self.cotacao_b.pk}/editar/", {}),
            ("get", f"/compras/cotacoes/{self.cotacao_b.pk}/proposta/", {}),
            ("post", f"/compras/cotacoes/{self.cotacao_b.pk}/abrir/", {}),
            (
                "post",
                f"/compras/cotacoes/{self.cotacao_b.pk}/propostas/{self.resposta_b.pk}/selecionar/",
                {},
            ),
        ]

        for metodo, url, dados in requisicoes:
            with self.subTest(url=url):
                response = getattr(self.client, metodo)(url, dados)
                self.assertEqual(response.status_code, 404)

    def test_urls_de_pedido_estrangeiro_retornam_404(self):
        requisicoes = [
            ("get", f"/compras/pedidos/{self.pedido_b.pk}/", {}),
            ("get", f"/compras/pedidos/{self.pedido_b.pk}/editar/", {}),
            ("post", f"/compras/pedidos/{self.pedido_b.pk}/enviar/", {}),
            ("post", f"/compras/pedidos/{self.pedido_b.pk}/gerar-entrada/", {}),
            ("post", f"/compras/pedidos/{self.pedido_b.pk}/cancelar/", {"motivo": "Teste"}),
        ]

        for metodo, url, dados in requisicoes:
            with self.subTest(url=url):
                response = getattr(self.client, metodo)(url, dados)
                self.assertEqual(response.status_code, 404)

    def test_urls_de_entrada_estrangeira_retornam_404(self):
        requisicoes = [
            ("get", f"/compras/{self.entrada_b.pk}/", {}),
            ("get", f"/compras/{self.entrada_b.pk}/imprimir/", {}),
            ("get", f"/compras/{self.entrada_b.pk}/editar/", {}),
            ("post", f"/compras/{self.entrada_b.pk}/finalizar/", {}),
            ("post", f"/compras/{self.entrada_b.pk}/cancelar/", {"motivo": "Teste"}),
            ("post", f"/compras/{self.entrada_b.pk}/excluir-rascunho/", {}),
        ]

        for metodo, url, dados in requisicoes:
            with self.subTest(url=url):
                response = getattr(self.client, metodo)(url, dados)
                self.assertEqual(response.status_code, 404)

    def test_exportacoes_respeitam_empresa_do_usuario(self):
        csv_response = self.client.get("/compras/exportar.csv")
        print_response = self.client.get("/compras/imprimir/")

        self.assertContains(csv_response, "NF-EMPRESA-A")
        self.assertNotContains(csv_response, "NF-EMPRESA-B")
        self.assertContains(print_response, "NF-EMPRESA-A")
        self.assertNotContains(print_response, "NF-EMPRESA-B")

    def test_super_admin_mantem_visao_global(self):
        self.client.force_login(self.super_admin)

        response = self.client.get("/compras/")

        self.assertContains(response, "NF-EMPRESA-A")
        self.assertContains(response, "NF-EMPRESA-B")