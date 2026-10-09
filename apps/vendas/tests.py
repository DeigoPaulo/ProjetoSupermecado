from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.test import TestCase

from apps.empresas.models import Empresa, Filial
from apps.estoque.models import Estoque, MovimentacaoEstoque, TipoMovimentacaoEstoque
from apps.financeiro.models import ContaFinanceira, ContaMovimentoFinanceiro, LancamentoFinanceiro, StatusContaFinanceira, TipoContaFinanceira, TipoContaMovimento, TipoLancamentoFinanceiro
from apps.fiscal.certificados import criptografar
from apps.fiscal.models import AmbienteFiscal, ConfiguracaoFiscal, DocumentoFiscal, NaturezaOperacao, SerieFiscal, StatusDocumentoFiscal, TipoDocumentoFiscal
from apps.clientes.models import Cliente
from apps.pdv.models import Caixa
from apps.produtos.models import Categoria, Produto

from .models import EstornoParcialPagamento, FormaPagamento, FormaPagamentoFilial, PagamentoVenda, StatusEstornoParcial, StatusPagamento, StatusVenda, TipoDocumentoConsumidor, Venda
from .services import calcular_item, cancelar_venda, confirmar_estorno_pagamento_eletronico, confirmar_estorno_parcial_eletronico, finalizar_venda, formas_pagamento_disponiveis, registrar_devolucao_venda


class VendaServiceTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(username="operador", password="123")
        self.empresa = Empresa.objects.create(
            razao_social="Mercado Teste Ltda",
            nome_fantasia="Mercado Teste",
            cnpj="12.345.678/0001-95",
        )
        self.filial = Filial.objects.create(empresa=self.empresa, nome="Loja 1", cnpj=self.empresa.cnpj)
        self.categoria = Categoria.all_objects.create(nome="Mercearia")
        self.produto = Produto.objects.create(
            codigo_barras="7890000000011",
            nome="Arroz 5kg",
            categoria=self.categoria,
            preco_custo=Decimal("15.00"),
            preco_venda=Decimal("25.00"),
            estoque_minimo=Decimal("2.000"),
        )
        self.estoque = Estoque.objects.create(produto=self.produto, filial=self.filial, quantidade_atual=Decimal("10.000"))
        self.caixa = Caixa.objects.create(filial=self.filial, usuario_abertura=self.usuario, valor_inicial=Decimal("100.00"))
        self.dinheiro = FormaPagamento.objects.create(nome="Dinheiro", tipo="DINHEIRO", permite_troco=True)
        self.pix = FormaPagamento.objects.create(nome="Pix", tipo="PIX")
        self.crediario = FormaPagamento.objects.create(nome="Crediario", tipo="CREDIARIO")
        self.cliente = Cliente.objects.create(empresa=self.empresa, nome="Cliente Teste", cpf_cnpj="123.456.789-00")

    def habilitar_pix(self):
        formas_pagamento_disponiveis(self.filial)
        FormaPagamentoFilial.objects.filter(
            filial=self.filial, forma_pagamento=self.pix,
        ).update(ativo=True)

    def test_finalizacao_rejeita_cliente_de_outra_empresa(self):
        empresa_estrangeira = Empresa.objects.create(
            razao_social="Outro Mercado Ltda",
            nome_fantasia="Outro Mercado",
            cnpj="22.222.222/0001-22",
        )
        cliente_estrangeiro = Cliente.objects.create(empresa=empresa_estrangeira, nome="Cliente estrangeiro")

        with self.assertRaisesMessage(ValidationError, "Cliente informado pertence a outra empresa"):
            finalizar_venda(
                caixa=self.caixa,
                usuario=self.usuario,
                cliente=cliente_estrangeiro,
                itens=[{"produto": self.produto, "quantidade": Decimal("1.000")}],
                pagamentos=[{"forma_pagamento": self.dinheiro, "valor": Decimal("25.00")}],
            )

        self.assertFalse(Venda.objects.exists())
        self.estoque.refresh_from_db()
        self.assertEqual(self.estoque.quantidade_atual, Decimal("10.000"))
    def test_finalizacao_sem_registro_de_estoque_retorna_erro_operacional(self):
        filial_sem_estoque = Filial.objects.create(empresa=self.empresa, nome="Loja sem saldo", cnpj="11.111.111/0002-00")
        caixa_sem_estoque = Caixa.objects.create(
            filial=filial_sem_estoque,
            usuario_abertura=self.usuario,
            valor_inicial=Decimal("50.00"),
        )

        with self.assertRaisesMessage(ValidationError, "Estoque insuficiente"):
            finalizar_venda(
                caixa=caixa_sem_estoque,
                usuario=self.usuario,
                itens=[{"produto": self.produto, "quantidade": Decimal("1.000")}],
                pagamentos=[{"forma_pagamento": self.dinheiro, "valor": Decimal("25.00")}],
            )

        self.assertFalse(Estoque.objects.filter(produto=self.produto, filial=filial_sem_estoque).exists())
    def test_nova_forma_global_e_inicializada_na_filial_automaticamente(self):
        formas_pagamento_disponiveis(self.filial)
        nova_forma = FormaPagamento.objects.create(nome="Cartão loja", tipo="CARTAO")

        disponiveis = formas_pagamento_disponiveis(self.filial)

        self.assertNotIn(nova_forma, disponiveis)
        self.assertTrue(
            FormaPagamentoFilial.objects.filter(
                filial=self.filial,
                forma_pagamento=nova_forma,
                ativo=False,
            ).exists()
        )
    def test_finalizacao_rejeita_forma_desabilitada_na_filial(self):
        FormaPagamentoFilial.objects.create(
            filial=self.filial,
            forma_pagamento=self.dinheiro,
            ativo=False,
        )
        FormaPagamentoFilial.objects.create(filial=self.filial, forma_pagamento=self.pix, ativo=True)
        FormaPagamentoFilial.objects.create(filial=self.filial, forma_pagamento=self.crediario, ativo=True)

        with self.assertRaisesMessage(ValidationError, "Forma de pagamento não habilitada para está filial"):
            finalizar_venda(
                caixa=self.caixa,
                usuario=self.usuario,
                itens=[{"produto": self.produto, "quantidade": Decimal("1.000")}],
                pagamentos=[{"forma_pagamento": self.dinheiro, "valor": Decimal("25.00")}],
            )

        self.assertFalse(Venda.objects.exists())
        self.estoque.refresh_from_db()
        self.assertEqual(self.estoque.quantidade_atual, Decimal("10.000"))

    def test_lancamento_usa_conta_configurada_para_a_filial(self):
        conta_pix = ContaMovimentoFinanceiro.objects.create(
            filial=self.filial,
            nome="PIX específico da filial",
            tipo=TipoContaMovimento.PIX,
        )
        FormaPagamentoFilial.objects.create(
            filial=self.filial,
            forma_pagamento=self.pix,
            conta_movimento_padrao=conta_pix,
            ativo=True,
        )

        venda = finalizar_venda(
            caixa=self.caixa,
            usuario=self.usuario,
            itens=[{"produto": self.produto, "quantidade": Decimal("1.000")}],
            pagamentos=[{"forma_pagamento": self.pix, "valor": Decimal("25.00")}],
        )

        self.assertTrue(
            LancamentoFinanceiro.objects.filter(
                conta=conta_pix,
                pagamento_venda__venda=venda,
                pagamento_venda__forma_pagamento=self.pix,
            ).exists()
        )
    def test_finalizar_venda_com_pagamento_dividido_baixa_estoque(self):
        self.habilitar_pix()
        self.estoque.custo_medio = Decimal("12.500000")
        self.estoque.save(update_fields=["custo_medio", "atualizado_em"])
        pix_configurado = ContaMovimentoFinanceiro.objects.create(
            filial=self.filial,
            nome="PIX Banco Preferencial",
            tipo=TipoContaMovimento.PIX,
            saldo_inicial=Decimal("0.00"),
        )
        self.pix.conta_movimento_padrao = pix_configurado
        self.pix.save(update_fields=["conta_movimento_padrao"])

        venda = finalizar_venda(
            caixa=self.caixa,
            usuario=self.usuario,
            itens=[{"produto": self.produto, "quantidade": Decimal("2.000")}],
            pagamentos=[
                {"forma_pagamento": self.dinheiro, "valor": Decimal("20.00")},
                {"forma_pagamento": self.pix, "valor": Decimal("30.00")},
            ],
        )

        self.assertEqual(venda.status, StatusVenda.FINALIZADA)
        self.assertEqual(venda.total_bruto, Decimal("50.00"))
        self.assertIsNone(venda.cliente)
        self.assertEqual(PagamentoVenda.objects.filter(venda=venda).count(), 2)
        self.assertEqual(venda.itens.get().custo_unitario_no_momento, Decimal("12.50"))
        self.estoque.refresh_from_db()
        self.assertEqual(self.estoque.quantidade_atual, Decimal("8.000"))
        self.assertTrue(
            MovimentacaoEstoque.objects.filter(
                produto=self.produto,
                filial=self.filial,
                tipo=TipoMovimentacaoEstoque.VENDA,
                referencia=f"venda:{venda.id}",
            ).exists()
        )
        self.assertEqual(LancamentoFinanceiro.objects.filter(origem="PDV_VENDA").count(), 2)
        self.assertTrue(ContaMovimentoFinanceiro.objects.filter(filial=self.filial, nome="Caixa PDV", tipo=TipoContaMovimento.CAIXA).exists())
        self.assertFalse(ContaMovimentoFinanceiro.objects.filter(filial=self.filial, nome="PIX PDV", tipo=TipoContaMovimento.PIX).exists())
        self.assertTrue(LancamentoFinanceiro.objects.filter(conta=pix_configurado, pagamento_venda__forma_pagamento=self.pix).exists())
        self.assertEqual(
            LancamentoFinanceiro.objects.filter(tipo=TipoLancamentoFinanceiro.ENTRADA).aggregate(total=Sum("valor"))["total"],
            Decimal("50.00"),
        )

    def test_troco_preserva_valor_informado_sem_inflar_financeiro(self):
        venda = finalizar_venda(
            caixa=self.caixa,
            usuario=self.usuario,
            itens=[{"produto": self.produto, "quantidade": Decimal("1.000")}],
            pagamentos=[{
                "forma_pagamento": self.dinheiro,
                "valor": Decimal("25.00"),
                "valor_informado": Decimal("40.00"),
            }],
            preparar_fiscal=False,
        )

        pagamento = venda.pagamentos.get()
        self.assertEqual(pagamento.valor, Decimal("25.00"))
        self.assertEqual(pagamento.valor_informado, Decimal("40.00"))
        self.assertEqual(
            LancamentoFinanceiro.objects.get(pagamento_venda=pagamento).valor,
            Decimal("25.00"),
        )

    def test_checkout_dinheiro_21_recebido_25_registra_somente_21(self):
        from types import SimpleNamespace

        from django.http import QueryDict

        from apps.pdv.views import _pagamentos_from_request

        self.produto.preco_venda = Decimal("21.00")
        self.produto.save(update_fields=["preco_venda"])
        post = QueryDict(mutable=True)
        post.setlist("pagamento_forma", [str(self.dinheiro.pk)])
        post.setlist("pagamento_valor", ["25.00"])
        pagamentos, recebido = _pagamentos_from_request(
            SimpleNamespace(POST=post), Decimal("21.00"), self.filial,
        )
        self.assertEqual(recebido, Decimal("25.00"))
        self.assertEqual(pagamentos[0]["valor"], Decimal("21.00"))
        self.assertEqual(pagamentos[0]["valor_informado"], Decimal("25.00"))

        venda = finalizar_venda(
            caixa=self.caixa,
            usuario=self.usuario,
            itens=[{"produto": self.produto, "quantidade": Decimal("1.000")}],
            pagamentos=pagamentos,
            preparar_fiscal=False,
        )
        pagamento = venda.pagamentos.get()
        self.assertEqual(venda.total_liquido, Decimal("21.00"))
        self.assertEqual(pagamento.valor, Decimal("21.00"))
        self.assertEqual(pagamento.valor_informado, Decimal("25.00"))
        self.assertEqual(pagamento.valor_informado - pagamento.valor, Decimal("4.00"))
        self.assertEqual(
            LancamentoFinanceiro.objects.get(pagamento_venda=pagamento).valor,
            Decimal("21.00"),
        )

    def test_forma_sem_troco_nao_pode_exceder_valor_aplicado(self):
        self.habilitar_pix()
        with self.assertRaisesMessage(ValidationError, "Somente uma forma configurada para troco"):
            finalizar_venda(
                caixa=self.caixa,
                usuario=self.usuario,
                itens=[{"produto": self.produto, "quantidade": Decimal("1.000")}],
                pagamentos=[{
                    "forma_pagamento": self.pix,
                    "valor": Decimal("25.00"),
                    "valor_informado": Decimal("30.00"),
                }],
                preparar_fiscal=False,
            )
        self.assertFalse(Venda.objects.exists())

    def test_duas_parcelas_da_mesma_modalidade_permanecem_independentes(self):
        self.habilitar_pix()
        venda = finalizar_venda(
            caixa=self.caixa,
            usuario=self.usuario,
            itens=[{"produto": self.produto, "quantidade": Decimal("1.000")}],
            pagamentos=[
                {"forma_pagamento": self.pix, "valor": Decimal("10.00")},
                {"forma_pagamento": self.pix, "valor": Decimal("15.00")},
            ],
            preparar_fiscal=False,
        )

        pagamentos = list(venda.pagamentos.order_by("pk"))
        self.assertEqual([item.valor for item in pagamentos], [Decimal("10.00"), Decimal("15.00")])
        self.assertEqual(len({item.transacao_externa_id for item in pagamentos}), 2)

    def test_configuracao_fiscal_tpag_xpag_falha_fechada(self):
        configuracao = FormaPagamentoFilial(
            filial=self.filial,
            forma_pagamento=self.crediario,
            codigo_fiscal_tpag="99",
        )
        with self.assertRaisesMessage(ValidationError, "Informe xPag"):
            configuracao.full_clean()
        configuracao.codigo_fiscal_tpag = "05"
        configuracao.descricao_fiscal_xpag = "Convênio"
        with self.assertRaisesMessage(ValidationError, "xPag só pode"):
            configuracao.full_clean()

        configuracao.codigo_fiscal_tpag = "98"
        configuracao.descricao_fiscal_xpag = ""
        with self.assertRaisesMessage(ValidationError, "não é reconhecido"):
            configuracao.full_clean()

        configuracao.codigo_fiscal_tpag = "90"
        with self.assertRaisesMessage(ValidationError, "não é suportado no fluxo"):
            configuracao.full_clean()

    def test_calcular_item_quantiza_venda_fracionada_uma_vez_em_centavos(self):
        for quantidade, preco, esperado in (
            ("0.155", "14.99", "2.32"),
            ("0.750", "14.99", "11.24"),
            ("1.000", "14.99", "14.99"),
            ("1.250", "14.99", "18.74"),
            ("0.333", "19.99", "6.66"),
        ):
            with self.subTest(quantidade=quantidade, preco=preco):
                self.produto.preco_venda = Decimal(preco)
                self.assertEqual(calcular_item(self.produto, Decimal(quantidade)), Decimal(esperado))

    def test_venda_pesavel_preserva_quantidade_custo_e_total_monetario(self):
        self.produto.nome = "Carne bovina"
        self.produto.unidade = "KG"
        self.produto.produto_pesavel = True
        self.produto.preco_venda = Decimal("14.99")
        self.produto.save(update_fields=["nome", "unidade", "produto_pesavel", "preco_venda", "updated_at"])
        self.estoque.custo_medio = Decimal("10.123456")
        self.estoque.save(update_fields=["custo_medio", "atualizado_em"])

        venda = finalizar_venda(
            caixa=self.caixa,
            usuario=self.usuario,
            itens=[{"produto": self.produto, "quantidade": Decimal("0.155")}],
            pagamentos=[{"forma_pagamento": self.dinheiro, "valor": Decimal("2.32")}],
        )

        item = venda.itens.get()
        self.assertEqual(item.quantidade, Decimal("0.155"))
        self.assertEqual(item.preco_unitario_venda, Decimal("14.99"))
        self.assertEqual(item.total, Decimal("2.32"))
        self.assertEqual(venda.total_bruto, Decimal("2.32"))
        self.assertEqual(venda.total_liquido, Decimal("2.32"))
        self.assertEqual(venda.pagamentos.get().valor, Decimal("2.32"))
        self.assertEqual(item.custo_unitario_no_momento, Decimal("10.123456"))
        self.assertEqual(item.quantidade * item.custo_unitario_no_momento, Decimal("1.569135680"))

    def test_snapshot_cmv_preserva_custo_de_fracao_de_centavo(self):
        self.produto.preco_venda = Decimal("1.00")
        self.produto.save(update_fields=["preco_venda", "updated_at"])
        self.estoque.custo_medio = Decimal("0.833333")
        self.estoque.save(update_fields=["custo_medio", "atualizado_em"])

        venda = finalizar_venda(
            caixa=self.caixa,
            usuario=self.usuario,
            itens=[{"produto": self.produto, "quantidade": Decimal("1.000")}],
            pagamentos=[{"forma_pagamento": self.dinheiro, "valor": Decimal("1.00")}],
        )

        self.assertEqual(venda.itens.get().custo_unitario_no_momento, Decimal("0.833333"))

    def test_pagamento_com_fracao_inferior_a_centavo_e_rejeitado(self):
        self.produto.preco_venda = Decimal("10.00")
        self.produto.save(update_fields=["preco_venda", "updated_at"])

        with self.assertRaisesMessage(ValidationError, "A soma dos pagamentos deve ser igual ao total da venda"):
            finalizar_venda(
                caixa=self.caixa,
                usuario=self.usuario,
                itens=[{"produto": self.produto, "quantidade": Decimal("1.000")}],
                pagamentos=[{"forma_pagamento": self.dinheiro, "valor": Decimal("10.001")}],
            )

        self.assertFalse(Venda.objects.exists())

    def test_devolucao_fracionada_quantiza_valor_em_centavos(self):
        self.produto.preco_venda = Decimal("14.99")
        self.produto.save(update_fields=["preco_venda", "updated_at"])
        venda = finalizar_venda(
            caixa=self.caixa,
            usuario=self.usuario,
            itens=[{"produto": self.produto, "quantidade": Decimal("0.750")}],
            pagamentos=[{"forma_pagamento": self.dinheiro, "valor": Decimal("11.24")}],
        )

        devolucao = registrar_devolucao_venda(
            venda=venda,
            usuario=self.usuario,
            itens=[{"item_venda": venda.itens.get(), "quantidade": Decimal("0.250")}],
            motivo="Devolução fracionada",
        )

        self.assertEqual(devolucao.valor_total, Decimal("3.75"))
        self.assertEqual(devolucao.itens.get().valor_total, Decimal("3.75"))

    def test_devolucao_parcial_rateia_estorno_financeiro_por_pagamento(self):
        self.habilitar_pix()
        venda = finalizar_venda(
            caixa=self.caixa,
            usuario=self.usuario,
            itens=[{"produto": self.produto, "quantidade": Decimal("2.000")}],
            pagamentos=[
                {"forma_pagamento": self.dinheiro, "valor": Decimal("20.00")},
                {
                    "forma_pagamento": self.pix,
                    "valor": Decimal("30.00"),
                    "transacao_externa_id": "PIX-123",
                    "nsu": "NSU123",
                    "codigo_autorizacao": "AUT123",
                },
            ],
        )
        item = venda.itens.get()

        devolucao = registrar_devolucao_venda(
            venda=venda,
            usuario=self.usuario,
            itens=[{"item_venda": item, "quantidade": Decimal("1.000")}],
            motivo="Devolucao parcial",
        )

        self.assertEqual(devolucao.valor_total, Decimal("25.00000"))
        self.assertEqual(PagamentoVenda.objects.filter(venda=venda, status=StatusPagamento.CONFIRMADO).count(), 2)
        estornos = LancamentoFinanceiro.objects.filter(origem="ESTORNO", pagamento_venda__venda=venda)
        self.assertEqual(estornos.count(), 1)
        self.assertEqual(estornos.get().valor, Decimal("10.00"))

        estorno_pix = EstornoParcialPagamento.objects.get(devolucao=devolucao)
        self.assertEqual(estorno_pix.valor, Decimal("15.00"))
        self.assertEqual(estorno_pix.status, StatusEstornoParcial.PENDENTE)
        self.assertFalse(estornos.filter(pagamento_venda=estorno_pix.pagamento).exists())

        confirmar_estorno_parcial_eletronico(
            estorno=estorno_pix,
            usuario=self.usuario,
            autorizacao="PIX-EST-123",
            transacao_estorno_id="REFUND-PIX-123",
            mensagem_processadora="Estorno PIX aprovado.",
        )
        estorno_pix.refresh_from_db()
        self.assertEqual(estorno_pix.status, StatusEstornoParcial.CONFIRMADO)
        self.assertEqual(estorno_pix.transacao_estorno_id, "REFUND-PIX-123")
        self.assertEqual(estornos.count(), 2)
        self.assertEqual(estornos.aggregate(total=Sum("valor"))["total"], Decimal("25.00"))
        with self.assertRaisesMessage(ValidationError, "Apenas estornos parciais pendentes"):
            confirmar_estorno_parcial_eletronico(
                estorno=estorno_pix,
                usuario=self.usuario,
                autorizacao="REPETIDO",
            )
        self.assertEqual(estornos.count(), 2)
        with self.assertRaisesMessage(ValidationError, "Venda com devolução parcial não pode ser cancelada integralmente"):
            cancelar_venda(venda=venda, usuario=self.usuario, motivo="Cancelamento indevido")

    def test_finalizar_venda_rejeita_pagamento_incompleto(self):
        with self.assertRaises(ValidationError):
            finalizar_venda(
                caixa=self.caixa,
                usuario=self.usuario,
                itens=[{"produto": self.produto, "quantidade": Decimal("1.000")}],
                pagamentos=[{"forma_pagamento": self.pix, "valor": Decimal("10.00")}],
            )

        self.assertFalse(Venda.objects.exists())
        self.estoque.refresh_from_db()
        self.assertEqual(self.estoque.quantidade_atual, Decimal("10.000"))

    def test_finalizar_venda_rejeita_pagamento_eletronico_pendente(self):
        self.habilitar_pix()
        with self.assertRaisesMessage(ValidationError, "Todos os pagamentos devem estar confirmados"):
            finalizar_venda(
                caixa=self.caixa,
                usuario=self.usuario,
                itens=[{"produto": self.produto, "quantidade": Decimal("1.000")}],
                pagamentos=[
                    {
                        "forma_pagamento": self.pix,
                        "valor": Decimal("25.00"),
                        "status": StatusPagamento.PENDENTE,
                        "transacao_externa_id": "pix-pendente-1",
                    }
                ],
            )

        self.assertFalse(Venda.objects.exists())
        self.estoque.refresh_from_db()
        self.assertEqual(self.estoque.quantidade_atual, Decimal("10.000"))

    def test_pagamento_eletronico_confirmado_gera_autorizacao_simulada(self):
        self.habilitar_pix()
        venda = finalizar_venda(
            caixa=self.caixa,
            usuario=self.usuario,
            itens=[{"produto": self.produto, "quantidade": Decimal("1.000")}],
            pagamentos=[{"forma_pagamento": self.pix, "valor": Decimal("25.00")}],
        )

        pagamento = venda.pagamentos.get()
        self.assertEqual(pagamento.status, StatusPagamento.CONFIRMADO)
        self.assertTrue(pagamento.transacao_externa_id.startswith("TEF-SIM-"))
        self.assertTrue(pagamento.nsu)
        self.assertTrue(pagamento.codigo_autorizacao)
        self.assertIn("Autorização eletrônica simulada", pagamento.mensagem_processadora)

    def test_pagamento_eletronico_preserva_metadados_nao_integrados(self):
        self.habilitar_pix()
        venda = finalizar_venda(
            caixa=self.caixa,
            usuario=self.usuario,
            itens=[{"produto": self.produto, "quantidade": Decimal("1.000")}],
            pagamentos=[
                {
                    "forma_pagamento": self.pix,
                    "valor": Decimal("25.00"),
                    "transacao_externa_id": "pix-e2e-real",
                    "nsu": "123456",
                    "codigo_autorizacao": "ABC123",
                    "tipo_integracao": "2",
                    "cnpj_instituicao_pagamento": "12.ABC.345/01DE-35",
                    "bandeira_cartao": "01",
                    "cnpj_beneficiario_pagamento": "00.ABC.000/0000-01",
                    "identificador_terminal_pagamento": "PINPAD-01",
                    "mensagem_processadora": "Aprovado pela operadora.",
                }
            ],
        )

        pagamento = venda.pagamentos.get()
        self.assertEqual(pagamento.transacao_externa_id, "pix-e2e-real")
        self.assertEqual(pagamento.nsu, "123456")
        self.assertEqual(pagamento.codigo_autorizacao, "ABC123")
        self.assertEqual(pagamento.tipo_integracao, "2")
        self.assertEqual(pagamento.cnpj_instituicao_pagamento, "12ABC34501DE35")
        self.assertEqual(pagamento.bandeira_cartao, "01")
        self.assertEqual(pagamento.cnpj_beneficiario_pagamento, "00ABC000000001")
        self.assertEqual(pagamento.identificador_terminal_pagamento, "PINPAD-01")
        self.assertEqual(pagamento.mensagem_processadora, "Aprovado pela operadora.")

    def test_pagamento_eletronico_rejeita_metadado_fiscal_malformado(self):
        self.habilitar_pix()
        base = {
            "forma_pagamento": self.pix,
            "valor": Decimal("25.00"),
            "transacao_externa_id": "pix-e2e-real",
            "nsu": "123456",
            "codigo_autorizacao": "ABC123",
        }
        invalidos = (
            ({"tipo_integracao": "3"}, "Tipo de integração"),
            ({"cnpj_instituicao_pagamento": "123"}, "14 caracteres"),
            ({"bandeira_cartao": "VISA"}, "2 dígitos"),
            ({"identificador_terminal_pagamento": "X" * 41}, "40 caracteres"),
        )
        for dados, mensagem in invalidos:
            with self.subTest(dados=dados), self.assertRaisesMessage(ValidationError, mensagem):
                finalizar_venda(
                    caixa=self.caixa,
                    usuario=self.usuario,
                    itens=[{"produto": self.produto, "quantidade": Decimal("1.000")}],
                    pagamentos=[{**base, **dados}],
                )

    def test_finalizar_venda_prepara_nfce_automaticamente_quando_fiscal_esta_pronto(self):
        self.filial.uf = "SP"
        self.filial.codigo_municipio_ibge = "3550308"
        self.filial.save(update_fields=["uf", "codigo_municipio_ibge"])
        self.produto.ncm = "10063021"
        self.produto.origem_mercadoria = "0"
        self.produto.cst_icms = "00"
        self.produto.aliquota_icms = Decimal("18.00")
        self.produto.cst_pis = "01"
        self.produto.aliquota_pis = Decimal("1.6500")
        self.produto.cst_cofins = "01"
        self.produto.aliquota_cofins = Decimal("7.6000")
        self.produto.save(
            update_fields=[
                "ncm", "origem_mercadoria", "cst_icms", "aliquota_icms",
                "cst_pis", "aliquota_pis", "cst_cofins", "aliquota_cofins",
            ]
        )
        ConfiguracaoFiscal.objects.create(
            filial=self.filial,
            ambiente=AmbienteFiscal.HOMOLOGACAO,
            regime_tributario="Regime normal",
            inscricao_estadual="123456789",
            csc_id="1",
            csc_token_criptografado=criptografar("token"),
            url_qrcode_nfce="https://homologacao.exemplo.gov.br/qrcode",
            url_consulta_nfce="https://homologacao.exemplo.gov.br/consulta",
            certificado_a1_criptografado=b"certificado",
            certificado_senha_criptografada=b"senha",
        )
        SerieFiscal.objects.create(filial=self.filial, tipo_documento=TipoDocumentoFiscal.NFCE, serie=1, proximo_numero=10)
        NaturezaOperacao.objects.create(empresa=self.filial.empresa, descricao="Venda ao consumidor", cfop="5102", tipo_documento=TipoDocumentoFiscal.NFCE)

        venda = finalizar_venda(
            caixa=self.caixa,
            usuario=self.usuario,
            itens=[{"produto": self.produto, "quantidade": Decimal("1.000")}],
            pagamentos=[{"forma_pagamento": self.dinheiro, "valor": Decimal("25.00")}],
        )

        documento = DocumentoFiscal.objects.get(venda=venda)
        self.assertEqual(documento.status, StatusDocumentoFiscal.PRONTO)
        self.assertEqual(documento.numero, 10)
        self.assertIn("<NFe", documento.xml_conteudo)
        self.assertNotIn("<CPF>", documento.xml_conteudo)
        self.assertEqual(SerieFiscal.objects.get(filial=self.filial).proximo_numero, 11)

    def test_finalizar_venda_com_cpf_na_nota_grava_documento_e_xml_nfce(self):
        self.filial.uf = "SP"
        self.filial.codigo_municipio_ibge = "3550308"
        self.filial.save(update_fields=["uf", "codigo_municipio_ibge"])
        self.produto.ncm = "10063021"
        self.produto.origem_mercadoria = "0"
        self.produto.cst_icms = "00"
        self.produto.aliquota_icms = Decimal("18.00")
        self.produto.cst_pis = "01"
        self.produto.aliquota_pis = Decimal("1.6500")
        self.produto.cst_cofins = "01"
        self.produto.aliquota_cofins = Decimal("7.6000")
        self.produto.save(
            update_fields=[
                "ncm", "origem_mercadoria", "cst_icms", "aliquota_icms",
                "cst_pis", "aliquota_pis", "cst_cofins", "aliquota_cofins",
            ]
        )
        ConfiguracaoFiscal.objects.create(
            filial=self.filial,
            ambiente=AmbienteFiscal.HOMOLOGACAO,
            regime_tributario="Regime normal",
            inscricao_estadual="123456789",
            csc_id="1",
            csc_token_criptografado=criptografar("token"),
            url_qrcode_nfce="https://homologacao.exemplo.gov.br/qrcode",
            url_consulta_nfce="https://homologacao.exemplo.gov.br/consulta",
            certificado_a1_criptografado=b"certificado",
            certificado_senha_criptografada=b"senha",
        )
        SerieFiscal.objects.create(filial=self.filial, tipo_documento=TipoDocumentoFiscal.NFCE, serie=1, proximo_numero=10)
        NaturezaOperacao.objects.create(empresa=self.filial.empresa, descricao="Venda ao consumidor", cfop="5102", tipo_documento=TipoDocumentoFiscal.NFCE)

        venda = finalizar_venda(
            caixa=self.caixa,
            usuario=self.usuario,
            itens=[{"produto": self.produto, "quantidade": Decimal("1.000")}],
            pagamentos=[{"forma_pagamento": self.dinheiro, "valor": Decimal("25.00")}],
            documento_consumidor_tipo=TipoDocumentoConsumidor.CPF,
            documento_consumidor="123.456.789-09",
        )

        documento = DocumentoFiscal.objects.get(venda=venda)
        self.assertEqual(venda.documento_consumidor, "12345678909")
        self.assertIn("<CPF>12345678909</CPF>", documento.xml_conteudo)

    def test_finalizar_venda_rejeita_cpf_com_digitos_verificadores_invalidos(self):
        with self.assertRaisesMessage(ValidationError, "CPF válido"):
            finalizar_venda(
                caixa=self.caixa,
                usuario=self.usuario,
                itens=[{"produto": self.produto, "quantidade": Decimal("1.000")}],
                pagamentos=[{"forma_pagamento": self.dinheiro, "valor": Decimal("25.00")}],
                documento_consumidor_tipo=TipoDocumentoConsumidor.CPF,
                documento_consumidor="111.111.111-11",
            )

        self.assertFalse(Venda.objects.exists())
        self.estoque.refresh_from_db()
        self.assertEqual(self.estoque.quantidade_atual, Decimal("10.000"))

    def test_finalizar_venda_com_cnpj_na_nota_grava_documento_e_xml_nfce(self):
        self.filial.uf = "SP"
        self.filial.codigo_municipio_ibge = "3550308"
        self.filial.save(update_fields=["uf", "codigo_municipio_ibge"])
        self.produto.ncm = "10063021"
        self.produto.origem_mercadoria = "0"
        self.produto.cst_icms = "00"
        self.produto.aliquota_icms = Decimal("18.00")
        self.produto.cst_pis = "01"
        self.produto.aliquota_pis = Decimal("1.6500")
        self.produto.cst_cofins = "01"
        self.produto.aliquota_cofins = Decimal("7.6000")
        self.produto.save(
            update_fields=[
                "ncm", "origem_mercadoria", "cst_icms", "aliquota_icms",
                "cst_pis", "aliquota_pis", "cst_cofins", "aliquota_cofins",
            ]
        )
        ConfiguracaoFiscal.objects.create(
            filial=self.filial,
            ambiente=AmbienteFiscal.HOMOLOGACAO,
            regime_tributario="Regime normal",
            inscricao_estadual="123456789",
            csc_id="",
            url_qrcode_nfce="https://homologacao.exemplo.gov.br/qrcode",
            url_consulta_nfce="https://homologacao.exemplo.gov.br/consulta",
            certificado_a1_criptografado=b"certificado",
            certificado_senha_criptografada=b"senha",
        )
        SerieFiscal.objects.create(
            filial=self.filial,
            tipo_documento=TipoDocumentoFiscal.NFCE,
            serie=1,
            proximo_numero=10,
        )
        NaturezaOperacao.objects.create(
            empresa=self.filial.empresa,
            descricao="Venda ao consumidor",
            cfop="5102",
            tipo_documento=TipoDocumentoFiscal.NFCE,
        )

        venda = finalizar_venda(
            caixa=self.caixa,
            usuario=self.usuario,
            itens=[{"produto": self.produto, "quantidade": Decimal("1.000")}],
            pagamentos=[{"forma_pagamento": self.dinheiro, "valor": Decimal("25.00")}],
            documento_consumidor_tipo=TipoDocumentoConsumidor.CNPJ,
            documento_consumidor="04.252.011/0001-10",
        )

        documento = DocumentoFiscal.objects.get(venda=venda)
        self.assertEqual(venda.documento_consumidor, "04252011000110")
        self.assertIn("<CNPJ>04252011000110</CNPJ>", documento.xml_conteudo)
        self.assertIn("<indIEDest>9</indIEDest>", documento.xml_conteudo)

    def test_finalizar_venda_rejeita_cnpj_invalido(self):
        with self.assertRaisesMessage(ValidationError, "CNPJ válido"):
            finalizar_venda(
                caixa=self.caixa,
                usuario=self.usuario,
                itens=[{"produto": self.produto, "quantidade": Decimal("1.000")}],
                pagamentos=[{"forma_pagamento": self.dinheiro, "valor": Decimal("25.00")}],
                documento_consumidor_tipo=TipoDocumentoConsumidor.CNPJ,
                documento_consumidor="12.345.678/0001-91",
            )

        self.assertFalse(Venda.objects.exists())

    def test_venda_crediario_cria_conta_receber(self):
        venda = finalizar_venda(
            caixa=self.caixa,
            usuario=self.usuario,
            cliente=self.cliente,
            itens=[{"produto": self.produto, "quantidade": Decimal("1.000")}],
            pagamentos=[{"forma_pagamento": self.crediario, "valor": Decimal("25.00")}],
        )

        conta = ContaFinanceira.objects.get(venda=venda)
        self.assertEqual(conta.tipo, TipoContaFinanceira.RECEBER)
        self.assertEqual(conta.status, StatusContaFinanceira.ABERTA)
        self.assertEqual(conta.valor, Decimal("25.00"))
        self.assertEqual(conta.cliente, self.cliente)
        self.assertEqual(conta.categoria.empresa, self.empresa)

    def test_venda_crediario_exige_cliente(self):
        with self.assertRaises(ValidationError):
            finalizar_venda(
                caixa=self.caixa,
                usuario=self.usuario,
                itens=[{"produto": self.produto, "quantidade": Decimal("1.000")}],
                pagamentos=[{"forma_pagamento": self.crediario, "valor": Decimal("25.00")}],
            )

        self.assertFalse(ContaFinanceira.objects.exists())

    def test_cancelamento_de_venda_mista_estorna_local_e_aguarda_operadora(self):
        self.habilitar_pix()
        venda = finalizar_venda(
            caixa=self.caixa,
            usuario=self.usuario,
            itens=[{"produto": self.produto, "quantidade": Decimal("1.000")}],
            pagamentos=[
                {"forma_pagamento": self.dinheiro, "valor": Decimal("10.00")},
                {
                    "forma_pagamento": self.pix,
                    "valor": Decimal("15.00"),
                    "transacao_externa_id": "pix-e2e-123",
                    "nsu": "123456",
                },
            ],
        )

        cancelar_venda(venda=venda, usuario=self.usuario, motivo="Venda duplicada")

        venda.refresh_from_db()
        dinheiro = venda.pagamentos.get(forma_pagamento=self.dinheiro)
        pix = venda.pagamentos.get(forma_pagamento=self.pix)
        self.assertEqual(dinheiro.status, StatusPagamento.ESTORNADO)
        self.assertIsNotNone(dinheiro.estornado_em)
        self.assertEqual(pix.status, StatusPagamento.ESTORNO_PENDENTE)
        self.assertIsNone(pix.estornado_em)
        self.assertEqual(pix.motivo_estorno, "Venda duplicada")
        self.assertIsNotNone(venda.cancelada_em)
        self.assertEqual(venda.cancelada_por, self.usuario)
        self.assertEqual(venda.motivo_cancelamento, "Venda duplicada")
        self.assertEqual(LancamentoFinanceiro.objects.filter(origem="PDV_VENDA").count(), 2)
        self.assertEqual(LancamentoFinanceiro.objects.filter(origem="ESTORNO").count(), 1)
        self.assertTrue(LancamentoFinanceiro.objects.filter(pagamento_venda=dinheiro, tipo=TipoLancamentoFinanceiro.ENTRADA).exists())
        self.assertTrue(LancamentoFinanceiro.objects.filter(pagamento_venda=dinheiro, tipo=TipoLancamentoFinanceiro.SAIDA).exists())
        self.assertFalse(LancamentoFinanceiro.objects.filter(pagamento_venda=pix, origem="ESTORNO").exists())

    def test_confirmacao_de_estorno_eletronico_reverte_financeiro(self):
        self.habilitar_pix()
        venda = finalizar_venda(
            caixa=self.caixa,
            usuario=self.usuario,
            itens=[{"produto": self.produto, "quantidade": Decimal("1.000")}],
            pagamentos=[
                {
                    "forma_pagamento": self.pix,
                    "valor": Decimal("25.00"),
                    "transacao_externa_id": "pix-e2e-123",
                    "nsu": "123456",
                    "codigo_autorizacao": "AUT123",
                },
            ],
        )
        cancelar_venda(venda=venda, usuario=self.usuario, motivo="Venda duplicada")
        pagamento = venda.pagamentos.get()

        confirmar_estorno_pagamento_eletronico(
            pagamento=pagamento,
            usuario=self.usuario,
            motivo="Operadora confirmou",
            autorizacao="EST987",
        )

        pagamento.refresh_from_db()
        self.assertEqual(pagamento.status, StatusPagamento.ESTORNADO)
        self.assertIsNotNone(pagamento.estornado_em)
        self.assertIn("EST987", pagamento.mensagem_processadora)
        self.assertTrue(LancamentoFinanceiro.objects.filter(pagamento_venda=pagamento, origem="ESTORNO").exists())

# Create your tests here.
