from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import PerfilUsuario, TipoPerfil
from apps.empresas.models import Empresa, Filial
from apps.pdv.models import Caixa
from apps.produtos.models import Categoria, Produto
from apps.vendas.models import FormaPagamento, Venda
from apps.vendas.services import finalizar_venda

from .models import (
    Estoque,
    LoteEstoque,
    MovimentacaoEstoque,
    MovimentacaoLoteEstoque,
    StatusTratamentoValidade,
    TipoMovimentacaoEstoque,
    movimentar_estoque,
    resumo_disponibilidade_venda_lotes,
)


class SaldoVendavelLotesTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            "estoquista-saldo-vendavel", password="senha"
        )
        self.empresa = Empresa.objects.create(
            razao_social="Mercado Saldo Vendável Ltda",
            nome_fantasia="Mercado Saldo Vendável",
            cnpj="92.222.222/0001-92",
        )
        self.filial = Filial.objects.create(
            empresa=self.empresa, nome="Matriz", cnpj=self.empresa.cnpj
        )
        PerfilUsuario.objects.create(
            usuario=self.usuario, filial=self.filial, tipo=TipoPerfil.ESTOQUISTA
        )
        categoria = Categoria.all_objects.create(nome="Saldo vendável")
        self.produto = Produto.objects.create(
            codigo_barras="7899922222222",
            nome="Produto com quarentena por lote",
            categoria=categoria,
            preco_custo=Decimal("3.00"),
            preco_venda=Decimal("7.00"),
            exige_lote=True,
        )
        self.estoque = Estoque.objects.create(
            produto=self.produto, filial=self.filial, quantidade_atual=Decimal("0.000")
        )

    def criar_lote(self, codigo, quantidade, dias, status):
        return LoteEstoque.objects.create(
            produto=self.produto,
            filial=self.filial,
            codigo=codigo,
            validade=timezone.localdate() + timedelta(days=dias),
            quantidade_inicial=Decimal(quantidade),
            quantidade_atual=Decimal(quantidade),
            custo_unitario=Decimal("3.00"),
            tratamento_validade_status=status,
        )

    def test_venda_ignora_separado_devolucao_descarte_e_consumo_promocao(self):
        separado = self.criar_lote(
            "SEPARADO", "3.000", 1, StatusTratamentoValidade.SEPARADO
        )
        devolucao = self.criar_lote(
            "DEVOLUCAO", "2.000", 2, StatusTratamentoValidade.DEVOLUCAO_PLANEJADA
        )
        descarte = self.criar_lote(
            "DESCARTE", "2.000", 3, StatusTratamentoValidade.DESCARTE_PLANEJADO
        )
        promocao = self.criar_lote(
            "PROMOCAO", "2.000", 4, StatusTratamentoValidade.PROMOCAO_PLANEJADA
        )
        normal = self.criar_lote(
            "NORMAL", "2.000", 5, StatusTratamentoValidade.NAO_INICIADO
        )
        Estoque.objects.filter(pk=self.estoque.pk).update(quantidade_atual=Decimal("11.000"))

        movimento = movimentar_estoque(
            produto=self.produto,
            filial=self.filial,
            tipo=TipoMovimentacaoEstoque.VENDA,
            quantidade=Decimal("3.000"),
            usuario=self.usuario,
            motivo="Venda de teste do saldo liberado",
            referencia="venda:saldo-vendavel",
        )

        alocacoes_registradas = list(
            MovimentacaoLoteEstoque.objects.filter(movimentacao=movimento)
        )
        alocacoes = {
            item.lote_id: item.quantidade for item in alocacoes_registradas
        }
        self.assertEqual(alocacoes, {
            promocao.pk: Decimal("2.000"), normal.pk: Decimal("1.000")
        })
        self.assertTrue(all(item.snapshot_integro for item in alocacoes_registradas))
        self.assertEqual(
            {item.lote_id: item.tratamento_status_snapshot for item in alocacoes_registradas},
            {
                promocao.pk: StatusTratamentoValidade.PROMOCAO_PLANEJADA,
                normal.pk: StatusTratamentoValidade.NAO_INICIADO,
            },
        )
        alocacao_imutavel = alocacoes_registradas[0]
        alocacao_imutavel.quantidade = Decimal("9.000")
        with self.assertRaisesMessage(ValidationError, "alocação histórica do lote é imutável"):
            alocacao_imutavel.save()
        alocacao_imutavel.refresh_from_db()
        self.assertNotEqual(alocacao_imutavel.quantidade, Decimal("9.000"))

        for lote in (separado, devolucao, descarte):
            lote.refresh_from_db()
            self.assertEqual(lote.quantidade_atual, lote.quantidade_inicial)
        resumo = resumo_disponibilidade_venda_lotes(
            produto=self.produto, filial=self.filial
        )
        self.assertEqual(resumo["quantidade_bloqueada"], Decimal("7.000"))
        self.assertEqual(resumo["quantidade_vendavel"], Decimal("1.000"))

    def test_venda_recusa_saldo_segregado_mesmo_com_agregado_suficiente(self):
        self.produto.exige_lote = False
        self.produto.save(update_fields=["exige_lote", "updated_at"])
        bloqueado = self.criar_lote(
            "BLOQUEADO", "3.000", 5, StatusTratamentoValidade.SEPARADO
        )
        Estoque.objects.filter(pk=self.estoque.pk).update(quantidade_atual=Decimal("5.000"))

        with self.assertRaisesMessage(ValidationError, "Estoque vendável insuficiente"):
            movimentar_estoque(
                produto=self.produto,
                filial=self.filial,
                tipo=TipoMovimentacaoEstoque.VENDA,
                quantidade=Decimal("3.000"),
                usuario=self.usuario,
                referencia="venda:bloqueada",
            )

        self.estoque.refresh_from_db()
        bloqueado.refresh_from_db()
        self.assertEqual(self.estoque.quantidade_atual, Decimal("5.000"))
        self.assertEqual(bloqueado.quantidade_atual, Decimal("3.000"))
        self.assertFalse(MovimentacaoEstoque.objects.exists())

    def test_caixa_reverte_venda_com_saldo_segregado(self):
        self.produto.exige_lote = False
        self.produto.save(update_fields=["exige_lote", "updated_at"])
        bloqueado = self.criar_lote(
            "CAIXA-BLOQUEADO", "3.000", 5, StatusTratamentoValidade.SEPARADO
        )
        Estoque.objects.filter(pk=self.estoque.pk).update(quantidade_atual=Decimal("5.000"))
        caixa = Caixa.objects.create(
            filial=self.filial,
            usuario_abertura=self.usuario,
            valor_inicial=Decimal("100.00"),
        )
        dinheiro = FormaPagamento.objects.create(
            nome="Dinheiro saldo vendável", tipo="DINHEIRO", permite_troco=True
        )

        with self.assertRaisesMessage(ValidationError, "Estoque vendável insuficiente"):
            finalizar_venda(
                caixa=caixa,
                usuario=self.usuario,
                itens=[{"produto": self.produto, "quantidade": Decimal("3.000")}],
                pagamentos=[{"forma_pagamento": dinheiro, "valor": Decimal("21.00")}],
                preparar_fiscal=False,
            )

        self.estoque.refresh_from_db()
        bloqueado.refresh_from_db()
        self.assertEqual(self.estoque.quantidade_atual, Decimal("5.000"))
        self.assertEqual(bloqueado.quantidade_atual, Decimal("3.000"))
        self.assertFalse(Venda.objects.exists())
        self.assertFalse(MovimentacaoEstoque.objects.exists())
    def test_perda_direcionada_continua_alcancando_lote_separado(self):
        lote = self.criar_lote(
            "PERDA-DIRETA", "2.000", -1, StatusTratamentoValidade.DESCARTE_PLANEJADO
        )
        Estoque.objects.filter(pk=self.estoque.pk).update(quantidade_atual=Decimal("2.000"))

        movimento = movimentar_estoque(
            produto=self.produto,
            filial=self.filial,
            tipo=TipoMovimentacaoEstoque.PERDA,
            quantidade=Decimal("1.000"),
            usuario=self.usuario,
            referencia="perda:direcionada",
            lote_id=lote.pk,
        )

        lote.refresh_from_db()
        self.assertEqual(lote.quantidade_atual, Decimal("1.000"))
        self.assertTrue(
            MovimentacaoLoteEstoque.objects.filter(
                movimentacao=movimento, lote=lote, quantidade=Decimal("1.000")
            ).exists()
        )

    def test_tela_distingue_disponivel_fisico_vendavel_e_bloqueado(self):
        self.produto.exige_lote = False
        self.produto.save(update_fields=["exige_lote", "updated_at"])
        self.criar_lote(
            "TELA-BLOQUEADO", "3.000", 5, StatusTratamentoValidade.SEPARADO
        )
        Estoque.objects.filter(pk=self.estoque.pk).update(quantidade_atual=Decimal("5.000"))
        self.client.force_login(self.usuario)

        resposta = self.client.get(reverse("estoque:lista"))

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Disponível físico")
        self.assertContains(resposta, "Vendável")
        self.assertContains(resposta, "Bloqueado por lote")
        self.assertContains(resposta, "<strong>2</strong>", html=True)