from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.compras.models import EntradaCompra, ItemEntradaCompra, StatusEntradaCompra
from apps.empresas.models import Empresa, Filial
from apps.estoque.models import MovimentacaoEstoque, TipoMovimentacaoEstoque
from apps.financeiro.models import (
    ContaFinanceira, ContaMovimentoFinanceiro, LancamentoFinanceiro,
    TipoContaFinanceira, TipoContaMovimento, TipoLancamentoFinanceiro,
)
from apps.financeiro.reconciliacao_contabil import gerar_reconciliacao_operacional
from apps.fiscal.models import (
    AmbienteFiscal, DocumentoDFeRecebido, DocumentoFiscal, StatusDFeRecebido,
    StatusDocumentoFiscal, TipoDocumentoFiscal,
)
from apps.fornecedores.models import Fornecedor
from apps.pdv.models import Caixa
from apps.produtos.models import Categoria, Produto
from apps.vendas.models import (
    FormaPagamento, ItemVenda, PagamentoVenda, StatusPagamento, StatusVenda, Venda,
)


class ReconciliacaoContabilTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_superuser(
            "admin-reconciliacao", "admin-reconciliacao@example.com", "123"
        )
        self.empresa = Empresa.objects.create(
            razao_social="Mercado Reconciliacao LTDA", nome_fantasia="Mercado Reconciliacao",
            cnpj="11.222.333/0001-81",
        )
        self.filial = Filial.objects.create(
            empresa=self.empresa, nome="Matriz Reconciliacao", cnpj=self.empresa.cnpj
        )
        self.caixa_pdv = Caixa.objects.create(filial=self.filial, usuario_abertura=self.usuario)
        self.conta_movimento = ContaMovimentoFinanceiro.objects.create(
            filial=self.filial, nome="Caixa PDV", tipo=TipoContaMovimento.CAIXA
        )
        self.forma_pagamento = FormaPagamento.objects.create(
            nome="Dinheiro reconciliacao", tipo="DINHEIRO",
            conta_movimento_padrao=self.conta_movimento,
        )
        self.categoria = Categoria.objects.create(nome="Mercearia reconciliacao")
        self.produto = Produto.objects.create(
            codigo_barras="7890000099001", nome="Produto reconciliado",
            categoria=self.categoria, preco_custo=Decimal("5.00"), preco_venda=Decimal("10.00"),
        )
        self.fornecedor = Fornecedor.objects.create(
            empresa=self.empresa, razao_social="Fornecedor Reconciliacao LTDA",
            cnpj="44.555.666/0001-20",
        )

    def _venda_coerente(self):
        venda = Venda.objects.create(
            filial=self.filial, caixa=self.caixa_pdv, usuario=self.usuario,
            total_bruto=Decimal("20.00"), total_liquido=Decimal("20.00"),
            status=StatusVenda.FINALIZADA,
        )
        ItemVenda.objects.create(
            venda=venda, produto=self.produto, quantidade=Decimal("2.000"),
            preco_unitario_venda=Decimal("10.00"), total=Decimal("20.00"),
        )
        pagamento = PagamentoVenda.objects.create(
            venda=venda, forma_pagamento=self.forma_pagamento, valor=Decimal("20.00"),
            status=StatusPagamento.CONFIRMADO,
        )
        LancamentoFinanceiro.objects.create(
            conta=self.conta_movimento, tipo=TipoLancamentoFinanceiro.ENTRADA,
            origem="VENDA", descricao="Venda reconciliada", valor=Decimal("20.00"),
            pagamento_venda=pagamento, usuario=self.usuario,
        )
        DocumentoFiscal.objects.create(
            filial=self.filial, venda=venda, tipo_documento=TipoDocumentoFiscal.NFCE,
            ambiente=AmbienteFiscal.HOMOLOGACAO, numero=101,
            status=StatusDocumentoFiscal.EMITIDO, valor_total=Decimal("20.00"),
            usuario=self.usuario,
        )
        MovimentacaoEstoque.objects.create(
            produto=self.produto, filial=self.filial, tipo=TipoMovimentacaoEstoque.VENDA,
            quantidade=Decimal("2.000"), referencia=f"venda:{venda.pk}", usuario=self.usuario,
        )
        return venda

    def _entrada_coerente(self):
        chave = "52260844555666000120550010000001011000000101"
        entrada = EntradaCompra.objects.create(
            fornecedor=self.fornecedor, filial=self.filial, usuario=self.usuario,
            numero_documento="101", chave_acesso_xml=chave,
            data_emissao=timezone.localdate(), vencimento_financeiro=timezone.localdate(),
            gerar_conta_financeira=True, status=StatusEntradaCompra.FINALIZADA,
            total_produtos=Decimal("15.00"), total_documento=Decimal("15.00"),
        )
        ItemEntradaCompra.objects.create(
            entrada=entrada, produto=self.produto, quantidade=Decimal("3.000"),
            custo_unitario=Decimal("5.00"), total=Decimal("15.00"),
        )
        DocumentoDFeRecebido.objects.create(
            empresa=self.empresa, filial_destino=None, entrada_compra=entrada,
            chave_acesso=chave, data_emissao=timezone.localdate(), valor_total=Decimal("15.00"),
            status=StatusDFeRecebido.XML_DISPONIVEL,
        )
        ContaFinanceira.objects.create(
            tipo=TipoContaFinanceira.PAGAR, descricao="Compra reconciliada",
            filial=self.filial, fornecedor=self.fornecedor, entrada_compra=entrada,
            valor=Decimal("15.00"), vencimento=timezone.localdate(), usuario=self.usuario,
        )
        MovimentacaoEstoque.objects.create(
            produto=self.produto, filial=self.filial, tipo=TipoMovimentacaoEstoque.ENTRADA,
            quantidade=Decimal("3.000"), referencia=f"entrada_compra:{entrada.pk}",
            custo_unitario=Decimal("5.00"), custo_total=Decimal("15.00"), usuario=self.usuario,
        )
        return entrada

    def test_confirma_venda_e_entrada_coerentes(self):
        self._venda_coerente()
        self._entrada_coerente()
        resultado = gerar_reconciliacao_operacional(
            filiais=[self.filial], data_inicio=timezone.localdate(), data_fim=timezone.localdate()
        )
        self.assertEqual(resultado["contrato"], "accounting_operational_reconciliation_v1")
        self.assertEqual(resultado["resumo"]["vendas_ok"], 1)
        self.assertEqual(resultado["resumo"]["entradas_ok"], 1)
        self.assertEqual(resultado["vendas"][0]["divergencias"], "")
        self.assertEqual(resultado["entradas"][0]["divergencias"], "")

    def test_explica_divergencias_sem_corrigir_dados(self):
        venda = Venda.objects.create(
            filial=self.filial, caixa=self.caixa_pdv, usuario=self.usuario,
            total_bruto=Decimal("20.00"), total_liquido=Decimal("20.00"),
            status=StatusVenda.FINALIZADA,
        )
        ItemVenda.objects.create(
            venda=venda, produto=self.produto, quantidade=Decimal("2.000"),
            preco_unitario_venda=Decimal("10.00"), total=Decimal("20.00"),
        )
        PagamentoVenda.objects.create(
            venda=venda, forma_pagamento=self.forma_pagamento, valor=Decimal("10.00"),
            status=StatusPagamento.CONFIRMADO,
        )
        entrada = EntradaCompra.objects.create(
            fornecedor=self.fornecedor, filial=self.filial, usuario=self.usuario,
            chave_acesso_xml="52260844555666000120550010000001021000000102",
            data_emissao=timezone.localdate(), gerar_conta_financeira=True,
            status=StatusEntradaCompra.FINALIZADA,
            total_produtos=Decimal("15.00"), total_documento=Decimal("15.00"),
        )
        ItemEntradaCompra.objects.create(
            entrada=entrada, produto=self.produto, quantidade=Decimal("3.000"),
            custo_unitario=Decimal("5.00"), total=Decimal("12.00"),
        )
        resultado = gerar_reconciliacao_operacional(
            filiais=[self.filial], data_inicio=timezone.localdate(), data_fim=timezone.localdate()
        )
        divergencias_venda = resultado["vendas"][0]["divergencias"]
        divergencias_entrada = resultado["entradas"][0]["divergencias"]
        for codigo in (
            "PAGAMENTO_DIVERGENTE", "LIVRO_FINANCEIRO_DIVERGENTE",
            "DOCUMENTO_FISCAL_AUSENTE", "ESTOQUE_DIVERGENTE",
        ):
            self.assertIn(codigo, divergencias_venda)
        for codigo in (
            "TOTAL_ITENS_DIVERGENTE", "DFE_RECEBIDO_NAO_VINCULADO",
            "CONTA_PAGAR_DIVERGENTE", "ESTOQUE_DIVERGENTE",
        ):
            self.assertIn(codigo, divergencias_entrada)
        self.assertEqual(Venda.objects.get(pk=venda.pk).total_liquido, Decimal("20.00"))
        self.assertFalse(DocumentoFiscal.objects.filter(venda=venda).exists())

    def test_respeita_isolamento_por_filial(self):
        self._venda_coerente()
        outra_filial = Filial.objects.create(
            empresa=self.empresa, nome="Filial fora da selecao", cnpj="11.222.333/0002-62"
        )
        outro_caixa = Caixa.objects.create(filial=outra_filial, usuario_abertura=self.usuario)
        Venda.objects.create(
            filial=outra_filial, caixa=outro_caixa, usuario=self.usuario,
            total_bruto=Decimal("99.00"), total_liquido=Decimal("99.00"),
            status=StatusVenda.FINALIZADA,
        )
        resultado = gerar_reconciliacao_operacional(
            filiais=[self.filial], data_inicio=timezone.localdate(), data_fim=timezone.localdate()
        )
        self.assertEqual(resultado["resumo"]["vendas"], 1)
        self.assertEqual(resultado["vendas"][0]["filial"], self.filial.nome)
