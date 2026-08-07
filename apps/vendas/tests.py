from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.test import TestCase

from apps.empresas.models import Empresa, Filial
from apps.estoque.models import Estoque, MovimentacaoEstoque, TipoMovimentacaoEstoque
from apps.financeiro.models import ContaFinanceira, ContaMovimentoFinanceiro, LancamentoFinanceiro, StatusContaFinanceira, TipoContaFinanceira, TipoContaMovimento, TipoLancamentoFinanceiro
from apps.fiscal.models import AmbienteFiscal, ConfiguracaoFiscal, DocumentoFiscal, NaturezaOperacao, SerieFiscal, StatusDocumentoFiscal, TipoDocumentoFiscal
from apps.clientes.models import Cliente
from apps.pdv.models import Caixa
from apps.produtos.models import Categoria, Produto

from .models import EstornoParcialPagamento, FormaPagamento, FormaPagamentoFilial, PagamentoVenda, StatusEstornoParcial, StatusPagamento, StatusVenda, TipoDocumentoConsumidor, Venda
from .services import cancelar_venda, confirmar_estorno_pagamento_eletronico, confirmar_estorno_parcial_eletronico, finalizar_venda, formas_pagamento_disponiveis, registrar_devolucao_venda


class VendaServiceTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(username="operador", password="123")
        self.empresa = Empresa.objects.create(
            razao_social="Mercado Teste Ltda",
            nome_fantasia="Mercado Teste",
            cnpj="11.111.111/0001-11",
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

        self.assertIn(nova_forma, disponiveis)
        self.assertTrue(
            FormaPagamentoFilial.objects.filter(
                filial=self.filial,
                forma_pagamento=nova_forma,
                ativo=True,
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

    def test_devolucao_parcial_rateia_estorno_financeiro_por_pagamento(self):
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

    def test_pagamento_eletronico_preserva_autorizacao_real(self):
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
                    "mensagem_processadora": "Aprovado pela operadora.",
                }
            ],
        )

        pagamento = venda.pagamentos.get()
        self.assertEqual(pagamento.transacao_externa_id, "pix-e2e-real")
        self.assertEqual(pagamento.nsu, "123456")
        self.assertEqual(pagamento.codigo_autorizacao, "ABC123")
        self.assertEqual(pagamento.mensagem_processadora, "Aprovado pela operadora.")

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
            csc_token="token",
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
            csc_token="token",
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

    def test_finalizar_venda_com_cnpj_na_nota_bloqueia_nfce_automatica(self):
        with self.assertRaisesMessage(ValidationError, "NF-e modelo 55"):
            finalizar_venda(
                caixa=self.caixa,
                usuario=self.usuario,
                itens=[{"produto": self.produto, "quantidade": Decimal("1.000")}],
                pagamentos=[{"forma_pagamento": self.dinheiro, "valor": Decimal("25.00")}],
                documento_consumidor_tipo=TipoDocumentoConsumidor.CNPJ,
                documento_consumidor="12.345.678/0001-90",
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

        dinheiro = venda.pagamentos.get(forma_pagamento=self.dinheiro)
        pix = venda.pagamentos.get(forma_pagamento=self.pix)
        self.assertEqual(dinheiro.status, StatusPagamento.ESTORNADO)
        self.assertIsNotNone(dinheiro.estornado_em)
        self.assertEqual(pix.status, StatusPagamento.ESTORNO_PENDENTE)
        self.assertIsNone(pix.estornado_em)
        self.assertEqual(pix.motivo_estorno, "Venda duplicada")
        self.assertEqual(LancamentoFinanceiro.objects.filter(origem="PDV_VENDA").count(), 2)
        self.assertEqual(LancamentoFinanceiro.objects.filter(origem="ESTORNO").count(), 1)
        self.assertTrue(LancamentoFinanceiro.objects.filter(pagamento_venda=dinheiro, tipo=TipoLancamentoFinanceiro.ENTRADA).exists())
        self.assertTrue(LancamentoFinanceiro.objects.filter(pagamento_venda=dinheiro, tipo=TipoLancamentoFinanceiro.SAIDA).exists())
        self.assertFalse(LancamentoFinanceiro.objects.filter(pagamento_venda=pix, origem="ESTORNO").exists())

    def test_confirmacao_de_estorno_eletronico_reverte_financeiro(self):
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
