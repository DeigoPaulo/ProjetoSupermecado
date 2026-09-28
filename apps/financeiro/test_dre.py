from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone

from apps.clientes.models import Cliente
from apps.compras.models import EntradaCompra
from apps.empresas.models import Empresa, Filial
from apps.estoque.models import (
    Estoque,
    FechamentoEstoqueContabil,
    MovimentacaoEstoque,
    PerdaEstoque,
    TipoMovimentacaoEstoque,
    TipoPerdaEstoque,
)
from apps.fornecedores.models import Fornecedor
from apps.pdv.models import Caixa, Sangria, Suprimento
from apps.produtos.models import Categoria as CategoriaProduto, Produto
from apps.vendas.models import (
    DevolucaoVenda,
    FormaPagamento,
    ItemDevolucaoVenda,
    ItemVenda,
    PagamentoVenda,
    StatusVenda,
    Venda,
)
from apps.vendas.services import finalizar_venda

from .models import (
    CategoriaFinanceira,
    ContaFinanceira,
    ContaMovimentoFinanceiro,
    GrupoDRE,
    ImportacaoExtratoFinanceiro,
    ItemExtratoFinanceiro,
    LancamentoFinanceiro,
    MovimentoRecebivelEletronico,
    RecebivelEletronico,
    RegraLiquidacaoEletronica,
    StatusRecebivelEletronico,
    TipoContaFinanceira,
    TipoContaMovimento,
    TipoLancamentoFinanceiro,
    TipoMovimentoRecebivelEletronico,
    TransferenciaFinanceira,
)
from .services_dre import calcular_dre_gerencial
from .services import baixar_conta


