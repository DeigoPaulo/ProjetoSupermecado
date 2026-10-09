from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.empresas.models import Empresa, Filial
from apps.estoque.models import Estoque, MovimentacaoEstoque, TipoMovimentacaoEstoque, movimentar_estoque
from apps.financeiro.models import LancamentoFinanceiro, RecebivelEletronico, RegraLiquidacaoEletronica
from apps.financeiro.services_dre import calcular_dre_gerencial
from apps.financeiro.services_recebiveis import sincronizar_recebiveis
from apps.fiscal.models import DocumentoFiscal, StatusDocumentoFiscal, TipoDocumentoFiscal
from apps.financeiro.views import _conciliacao_periodo
from apps.pdv.models import Caixa
from apps.pdv.views import _resumo_caixa
from apps.produtos.models import Categoria, Produto
from apps.vendas.models import FormaPagamento, FormaPagamentoFilial, StatusPagamento, Venda

from .models import (
    DevolucaoPedido, ItemPedidoOnline, OrigemRecebimentoPedido, PagamentoPedido, PedidoOnline,
    StatusAcertoEntrega, StatusPagamentoPedido, StatusPedido, TipoEntrega,
)
from .services import (
    acertar_dinheiro_entrega, alterar_status_pedido, cancelar_pedido,
    registrar_parcelas_pedido, registrar_retorno_recusado, reservar_pedido,
)


class PagamentoPedidoFinanceiroTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_superuser("pedido_fin", "pedido@example.com", "senha")
        empresa = Empresa.objects.create(
            razao_social="Pedido Financeiro", nome_fantasia="Pedido Financeiro", cnpj="12345678000195"
        )
        self.filial = Filial.objects.create(empresa=empresa, nome="Matriz")
        categoria = Categoria.objects.create(nome="Itens de entrega")
        self.produto = Produto.objects.create(
            codigo_barras="789100000987", nome="Produto entregue", categoria=categoria,
            preco_custo=Decimal("10.00"), preco_venda=Decimal("15.00"),
        )
        Estoque.objects.create(
            produto=self.produto, filial=self.filial, quantidade_atual=Decimal("10.000"),
            custo_medio=Decimal("10.00"),
        )
        self.pedido = PedidoOnline.objects.create(
            filial=self.filial, nome_cliente="Cliente", usuario=self.usuario,
            tipo_entrega=TipoEntrega.ENTREGA, endereco_entrega="Rua Teste, 1",
        )
        ItemPedidoOnline.objects.create(
            pedido=self.pedido, produto=self.produto, quantidade=Decimal("2.000"),
            preco_unitario=Decimal("15.00"),
        )
        self.pedido.recalcular()
        reservar_pedido(pedido=self.pedido, usuario=self.usuario)
        for item in self.pedido.itens.all():
            item.quantidade_separada = item.quantidade
            item.save(update_fields=["quantidade_separada"])
        alterar_status_pedido(pedido=self.pedido, destino=StatusPedido.PRONTO, usuario=self.usuario)
        self.caixa = Caixa.objects.create(filial=self.filial, usuario_abertura=self.usuario)
        self.dinheiro = FormaPagamento.objects.create(nome="Dinheiro entrega", tipo="DINHEIRO", permite_troco=True)

    def _parcela(self, forma, valor, chave, origem, caixa=None, **extra):
        pedido, parcelas = registrar_parcelas_pedido(
            pedido=self.pedido,
            parcelas=[{"forma_pagamento": forma, "valor": Decimal(valor), "idempotency_key": chave, **extra}],
            origem_recebimento=origem, caixa=caixa, usuario=self.usuario,
        )
        return pedido, parcelas[0]

    def _habilitar_forma(self, forma):
        FormaPagamentoFilial.objects.update_or_create(
            filial=self.filial, forma_pagamento=forma, defaults={"ativo": True},
        )
        return forma

    def _simular_saida_historica(self):
        for item in self.pedido.itens.select_related("produto"):
            movimentar_estoque(
                produto=item.produto, filial=self.filial,
                tipo=TipoMovimentacaoEstoque.LIBERACAO_RESERVA,
                quantidade=item.quantidade, usuario=self.usuario,
            )
            movimentar_estoque(
                produto=item.produto, filial=self.filial,
                tipo=TipoMovimentacaoEstoque.SAIDA,
                quantidade=item.quantidade, usuario=self.usuario,
                custo_unitario=item.custo_unitario_no_momento,
            )
        self.pedido.status = StatusPedido.SAIU_ENTREGA
        self.pedido.estoque_reservado = False
        self.pedido.save(update_fields=["status", "estoque_reservado"])

    def _dre(self):
        hoje = timezone.localdate()
        return calcular_dre_gerencial(data_inicio=hoje, data_fim=hoje, filial_ids=[self.filial.pk])

    def test_retorno_recusado_estorna_estoque_financeiro_e_dre_uma_vez(self):
        referencia = f"pedido_online:{self.pedido.pk}"
        for item in self.pedido.itens.select_related("produto"):
            movimentar_estoque(produto=item.produto, filial=self.filial, tipo=TipoMovimentacaoEstoque.LIBERACAO_RESERVA, quantidade=item.quantidade, usuario=self.usuario, referencia=referencia)
            movimentar_estoque(produto=item.produto, filial=self.filial, tipo=TipoMovimentacaoEstoque.SAIDA, quantidade=item.quantidade, usuario=self.usuario, referencia=referencia, custo_unitario=item.custo_unitario_no_momento)
        self.pedido.estoque_reservado = False
        self.pedido.status = StatusPedido.SAIU_ENTREGA
        self.pedido.save(update_fields=["estoque_reservado", "status"])
        _, parcela = self._parcela(self.dinheiro, "30.00", "retorno-cash", OrigemRecebimentoPedido.ENTREGA)
        acertar_dinheiro_entrega(pagamento=parcela, caixa=self.caixa, usuario=self.usuario)
        alterar_status_pedido(pedido=self.pedido, destino=StatusPedido.CONCLUIDO, usuario=self.usuario)
        estoque = Estoque.objects.get(produto=self.produto, filial=self.filial)
        self.assertEqual(estoque.quantidade_atual, Decimal("8.000"))

        devolucao = registrar_retorno_recusado(
            pedido=self.pedido, usuario=self.usuario, motivo="Cliente recusou",
            produto_apto_venda=True, valor_devolvido_confirmado=True,
        )

        estoque.refresh_from_db()
        self.pedido.refresh_from_db()
        parcela.refresh_from_db()
        self.assertEqual(estoque.quantidade_atual, Decimal("10.000"))
        self.assertEqual(estoque.quantidade_reservada, Decimal("0.000"))
        self.assertEqual(self.pedido.status, StatusPedido.CONCLUIDO)
        self.assertEqual(self.pedido.status_pagamento, StatusPagamentoPedido.ESTORNADO)
        self.assertEqual(parcela.status, StatusPagamento.ESTORNADO)
        self.assertEqual(DevolucaoPedido.objects.filter(pedido=self.pedido).count(), 1)
        self.assertEqual(MovimentacaoEstoque.objects.filter(referencia=f"devolucao_pedido:{self.pedido.pk}", tipo=TipoMovimentacaoEstoque.DEVOLUCAO).count(), 1)
        self.assertEqual(LancamentoFinanceiro.objects.filter(pagamento_pedido=parcela, estorno_de__isnull=False).count(), 1)
        self.assertEqual(self._dre()["totais"]["devolucoes"], Decimal("30.00"))
        with self.assertRaisesMessage(ValidationError, "já foi registrado"):
            registrar_retorno_recusado(pedido=self.pedido, usuario=self.usuario, motivo="Repetido", produto_apto_venda=True, valor_devolvido_confirmado=True)
        self.assertEqual(DevolucaoPedido.objects.get(pedido=self.pedido).pk, devolucao.pk)

    def test_retorno_exige_confirmacoes_sem_movimentar(self):
        self.pedido.status = StatusPedido.CONCLUIDO
        self.pedido.save(update_fields=["status"])
        with self.assertRaisesMessage(ValidationError, "Confirme o retorno"):
            registrar_retorno_recusado(pedido=self.pedido, usuario=self.usuario, motivo="Recusou", produto_apto_venda=False, valor_devolvido_confirmado=True)
        self.assertFalse(DevolucaoPedido.objects.exists())

    def test_retorno_bloqueia_documento_fiscal_sem_alterar_estoque(self):
        self.pedido.status = StatusPedido.CONCLUIDO
        self.pedido.save(update_fields=["status"])
        DocumentoFiscal.objects.create(
            filial=self.filial, pedido_online=self.pedido, usuario=self.usuario,
            tipo_documento=TipoDocumentoFiscal.NFE, status=StatusDocumentoFiscal.EMITIDO,
        )
        with self.assertRaisesMessage(ValidationError, "tratamento fiscal"):
            registrar_retorno_recusado(pedido=self.pedido, usuario=self.usuario, motivo="Recusa", produto_apto_venda=True, valor_devolvido_confirmado=True)
        self.assertFalse(DevolucaoPedido.objects.exists())

    def test_retorno_fica_na_data_propria_sem_apagar_receita_original(self):
        referencia = f"pedido_online:{self.pedido.pk}"
        for item in self.pedido.itens.select_related("produto"):
            movimentar_estoque(produto=item.produto, filial=self.filial, tipo=TipoMovimentacaoEstoque.LIBERACAO_RESERVA, quantidade=item.quantidade, usuario=self.usuario, referencia=referencia)
            movimentar_estoque(produto=item.produto, filial=self.filial, tipo=TipoMovimentacaoEstoque.SAIDA, quantidade=item.quantidade, usuario=self.usuario, referencia=referencia, custo_unitario=item.custo_unitario_no_momento)
        self.pedido.status = StatusPedido.SAIU_ENTREGA
        self.pedido.estoque_reservado = False
        self.pedido.save(update_fields=["status", "estoque_reservado"])
        _, parcela = self._parcela(self.dinheiro, "30.00", "retorno-temporal", OrigemRecebimentoPedido.ENTREGA)
        acertar_dinheiro_entrega(pagamento=parcela, caixa=self.caixa, usuario=self.usuario)
        self.pedido.status = StatusPedido.CONCLUIDO
        self.pedido.concluido_em = timezone.now() - timedelta(days=1)
        self.pedido.save(update_fields=["status", "concluido_em"])
        registrar_retorno_recusado(pedido=self.pedido, usuario=self.usuario, motivo="Recusa", produto_apto_venda=True, valor_devolvido_confirmado=True)

        ontem = timezone.localdate() - timedelta(days=1)
        original = calcular_dre_gerencial(data_inicio=ontem, data_fim=ontem, filial_ids=[self.filial.pk])
        retorno = self._dre()
        self.assertEqual(original["totais"]["receita_bruta"], Decimal("30.00"))
        self.assertEqual(original["totais"]["devolucoes"], Decimal("0.00"))
        self.assertEqual(retorno["totais"]["devolucoes"], Decimal("30.00"))

    def test_parcelas_no_caixa_sao_idempotentes_e_nao_criam_venda(self):
        self._parcela(self.dinheiro, "10.00", "caixa-1", OrigemRecebimentoPedido.CAIXA_PDV, self.caixa)
        self._parcela(self.dinheiro, "20.00", "caixa-2", OrigemRecebimentoPedido.CAIXA_PDV, self.caixa)
        pago_em = PedidoOnline.objects.get(pk=self.pedido.pk).pago_em
        self._parcela(self.dinheiro, "20.00", "caixa-2", OrigemRecebimentoPedido.CAIXA_PDV, self.caixa)
        self.assertEqual(PagamentoPedido.objects.count(), 2)
        self.assertEqual(PedidoOnline.objects.get(pk=self.pedido.pk).pago_em, pago_em)
        self.assertEqual(Venda.objects.count(), 0)
        resumo = _resumo_caixa(self.caixa)
        self.assertEqual(resumo["total_pedidos_recebidos_no_caixa"], Decimal("30.00"))
        self.assertEqual(resumo["pagamentos_por_forma"][0]["total"], Decimal("30.00"))
        self.assertEqual(LancamentoFinanceiro.objects.filter(pagamento_pedido__pedido=self.pedido).count(), 2)
        self.assertEqual(self._dre()["totais"]["receita_bruta"], Decimal("0.00"))
        hoje = timezone.localdate()
        conciliacao = _conciliacao_periodo(hoje, hoje, filial_id=self.filial.pk)[0]
        self.assertEqual(conciliacao["entradas_pdv"], Decimal("0.00"))
        self.assertEqual(conciliacao["recebimentos_pedidos"], Decimal("30.00"))

    def test_pagamento_parcial_misto_e_troco_preservam_resumo(self):
        cartao = self._habilitar_forma(FormaPagamento.objects.create(nome="Cartão pedido", tipo="CREDITO"))
        pedido, primeira = self._parcela(
            cartao, "10.00", "misto-cartao", OrigemRecebimentoPedido.CAIXA_PDV, self.caixa,
            status=StatusPagamento.CONFIRMADO, transacao_externa_id="transacao-mista",
            nsu="nsu-misto", codigo_autorizacao="auth-misto", tipo_integracao="2",
        )
        self.assertEqual(pedido.status_pagamento, "PENDENTE")
        self.assertEqual(pedido.valor_pago, Decimal("10.00"))
        self.assertEqual(primeira.nsu, "nsu-misto")
        self.assertEqual(primeira.codigo_autorizacao, "auth-misto")
        pedido, segunda = self._parcela(
            self.dinheiro, "25.00", "misto-dinheiro", OrigemRecebimentoPedido.CAIXA_PDV,
            self.caixa,
        )
        self.assertEqual(segunda.valor, Decimal("20.00"))
        self.assertEqual(segunda.valor_informado, Decimal("25.00"))
        self.assertEqual(pedido.valor_pago, Decimal("30.00"))
        self.assertEqual(pedido.status_pagamento, "PAGO")
        self.assertEqual(pedido.forma_pagamento, "OUTRO")
        self.assertEqual(_resumo_caixa(self.caixa)["total_pedidos_recebidos_no_caixa"], Decimal("30.00"))

    def test_cartao_sem_confirmacao_nao_gera_parcela(self):
        self._simular_saida_historica()
        cartao = self._habilitar_forma(FormaPagamento.objects.create(nome="Cartão sem NSU", tipo="CREDITO"))
        with self.assertRaisesMessage(ValidationError, "NSU"):
            self._parcela(
                cartao, "30.00", "cartao-incompleto", OrigemRecebimentoPedido.ENTREGA,
                status=StatusPagamento.CONFIRMADO, transacao_externa_id="transacao-sem-nsu",
                codigo_autorizacao="auth-sem-nsu", tipo_integracao="2",
            )
        self.assertFalse(PagamentoPedido.objects.exists())

    def test_tef_integrado_sem_confirmacao_do_servidor_e_bloqueado(self):
        cartao = self._habilitar_forma(FormaPagamento.objects.create(nome="TEF sem verificador", tipo="CREDITO"))
        with self.assertRaisesMessage(ValidationError, "confirmação confiável"):
            self._parcela(
                cartao, "30.00", "tef-sem-verificador", OrigemRecebimentoPedido.CAIXA_PDV,
                self.caixa, status=StatusPagamento.CONFIRMADO,
                transacao_externa_id="transacao-tef", nsu="nsu-tef",
                codigo_autorizacao="auth-tef", tipo_integracao="1",
            )
        self.assertFalse(PagamentoPedido.objects.exists())

    def test_conclusao_bloqueada_ate_pagamento_completo(self):
        self._simular_saida_historica()
        self._parcela(self.dinheiro, "10.00", "conclusao-parcial", OrigemRecebimentoPedido.ENTREGA)
        with self.assertRaisesMessage(ValidationError, "pagamento"):
            alterar_status_pedido(pedido=self.pedido, destino=StatusPedido.CONCLUIDO, usuario=self.usuario)
        self._parcela(self.dinheiro, "20.00", "conclusao-final", OrigemRecebimentoPedido.ENTREGA)
        alterar_status_pedido(pedido=self.pedido, destino=StatusPedido.CONCLUIDO, usuario=self.usuario)
        self.assertIsNotNone(PedidoOnline.objects.get(pk=self.pedido.pk).concluido_em)

    def test_dinheiro_na_entrega_so_entra_no_caixa_apos_acerto(self):
        self._simular_saida_historica()
        _, parcela = self._parcela(self.dinheiro, "30.00", "entrega-cash", OrigemRecebimentoPedido.ENTREGA)
        self.assertEqual(parcela.status_acerto, StatusAcertoEntrega.PENDENTE)
        self.assertEqual(_resumo_caixa(self.caixa)["total_acertos_entrega"], Decimal("0.00"))
        self.assertFalse(LancamentoFinanceiro.objects.filter(pagamento_pedido=parcela).exists())
        acertar_dinheiro_entrega(pagamento=parcela, caixa=self.caixa, usuario=self.usuario)
        acertar_dinheiro_entrega(pagamento=parcela, caixa=self.caixa, usuario=self.usuario)
        self.assertEqual(_resumo_caixa(self.caixa)["total_acertos_entrega"], Decimal("30.00"))
        self.assertEqual(LancamentoFinanceiro.objects.filter(pagamento_pedido=parcela).count(), 1)

    def test_acerto_em_outro_caixa_e_bloqueado(self):
        self._simular_saida_historica()
        _, parcela = self._parcela(self.dinheiro, "30.00", "acerto-unico", OrigemRecebimentoPedido.ENTREGA)
        acertar_dinheiro_entrega(pagamento=parcela, caixa=self.caixa, usuario=self.usuario)
        outro_caixa = Caixa.objects.create(filial=self.filial, usuario_abertura=self.usuario)
        with self.assertRaisesMessage(ValidationError, "outro caixa"):
            acertar_dinheiro_entrega(pagamento=parcela, caixa=outro_caixa, usuario=self.usuario)
        self.assertEqual(_resumo_caixa(outro_caixa)["total_acertos_entrega"], Decimal("0.00"))

    def test_caixa_de_outra_filial_nao_recebe_pedido_nem_acerto(self):
        outra_empresa = Empresa.objects.create(
            razao_social="Outra empresa", nome_fantasia="Outra", cnpj="98765432000190"
        )
        outra_filial = Filial.objects.create(empresa=outra_empresa, nome="Outra matriz")
        outro_caixa = Caixa.objects.create(filial=outra_filial, usuario_abertura=self.usuario)
        with self.assertRaisesMessage(ValidationError, "filial"):
            self._parcela(self.dinheiro, "30.00", "caixa-outra-filial", OrigemRecebimentoPedido.CAIXA_PDV, outro_caixa)
        self._simular_saida_historica()
        _, parcela = self._parcela(self.dinheiro, "30.00", "entrega-outra-filial", OrigemRecebimentoPedido.ENTREGA)
        with self.assertRaisesMessage(ValidationError, "filial"):
            acertar_dinheiro_entrega(pagamento=parcela, caixa=outro_caixa, usuario=self.usuario)
        self.assertEqual(_resumo_caixa(outro_caixa)["total_pedidos_recebidos_no_caixa"], Decimal("0.00"))

    def _pagamento_eletronico_na_entrega(self, tipo):
        self._simular_saida_historica()
        forma = self._habilitar_forma(FormaPagamento.objects.create(nome=f"{tipo} entrega", tipo=tipo))
        RegraLiquidacaoEletronica.objects.create(filial=self.filial, forma_pagamento=forma)
        _, parcela = self._parcela(
            forma, "30.00", f"entrega-{tipo}", OrigemRecebimentoPedido.ENTREGA,
            status=StatusPagamento.CONFIRMADO, transacao_externa_id=f"transacao-{tipo}",
            nsu=f"nsu-{tipo}", codigo_autorizacao=f"auth-{tipo}", tipo_integracao="2",
        )
        self.assertIsNone(parcela.caixa_recebimento_id)
        self.assertEqual(parcela.status_acerto, StatusAcertoEntrega.NAO_APLICA)
        self.assertEqual(_resumo_caixa(self.caixa)["total_pedidos_recebidos_no_caixa"], Decimal("0.00"))
        self.assertEqual(_resumo_caixa(self.caixa)["total_acertos_entrega"], Decimal("0.00"))
        self.assertEqual(RecebivelEletronico.objects.filter(pagamento_pedido=parcela).count(), 1)
        self.assertEqual(LancamentoFinanceiro.objects.filter(pagamento_pedido=parcela).count(), 1)
        self.assertEqual(self._dre()["totais"]["receita_bruta"], Decimal("0.00"))

    def test_pix_na_entrega_gera_recebivel_sem_caixa(self):
        self._pagamento_eletronico_na_entrega("PIX")

    def test_cartao_na_entrega_gera_recebivel_sem_caixa(self):
        self._pagamento_eletronico_na_entrega("CREDITO")

    def test_cartao_e_pix_divididos_preservam_referencias(self):
        self._simular_saida_historica()
        cartao = self._habilitar_forma(FormaPagamento.objects.create(nome="Cartão dividido", tipo="CREDITO"))
        pix = self._habilitar_forma(FormaPagamento.objects.create(nome="PIX dividido", tipo="PIX"))
        for forma in (cartao, pix):
            RegraLiquidacaoEletronica.objects.create(filial=self.filial, forma_pagamento=forma)
        for forma, valor in ((cartao, "10.00"), (pix, "20.00")):
            self._parcela(
                forma, valor, f"dividido-{forma.tipo}", OrigemRecebimentoPedido.ENTREGA,
                status=StatusPagamento.CONFIRMADO,
                transacao_externa_id=f"transacao-{forma.tipo}",
                nsu=f"nsu-{forma.tipo}", codigo_autorizacao=f"auth-{forma.tipo}",
                tipo_integracao="2",
            )
        self.assertEqual(PagamentoPedido.objects.count(), 2)
        self.assertEqual(RecebivelEletronico.objects.count(), 2)
        self.assertEqual(PedidoOnline.objects.get(pk=self.pedido.pk).valor_pago, Decimal("30.00"))
        self.assertEqual(
            set(PagamentoPedido.objects.values_list("nsu", flat=True)),
            {"nsu-CREDITO", "nsu-PIX"},
        )
        self.assertEqual(_resumo_caixa(self.caixa)["total_pedidos_recebidos_no_caixa"], Decimal("0.00"))

    def test_agenda_financeira_exibe_recebivel_de_pedido(self):
        self._simular_saida_historica()
        pix = self._habilitar_forma(FormaPagamento.objects.create(nome="PIX agenda", tipo="PIX"))
        RegraLiquidacaoEletronica.objects.create(filial=self.filial, forma_pagamento=pix)
        self._parcela(
            pix, "30.00", "pix-agenda", OrigemRecebimentoPedido.ENTREGA,
            status=StatusPagamento.CONFIRMADO, transacao_externa_id="transacao-agenda",
            nsu="nsu-agenda", codigo_autorizacao="auth-agenda", tipo_integracao="2",
        )
        self.client.force_login(self.usuario)
        periodo = {"data_fim": (timezone.localdate() + timedelta(days=2)).isoformat()}
        pagina = self.client.get("/financeiro/agenda-recebiveis/", periodo)
        self.assertEqual(pagina.status_code, 200)
        self.assertIn(f"Pedido #{self.pedido.pk}", pagina.content.decode("utf-8"))
        csv = self.client.get("/financeiro/agenda-recebiveis/exportar.csv", periodo)
        self.assertEqual(csv.status_code, 200)
        self.assertIn(f"Pedido #{self.pedido.pk}", csv.content.decode("utf-8"))

    def test_sincronizacao_posterior_cria_recebivel_sem_duplicar_lancamento(self):
        self._simular_saida_historica()
        forma = self._habilitar_forma(FormaPagamento.objects.create(nome="PIX sem regra", tipo="PIX"))
        _, parcela = self._parcela(
            forma, "30.00", "pix-regra-posterior", OrigemRecebimentoPedido.ENTREGA,
            status=StatusPagamento.CONFIRMADO, transacao_externa_id="transacao-posterior",
            nsu="nsu-posterior", codigo_autorizacao="auth-posterior", tipo_integracao="2",
        )
        self.assertFalse(RecebivelEletronico.objects.filter(pagamento_pedido=parcela).exists())
        RegraLiquidacaoEletronica.objects.create(filial=self.filial, forma_pagamento=forma)
        self.assertEqual(sincronizar_recebiveis(filiais=[self.filial])["criados"], 1)
        self.assertEqual(sincronizar_recebiveis(filiais=[self.filial])["criados"], 0)
        self.assertEqual(RecebivelEletronico.objects.filter(pagamento_pedido=parcela).count(), 1)
        self.assertEqual(LancamentoFinanceiro.objects.filter(pagamento_pedido=parcela).count(), 1)

    def test_conclusao_reconhece_receita_e_cmv_historico_uma_vez(self):
        self._parcela(self.dinheiro, "30.00", "dre-pedido", OrigemRecebimentoPedido.CAIXA_PDV, self.caixa)
        self.assertEqual(self._dre()["totais"]["receita_bruta"], Decimal("0.00"))
        self._simular_saida_historica()
        alterar_status_pedido(pedido=self.pedido, destino=StatusPedido.CONCLUIDO, usuario=self.usuario)
        concluido_em = PedidoOnline.objects.get(pk=self.pedido.pk).concluido_em
        self.produto.preco_custo = Decimal("99.00")
        self.produto.save(update_fields=["preco_custo"])
        dre = self._dre()
        self.assertEqual(dre["totais"]["receita_bruta"], Decimal("30.00"))
        self.assertEqual(dre["cmv"]["cmv_bruto_vendas"], Decimal("20.00"))
        self.assertEqual(PedidoOnline.objects.get(pk=self.pedido.pk).concluido_em, concluido_em)

    def test_cancelamento_pago_nao_finge_estorno(self):
        self._parcela(self.dinheiro, "30.00", "cancel-pago", OrigemRecebimentoPedido.CAIXA_PDV, self.caixa)
        with self.assertRaisesMessage(ValidationError, "estorno financeiro"):
            cancelar_pedido(pedido=self.pedido, usuario=self.usuario, motivo="Cliente desistiu")
        self.assertEqual(PedidoOnline.objects.get(pk=self.pedido.pk).status, StatusPedido.PRONTO)

    def test_cancelamento_nao_pago_nao_entra_no_dre(self):
        cancelar_pedido(pedido=self.pedido, usuario=self.usuario, motivo="Cliente desistiu")
        self.assertEqual(self._dre()["totais"]["receita_bruta"], Decimal("0.00"))