class DREGerencialV2Tests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_superuser(
            "dre-admin", "dre@example.com", "123"
        )
        self.empresa = Empresa.objects.create(
            razao_social="Mercado DRE Ltda",
            nome_fantasia="Mercado DRE",
            cnpj="11.111.111/0001-11",
        )
        self.filial = Filial.objects.create(
            empresa=self.empresa, nome="Matriz", cnpj=self.empresa.cnpj
        )
        self.caixa = Caixa.objects.create(filial=self.filial, usuario_abertura=self.usuario)
        self.categoria_produto = CategoriaProduto.all_objects.create(nome="DRE Produtos")
        self.produto = Produto.objects.create(
            codigo_barras="7891860000001",
            nome="Produto DRE",
            categoria=self.categoria_produto,
            preco_custo=Decimal("999.000000"),
            preco_venda=Decimal("100.00"),
        )
        self.conta_movimento = ContaMovimentoFinanceiro.objects.create(
            filial=self.filial, nome="Banco DRE", tipo=TipoContaMovimento.BANCO
        )
        self.hoje = timezone.localdate()

    def _momento(self, dia):
        return timezone.make_aware(datetime.combine(dia, time(12, 0)))

    def _venda(
        self,
        *,
        dia=None,
        bruto=Decimal("100.00"),
        desconto=Decimal("10.00"),
        quantidade=Decimal("1.000"),
        custo=Decimal("60.000000"),
        filial=None,
        produto=None,
        criar_movimento=True,
    ):
        dia = dia or self.hoje
        filial = filial or self.filial
        produto = produto or self.produto
        venda = Venda.objects.create(
            filial=filial,
            caixa=self.caixa,
            usuario=self.usuario,
            total_bruto=bruto,
            desconto=desconto,
            total_liquido=bruto - desconto,
            status=StatusVenda.FINALIZADA,
        )
        Venda.objects.filter(pk=venda.pk).update(data=self._momento(dia))
        venda.refresh_from_db()
        item = ItemVenda.objects.create(
            venda=venda,
            produto=produto,
            quantidade=quantidade,
            preco_unitario_venda=bruto / quantidade,
            total=bruto,
            custo_unitario_no_momento=custo,
        )
        if criar_movimento:
            MovimentacaoEstoque.objects.create(
                produto=produto,
                filial=filial,
                tipo=TipoMovimentacaoEstoque.VENDA,
                quantidade=quantidade,
                referencia=f"venda:{venda.pk}",
                custo_unitario=custo,
                custo_total=None if custo is None else quantidade * custo,
                usuario=self.usuario,
            )
        return venda, item

    def _dre(self, inicio=None, fim=None, filial_ids=None):
        return calcular_dre_gerencial(
            data_inicio=inicio or self.hoje,
            data_fim=fim or self.hoje,
            filial_ids=filial_ids or [self.filial.pk],
        )

    def _lancamento(self, *, valor, grupo, tipo=TipoLancamentoFinanceiro.SAIDA, origem="BAIXA"):
        categoria = CategoriaFinanceira.objects.create(
            empresa=self.empresa,
            nome=f"{grupo}-{CategoriaFinanceira.objects.count()}",
            tipo=TipoContaFinanceira.PAGAR if tipo == TipoLancamentoFinanceiro.SAIDA else TipoContaFinanceira.RECEBER,
            grupo_dre=grupo,
        )
        conta = ContaFinanceira.objects.create(
            tipo=categoria.tipo,
            descricao=categoria.nome,
            categoria=categoria,
            filial=self.filial,
            valor=valor,
            vencimento=self.hoje,
            usuario=self.usuario,
        )
        return LancamentoFinanceiro.objects.create(
            conta=self.conta_movimento,
            tipo=tipo,
            origem=origem,
            descricao=categoria.nome,
            valor=valor,
            data=self.hoje,
            conta_financeira=conta,
            usuario=self.usuario,
        )

    def _recebivel_liquidado(
        self,
        *,
        valor_liquidado,
        tipo_movimento=TipoMovimentoRecebivelEletronico.LIQUIDACAO,
        movimentos_liquidacao=1,
    ):
        venda, _ = self._venda(desconto=Decimal("0.00"))
        indice = RecebivelEletronico.objects.count() + 1
        forma = FormaPagamento.objects.create(nome=f"Cartão liquidação {indice}", tipo="CARTAO")
        pagamento = PagamentoVenda.objects.create(
            venda=venda, forma_pagamento=forma, valor=Decimal("100.00")
        )
        regra = RegraLiquidacaoEletronica.objects.create(
            filial=self.filial, forma_pagamento=forma, taxa_percentual=Decimal("3.5000")
        )
        recebivel = RecebivelEletronico.objects.create(
            pagamento=pagamento,
            regra=regra,
            status=(
                StatusRecebivelEletronico.ANTECIPADO
                if tipo_movimento == TipoMovimentoRecebivelEletronico.ANTECIPACAO
                else StatusRecebivelEletronico.LIQUIDADO
            ),
            data_venda=self.hoje,
            data_prevista=self.hoje + timedelta(days=2),
            valor_bruto=Decimal("100.00"),
            taxa_prevista=Decimal("3.50"),
            valor_liquido_previsto=Decimal("96.50"),
            data_liquidacao=self.hoje,
            valor_liquidado=valor_liquidado,
        )
        importacao = ImportacaoExtratoFinanceiro.objects.create(
            conta=self.conta_movimento,
            arquivo_nome=f"liquidacao-{indice}.csv",
            arquivo_sha256=f"{indice:064d}",
            usuario=self.usuario,
        )
        for numero in range(1, movimentos_liquidacao + 1):
            item = ItemExtratoFinanceiro.objects.create(
                importacao=importacao,
                conta=self.conta_movimento,
                numero_linha=numero,
                data=self.hoje,
                tipo=TipoLancamentoFinanceiro.ENTRADA,
                valor=valor_liquidado,
                descricao="Liquidação histórica",
                referencia_externa=f"LIQ-{indice}-{numero}",
            )
            MovimentoRecebivelEletronico.objects.create(
                recebivel=recebivel,
                item_extrato=item,
                tipo=tipo_movimento,
                data=self.hoje,
                valor=valor_liquidado,
                referencia=f"LIQ-{indice}-{numero}",
                usuario=self.usuario,
            )
        return recebivel

    def test_venda_simples_e_fracionada_preservam_decimal(self):
        self._venda()
        dre = self._dre()

        self.assertEqual(dre["totais"]["receita_bruta"], Decimal("100.00"))
        self.assertEqual(dre["totais"]["descontos"], Decimal("10.00"))
        self.assertEqual(dre["totais"]["receita_liquida"], Decimal("90.00"))
        self.assertEqual(dre["totais"]["cmv"], Decimal("60.00"))
        self.assertEqual(dre["totais"]["lucro_bruto"], Decimal("30.00"))
        self.assertEqual(dre["reconciliacao_cmv"]["estado"], "OK")

    def test_venda_fracionada_quantiza_apenas_total_apresentado(self):
        self._venda(
            bruto=Decimal("2.32"),
            desconto=Decimal("0.00"),
            quantidade=Decimal("0.155"),
            custo=Decimal("10.123456"),
        )

        dre = self._dre()

        self.assertEqual(Decimal("0.155") * Decimal("10.123456"), Decimal("1.569135680"))
        self.assertEqual(dre["cmv"]["cmv_bruto_vendas"], Decimal("1.57"))

    def test_devolucao_em_periodo_posterior_reverte_receita_e_cmv(self):
        dia_venda = self.hoje - timedelta(days=2)
        dia_devolucao = self.hoje
        venda, item = self._venda(dia=dia_venda, desconto=Decimal("0.00"))
        devolucao = DevolucaoVenda.objects.create(
            venda=venda, usuario=self.usuario, motivo="Parcial", valor_total=Decimal("25.00")
        )
        DevolucaoVenda.objects.filter(pk=devolucao.pk).update(data=self._momento(dia_devolucao))
        ItemDevolucaoVenda.objects.create(
            devolucao=devolucao,
            item_venda=item,
            produto=self.produto,
            quantidade=Decimal("0.250"),
            valor_unitario=Decimal("100.00"),
            valor_total=Decimal("25.00"),
        )
        MovimentacaoEstoque.objects.create(
            produto=self.produto,
            filial=self.filial,
            tipo=TipoMovimentacaoEstoque.DEVOLUCAO,
            quantidade=Decimal("0.250"),
            referencia=f"devolucao_venda:{devolucao.pk}",
            custo_unitario=Decimal("60.000000"),
            custo_total=Decimal("15.000000"),
        )

        dre_venda = self._dre(dia_venda, dia_venda)
        dre_devolucao = self._dre(dia_devolucao, dia_devolucao)

        self.assertEqual(dre_venda["totais"]["receita_bruta"], Decimal("100.00"))
        self.assertEqual(dre_devolucao["totais"]["devolucoes"], Decimal("25.00"))
        self.assertEqual(dre_devolucao["cmv"]["cmv_reversao_devolucoes"], Decimal("15.00"))

    def test_cancelamento_com_desconto_zerado_e_legado_identificado(self):
        dia_venda = self.hoje - timedelta(days=2)
        venda, _item = self._venda(dia=dia_venda)
        Venda.objects.filter(pk=venda.pk).update(
            status=StatusVenda.CANCELADA,
            cancelada_em=self._momento(self.hoje),
            cancelada_por=self.usuario,
            motivo_cancelamento="Duplicada",
        )
        MovimentacaoEstoque.objects.create(
            produto=self.produto,
            filial=self.filial,
            tipo=TipoMovimentacaoEstoque.DEVOLUCAO,
            quantidade=Decimal("1.000"),
            referencia=f"cancelamento_venda:{venda.pk}",
            custo_unitario=Decimal("60.000000"),
            custo_total=Decimal("60.000000"),
        )

        dre_venda = self._dre(dia_venda, dia_venda)
        dre_cancelamento = self._dre(self.hoje, self.hoje)
        dre_total = self._dre(dia_venda, self.hoje)

        self.assertEqual(dre_venda["totais"]["receita_liquida"], Decimal("90.00"))
        self.assertEqual(dre_cancelamento["totais"]["cancelamentos"], Decimal("90.00"))
        self.assertEqual(dre_cancelamento["cmv"]["cmv_reversao_cancelamentos"], Decimal("60.00"))
        self.assertEqual(dre_total["totais"]["receita_liquida"], Decimal("0.00"))
        self.assertEqual(dre_total["totais"]["cmv"], Decimal("0.00"))

        legado, _ = self._venda(dia=self.hoje, bruto=Decimal("50.00"), desconto=Decimal("5.00"))
        Venda.objects.filter(pk=legado.pk).update(status=StatusVenda.CANCELADA)
        dre_legado = self._dre()
        self.assertEqual(dre_legado["cancelamentos_legados_sem_data"], 1)
        self.assertTrue(dre_legado["qualidade_temporal_parcial"])

    def test_classificacao_financeira_exclui_compra_transferencia_e_caixa(self):
        self._lancamento(valor=Decimal("120.00"), grupo=GrupoDRE.DESPESA_OPERACIONAL)
        self._lancamento(valor=Decimal("30.00"), grupo=GrupoDRE.NAO_CLASSIFICADO)

        fornecedor = Fornecedor.objects.create(empresa=self.empresa, razao_social="Fornecedor DRE")
        entrada = EntradaCompra.objects.create(
            fornecedor=fornecedor, filial=self.filial, usuario=self.usuario, total_produtos=Decimal("500.00")
        )
        conta_compra = ContaFinanceira.objects.create(
            tipo=TipoContaFinanceira.PAGAR,
            descricao="Compra de estoque",
            filial=self.filial,
            entrada_compra=entrada,
            valor=Decimal("500.00"),
            vencimento=self.hoje,
            usuario=self.usuario,
        )
        LancamentoFinanceiro.objects.create(
            conta=self.conta_movimento,
            tipo=TipoLancamentoFinanceiro.SAIDA,
            origem="BAIXA_COMPRA",
            descricao="Pagamento de mercadoria",
            valor=Decimal("500.00"),
            data=self.hoje,
            conta_financeira=conta_compra,
            usuario=self.usuario,
        )
        outra_conta = ContaMovimentoFinanceiro.objects.create(
            filial=self.filial, nome="Caixa DRE", tipo=TipoContaMovimento.CAIXA
        )
        transferencia = TransferenciaFinanceira.objects.create(
            conta_origem=self.conta_movimento,
            conta_destino=outra_conta,
            valor=Decimal("80.00"),
            data=self.hoje,
            usuario=self.usuario,
        )
        LancamentoFinanceiro.objects.create(
            conta=self.conta_movimento,
            tipo=TipoLancamentoFinanceiro.SAIDA,
            origem="TRANSFERENCIA",
            descricao="Transferência",
            valor=Decimal("80.00"),
            data=self.hoje,
            transferencia=transferencia,
            usuario=self.usuario,
        )
        sangria = Sangria.objects.create(
            caixa=self.caixa, usuario=self.usuario, valor=Decimal("20.00"), motivo="Guarda"
        )
        suprimento = Suprimento.objects.create(
            caixa=self.caixa, usuario=self.usuario, valor=Decimal("10.00"), motivo="Troco"
        )
        for tipo, valor, objeto in [
            (TipoLancamentoFinanceiro.SAIDA, Decimal("20.00"), sangria),
            (TipoLancamentoFinanceiro.ENTRADA, Decimal("10.00"), suprimento),
        ]:
            LancamentoFinanceiro.objects.create(
                conta=self.conta_movimento,
                tipo=tipo,
                origem="CAIXA",
                descricao="Movimento de caixa",
                valor=valor,
                data=self.hoje,
                sangria=objeto if isinstance(objeto, Sangria) else None,
                suprimento=objeto if isinstance(objeto, Suprimento) else None,
                usuario=self.usuario,
            )

        dre = self._dre()

        self.assertEqual(dre["totais"]["despesas_operacionais"], Decimal("120.00"))
        self.assertEqual(dre["saidas_nao_classificadas"]["valor"], Decimal("30.00"))

    def test_fluxo_real_pdv_reconhece_receita_sem_reclassificar_recebimento(self):
        Estoque.objects.create(
            produto=self.produto,
            filial=self.filial,
            quantidade_atual=Decimal("10.000"),
            custo_medio=Decimal("60.000000"),
        )
        dinheiro = FormaPagamento.objects.create(
            nome="Dinheiro DRE", tipo="DINHEIRO", conta_movimento_padrao=self.conta_movimento
        )

        venda = finalizar_venda(
            caixa=self.caixa,
            usuario=self.usuario,
            itens=[{"produto": self.produto, "quantidade": Decimal("1.000")}],
            pagamentos=[{"forma_pagamento": dinheiro, "valor": Decimal("100.00")}],
            preparar_fiscal=False,
        )
        dre = self._dre()

        self.assertTrue(venda.pagamentos.exists())
        self.assertTrue(
            LancamentoFinanceiro.objects.filter(
                pagamento_venda__venda=venda, origem="PDV_VENDA"
            ).exists()
        )
        self.assertTrue(
            MovimentacaoEstoque.objects.filter(referencia=f"venda:{venda.pk}").exists()
        )
        self.assertEqual(dre["totais"]["receita_bruta"], Decimal("100.00"))
        self.assertEqual(dre["totais"]["cmv"], Decimal("60.00"))
        self.assertEqual(dre["totais"]["outras_receitas"], Decimal("0.00"))
        self.assertEqual(dre["entradas_nao_classificadas"]["quantidade"], 0)

    def test_crediario_recebido_permanece_no_resultado_financeiro_mas_nao_na_dre(self):
        Estoque.objects.create(
            produto=self.produto,
            filial=self.filial,
            quantidade_atual=Decimal("10.000"),
            custo_medio=Decimal("60.000000"),
        )
        cliente = Cliente.objects.create(
            empresa=self.empresa, nome="Cliente crediário DRE", cpf_cnpj="123.456.789-00"
        )
        crediario = FormaPagamento.objects.create(nome="Crediário DRE", tipo="CREDIARIO")
        venda = finalizar_venda(
            caixa=self.caixa,
            usuario=self.usuario,
            cliente=cliente,
            itens=[{"produto": self.produto, "quantidade": Decimal("1.000")}],
            pagamentos=[{"forma_pagamento": crediario, "valor": Decimal("100.00")}],
            vencimento_financeiro=self.hoje,
            preparar_fiscal=False,
        )
        conta = ContaFinanceira.objects.get(venda=venda)
        baixar_conta(
            conta=conta,
            usuario=self.usuario,
            data_pagamento=self.hoje,
            valor_pago=Decimal("100.00"),
            forma_pagamento="PIX",
            conta_movimento=self.conta_movimento,
        )

        dre = self._dre()
        cliente_http = Client(HTTP_HOST="localhost")
        cliente_http.force_login(self.usuario)
        resultado = cliente_http.get(
            "/financeiro/resultado/",
            {"data_inicio": self.hoje.isoformat(), "data_fim": self.hoje.isoformat(), "filial": self.filial.pk},
        )

        self.assertEqual(resultado.status_code, 200)
        self.assertEqual(resultado.context["receitas"], Decimal("100.00"))
        self.assertEqual(dre["totais"]["receita_bruta"], Decimal("100.00"))
        self.assertEqual(dre["totais"]["outras_receitas"], Decimal("0.00"))
        self.assertEqual(dre["entradas_nao_classificadas"]["quantidade"], 0)

    def test_outra_receita_legitima_e_saida_nao_classificada_permanecem_visiveis(self):
        self._lancamento(
            valor=Decimal("25.00"),
            grupo=GrupoDRE.OUTRA_RECEITA,
            tipo=TipoLancamentoFinanceiro.ENTRADA,
            origem="RECEITA_EXTRAORDINARIA",
        )
        self._lancamento(valor=Decimal("12.00"), grupo=GrupoDRE.NAO_CLASSIFICADO)

        dre = self._dre()

        self.assertEqual(dre["totais"]["outras_receitas"], Decimal("25.00"))
        self.assertEqual(dre["saidas_nao_classificadas"]["valor"], Decimal("12.00"))

    def test_perda_taxa_realizada_chargeback_e_taxa_prevista(self):
        venda, _ = self._venda(desconto=Decimal("0.00"))
        PerdaEstoque.objects.create(
            produto=self.produto,
            filial=self.filial,
            usuario=self.usuario,
            tipo=TipoPerdaEstoque.AVARIA,
            quantidade=Decimal("2.000"),
            motivo="Quebra",
            custo_unitario_no_momento=Decimal("7.500000"),
            preco_venda_no_momento=Decimal("12.00"),
            valor_custo_estimado=Decimal("15.00"),
            valor_venda_estimado=Decimal("24.00"),
        )
        forma = FormaPagamento.objects.create(nome="Cartão DRE", tipo="CARTAO")
        pagamento = PagamentoVenda.objects.create(venda=venda, forma_pagamento=forma, valor=Decimal("100.00"))
        regra = RegraLiquidacaoEletronica.objects.create(
            filial=self.filial, forma_pagamento=forma, taxa_percentual=Decimal("3.5000")
        )
        recebivel = RecebivelEletronico.objects.create(
            pagamento=pagamento,
            regra=regra,
            status=StatusRecebivelEletronico.LIQUIDADO,
            data_venda=self.hoje,
            data_prevista=self.hoje,
            valor_bruto=Decimal("100.00"),
            taxa_prevista=Decimal("3.50"),
            valor_liquido_previsto=Decimal("96.50"),
            data_liquidacao=self.hoje,
            valor_liquidado=Decimal("96.50"),
        )
        importacao = ImportacaoExtratoFinanceiro.objects.create(
            conta=self.conta_movimento,
            arquivo_nome="dre.csv",
            arquivo_sha256="a" * 64,
            usuario=self.usuario,
        )
        for numero, tipo, valor, movimento_financeiro in [
            (1, TipoMovimentoRecebivelEletronico.LIQUIDACAO, Decimal("96.50"), TipoLancamentoFinanceiro.ENTRADA),
            (2, TipoMovimentoRecebivelEletronico.CHARGEBACK, Decimal("40.00"), TipoLancamentoFinanceiro.SAIDA),
        ]:
            item = ItemExtratoFinanceiro.objects.create(
                importacao=importacao,
                conta=self.conta_movimento,
                numero_linha=numero,
                data=self.hoje,
                tipo=movimento_financeiro,
                valor=valor,
                descricao=tipo,
                referencia_externa=f"DRE-{numero}",
            )
            MovimentoRecebivelEletronico.objects.create(
                recebivel=recebivel,
                item_extrato=item,
                tipo=tipo,
                data=self.hoje,
                valor=valor,
                referencia=f"DRE-{numero}",
                usuario=self.usuario,
            )

        dre = self._dre()

        self.assertEqual(dre["totais"]["perdas_estoque"], Decimal("15.00"))
        self.assertEqual(dre["recebiveis"]["custos_liquidacao_realizados"], Decimal("3.50"))
        self.assertEqual(dre["recebiveis"]["taxas_realizadas"], Decimal("3.50"))
        self.assertEqual(dre["recebiveis"]["taxas_previstas_diagnostico"], Decimal("3.50"))
        self.assertEqual(dre["recebiveis"]["divergencia_liquidacao"], Decimal("0.00"))
        self.assertEqual(dre["recebiveis"]["chargebacks"], Decimal("40.00"))
        self.assertEqual(dre["totais"]["despesas_financeiras"], Decimal("43.50"))

    def test_liquidacao_divergente_usa_realizado_e_expoe_diferenca_prevista(self):
        self._recebivel_liquidado(valor_liquidado=Decimal("95.00"))

        dre = self._dre()

        self.assertEqual(dre["recebiveis"]["custos_liquidacao_realizados"], Decimal("5.00"))
        self.assertEqual(dre["recebiveis"]["divergencia_liquidacao"], Decimal("-1.50"))
        self.assertEqual(dre["totais"]["despesas_financeiras"], Decimal("5.00"))

    def test_liquidacao_acima_do_previsto_reduz_custo_realizado(self):
        self._recebivel_liquidado(valor_liquidado=Decimal("97.00"))

        dre = self._dre()

        self.assertEqual(dre["recebiveis"]["custos_liquidacao_realizados"], Decimal("3.00"))
        self.assertEqual(dre["recebiveis"]["divergencia_liquidacao"], Decimal("0.50"))

    def test_antecipacao_nao_inventa_taxa_especifica(self):
        self._recebivel_liquidado(
            valor_liquidado=Decimal("96.00"),
            tipo_movimento=TipoMovimentoRecebivelEletronico.ANTECIPACAO,
        )

        dre = self._dre()

        self.assertEqual(dre["recebiveis"]["custos_liquidacao_realizados"], Decimal("4.00"))
        self.assertEqual(dre["recebiveis"]["antecipacoes_quantidade"], 1)
        self.assertEqual(
            dre["recebiveis"]["antecipacoes_valor_liquidado_sem_taxa_segregada"],
            Decimal("96.00"),
        )

    def test_multiplos_movimentos_nao_repetem_custo_do_recebivel(self):
        self._recebivel_liquidado(
            valor_liquidado=Decimal("96.50"), movimentos_liquidacao=2
        )

        dre = self._dre()

        self.assertEqual(dre["recebiveis"]["custos_liquidacao_realizados"], Decimal("3.50"))
        self.assertEqual(len(dre["recebiveis"]["liquidacoes"]), 1)

    def test_chargeback_posterior_permanece_evento_separado(self):
        recebivel = self._recebivel_liquidado(valor_liquidado=Decimal("96.50"))
        dia_chargeback = self.hoje + timedelta(days=1)
        importacao = recebivel.movimentos.first().item_extrato.importacao
        item = ItemExtratoFinanceiro.objects.create(
            importacao=importacao,
            conta=self.conta_movimento,
            numero_linha=99,
            data=dia_chargeback,
            tipo=TipoLancamentoFinanceiro.SAIDA,
            valor=Decimal("40.00"),
            descricao="Chargeback posterior",
            referencia_externa="CHARGEBACK-POSTERIOR",
        )
        MovimentoRecebivelEletronico.objects.create(
            recebivel=recebivel,
            item_extrato=item,
            tipo=TipoMovimentoRecebivelEletronico.CHARGEBACK,
            data=dia_chargeback,
            valor=Decimal("40.00"),
            referencia="CHARGEBACK-POSTERIOR",
            usuario=self.usuario,
        )

        dre_liquidacao = self._dre(self.hoje, self.hoje)
        dre_chargeback = self._dre(dia_chargeback, dia_chargeback)
        dre_total = self._dre(self.hoje, dia_chargeback)

        self.assertEqual(dre_liquidacao["totais"]["despesas_financeiras"], Decimal("3.50"))
        self.assertEqual(dre_liquidacao["recebiveis"]["chargebacks"], Decimal("0.00"))
        self.assertEqual(dre_chargeback["totais"]["despesas_financeiras"], Decimal("40.00"))
        self.assertEqual(dre_total["totais"]["despesas_financeiras"], Decimal("43.50"))

    def test_snapshot_ausente_divergencia_e_fechamento_complementar(self):
        self._venda(custo=None, criar_movimento=False)
        FechamentoEstoqueContabil.objects.create(
            filial=self.filial,
            data_referencia=self.hoje,
            criterio_custo="CUSTO_MEDIO_PONDERADO_MOVEL",
            valor_total_custo=Decimal("800.00"),
            conteudo_sha256="b" * 64,
            capturado_por=self.usuario,
        )
        dre_incompleta = self._dre()
        self.assertFalse(dre_incompleta["cmv"]["cmv_completo"])
        self.assertEqual(dre_incompleta["reconciliacao_cmv"]["estado"], "INCOMPLETO")
        self.assertEqual(
            dre_incompleta["reconciliacao_cmv"]["fechamentos_estoque"][0]["qualidade"], "EXATA"
        )

    def test_fechamentos_apenas_anteriores_e_ausentes_nao_sao_inventados(self):
        filial_anterior = Filial.objects.create(
            empresa=self.empresa, nome="Com fechamento anterior", cnpj="11.111.111/0002-00"
        )
        filial_sem = Filial.objects.create(
            empresa=self.empresa, nome="Sem fechamento", cnpj="11.111.111/0003-00"
        )
        FechamentoEstoqueContabil.objects.create(
            filial=filial_anterior,
            data_referencia=self.hoje - timedelta(days=1),
            criterio_custo="CUSTO_MEDIO_PONDERADO_MOVEL",
            valor_total_custo=Decimal("400.00"),
            conteudo_sha256="c" * 64,
            capturado_por=self.usuario,
        )

        dre = self._dre(filial_ids=[filial_anterior.pk, filial_sem.pk])
        evidencias = {
            item["filial_id"]: item for item in dre["reconciliacao_cmv"]["fechamentos_estoque"]
        }

        self.assertEqual(evidencias[filial_anterior.pk]["qualidade"], "REFERENCIA_TEMPORAL")
        self.assertFalse(evidencias[filial_anterior.pk]["final"]["data_exata"])
        self.assertEqual(evidencias[filial_sem.pk]["qualidade"], "SEM_FECHAMENTO")
        self.assertIsNone(evidencias[filial_sem.pk]["inicial"])
        self.assertIsNone(evidencias[filial_sem.pk]["final"])

    def test_reconciliacao_detecta_movimento_divergente_e_isola_empresa(self):
        venda, _ = self._venda()
        MovimentacaoEstoque.objects.filter(referencia=f"venda:{venda.pk}").update(
            custo_total=Decimal("59.990000")
        )
        outra_empresa = Empresa.objects.create(
            razao_social="Outra Empresa DRE", nome_fantasia="Outra DRE", cnpj="22.222.222/0001-22"
        )
        outra_filial = Filial.objects.create(
            empresa=outra_empresa, nome="Outra matriz", cnpj=outra_empresa.cnpj
        )
        outro_caixa = Caixa.objects.create(filial=outra_filial, usuario_abertura=self.usuario)
        venda_externa = Venda.objects.create(
            filial=outra_filial,
            caixa=outro_caixa,
            usuario=self.usuario,
            total_bruto=Decimal("999.00"),
            total_liquido=Decimal("999.00"),
            status=StatusVenda.FINALIZADA,
        )
        ItemVenda.objects.create(
            venda=venda_externa,
            produto=self.produto,
            quantidade=Decimal("1.000"),
            preco_unitario_venda=Decimal("999.00"),
            total=Decimal("999.00"),
            custo_unitario_no_momento=Decimal("10.000000"),
        )

        dre = self._dre()

        self.assertEqual(dre["totais"]["receita_bruta"], Decimal("100.00"))
        self.assertEqual(dre["reconciliacao_cmv"]["estado"], "DIVERGENTE")
        self.assertEqual(dre["reconciliacao_cmv"]["diferenca"], Decimal("-0.01"))

    def test_endpoints_usam_contrato_versionado_e_json_sem_float(self):
        self._venda()
        cliente = Client(HTTP_HOST="localhost")
        cliente.force_login(self.usuario)

        pagina = cliente.get(f"/financeiro/dre/?empresa={self.empresa.pk}")
        resposta_json = cliente.get(f"/financeiro/dre.json?empresa={self.empresa.pk}")
        resposta_csv = cliente.get(f"/financeiro/dre/exportar.csv?empresa={self.empresa.pk}")

        self.assertEqual(pagina.status_code, 200)
        self.assertContains(pagina, "DRE gerencial 2.0")
        self.assertEqual(resposta_json.json()["contrato"], "financial_dre_v2")
        self.assertEqual(resposta_json.json()["totais"]["receita_bruta"], "100.00")
        self.assertEqual(
            resposta_json.json()["reconciliacao_cmv"]["contrato"],
            "financial_cmv_reconciliation_v1",
        )
        self.assertContains(resposta_csv, "financial_dre_v2")


class CategoriaGrupoDRETests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(
            razao_social="Classificação DRE", nome_fantasia="Classificação", cnpj="33.333.333/0001-33"
        )

    def test_rejeita_grupos_contraditorios(self):
        receber = CategoriaFinanceira(
            empresa=self.empresa,
            nome="Receber como despesa",
            tipo=TipoContaFinanceira.RECEBER,
            grupo_dre=GrupoDRE.DESPESA_OPERACIONAL,
        )
        pagar = CategoriaFinanceira(
            empresa=self.empresa,
            nome="Pagar como receita",
            tipo=TipoContaFinanceira.PAGAR,
            grupo_dre=GrupoDRE.OUTRA_RECEITA,
        )

        with self.assertRaisesMessage(Exception, "grupo de despesa"):
            receber.full_clean()
        with self.assertRaisesMessage(Exception, "outra receita"):
            pagar.full_clean()
