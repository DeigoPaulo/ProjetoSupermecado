import json
from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.compras.models import EntradaCompra, ItemEntradaCompra
from apps.compras.services import finalizar_entrada_compra
from apps.empresas.models import Empresa, Filial
from apps.fiscal.models import DocumentoFiscal
from apps.fornecedores.models import Fornecedor
from apps.pdv.models import Caixa
from apps.produtos.models import Categoria, Produto
from apps.vendas.models import FormaPagamento
from apps.vendas.services import finalizar_venda

from .evidencia_piloto import gerar_evidencia_fluxo_estoque_piloto
from .fechamento_contabil import capturar_fechamento_estoque_contabil
from .models import (
    Estoque,
    LoteEstoque,
    MovimentacaoLoteEstoque,
    StatusInventario,
    StatusTratamentoValidade,
)
from .services import (
    aplicar_inventario,
    criar_inventario_divergencias_validade,
    planejar_tratamento_validade_lote,
    registrar_conferencia_fisica_validade_lote,
    registrar_contagem_lote_inventario_validade,
    registrar_perda_lote_validade,
)


class FluxoEstoquePilotoPontaAPontaTests(TestCase):
    def test_compra_venda_perda_inventario_e_fechamento_geram_evidencia_valida(self):
        usuario = get_user_model().objects.create_superuser(
            "master-piloto-estoque", "piloto@example.com", "senha"
        )
        empresa = Empresa.objects.create(
            razao_social="Mercado Piloto Sintético Ltda",
            nome_fantasia="Mercado Piloto Sintético",
            cnpj="91.111.111/0001-91",
        )
        filial = Filial.objects.create(
            empresa=empresa, nome="Filial Ensaio", cnpj=empresa.cnpj
        )
        fornecedor = Fornecedor.objects.create(
            razao_social="Fornecedor Sintético Ltda",
            nome_fantasia="Fornecedor Sintético",
        )
        categoria = Categoria.all_objects.create(nome="Categoria Ensaio Ponta a Ponta")
        produto = Produto.objects.create(
            codigo_barras="7899911111111",
            nome="Produto Sintético Rastreado",
            categoria=categoria,
            preco_custo=Decimal("4.00"),
            preco_venda=Decimal("10.00"),
            exige_lote=True,
        )
        entrada = EntradaCompra.objects.create(
            fornecedor=fornecedor,
            filial=filial,
            usuario=usuario,
            numero_documento="ENSAIO-SEM-VALOR-FISCAL",
            gerar_conta_financeira=False,
        )
        ItemEntradaCompra.objects.create(
            entrada=entrada,
            produto=produto,
            quantidade=Decimal("3.000"),
            custo_unitario=Decimal("4.00"),
            total=Decimal("12.00"),
            codigo_lote="LOTE-VENCIDO-ENSAIO",
            validade=timezone.localdate() - timedelta(days=1),
        )
        ItemEntradaCompra.objects.create(
            entrada=entrada,
            produto=produto,
            quantidade=Decimal("7.000"),
            custo_unitario=Decimal("4.00"),
            total=Decimal("28.00"),
            codigo_lote="LOTE-VALIDO-ENSAIO",
            validade=timezone.localdate() + timedelta(days=10),
        )
        finalizar_entrada_compra(entrada, supervisor=usuario)

        lote_vencido = LoteEstoque.objects.get(codigo="LOTE-VENCIDO-ENSAIO")
        lote_valido = LoteEstoque.objects.get(codigo="LOTE-VALIDO-ENSAIO")
        caixa = Caixa.objects.create(
            filial=filial, usuario_abertura=usuario, valor_inicial=Decimal("0.00")
        )
        dinheiro = FormaPagamento.objects.create(
            nome="Dinheiro Ensaio", tipo="DINHEIRO", permite_troco=True
        )
        venda = finalizar_venda(
            caixa=caixa,
            usuario=usuario,
            itens=[{"produto": produto, "quantidade": Decimal("2.000")}],
            pagamentos=[{"forma_pagamento": dinheiro, "valor": Decimal("20.00")}],
            preparar_fiscal=False,
        )
        lote_vencido.refresh_from_db()
        lote_valido.refresh_from_db()
        self.assertEqual(lote_vencido.quantidade_atual, Decimal("3.000"))
        self.assertEqual(lote_valido.quantidade_atual, Decimal("5.000"))
        alocacao_venda = MovimentacaoLoteEstoque.objects.get(
            movimentacao__referencia=f"venda:{venda.pk}", lote=lote_valido
        )
        self.assertEqual(alocacao_venda.lote_codigo_snapshot, "LOTE-VALIDO-ENSAIO")
        self.assertEqual(alocacao_venda.lote_validade_snapshot, lote_valido.validade)
        self.assertEqual(
            alocacao_venda.tratamento_status_snapshot,
            StatusTratamentoValidade.NAO_INICIADO,
        )
        self.assertTrue(alocacao_venda.snapshot_integro)

        planejar_tratamento_validade_lote(
            lote=lote_vencido,
            status=StatusTratamentoValidade.DESCARTE_PLANEJADO,
            observacao="Separado para o ensaio de descarte controlado.",
            usuario=usuario,
        )
        registrar_conferencia_fisica_validade_lote(
            lote=lote_vencido,
            quantidade_observada=Decimal("3.000"),
            observacao="Conferência sintética antes da perda.",
            confirmar_dados=True,
            usuario=usuario,
        )
        perda = registrar_perda_lote_validade(
            lote=lote_vencido,
            quantidade=Decimal("1.000"),
            motivo="Unidade sintética vencida",
            usuario=usuario,
            supervisor=usuario,
        )
        lote_vencido.refresh_from_db()
        registrar_conferencia_fisica_validade_lote(
            lote=lote_vencido,
            quantidade_observada=Decimal("1.000"),
            observacao="Divergência sintética restante para inventário.",
            confirmar_dados=True,
            usuario=usuario,
        )
        inventario, criado = criar_inventario_divergencias_validade(
            filial=filial,
            lotes=[lote_vencido],
            usuario=usuario,
            descricao="Ensaio integrado de validade",
        )
        self.assertTrue(criado)
        item = inventario.itens.get(produto=produto)
        item.quantidade_contada = Decimal("6.000")
        item.save(update_fields=["quantidade_contada"])
        for escopo in item.escopos_validade.select_related("lote"):
            registrar_contagem_lote_inventario_validade(
                escopo=escopo,
                quantidade_contada=(
                    Decimal("1.000") if escopo.lote_id == lote_vencido.pk
                    else escopo.lote.quantidade_atual
                ),
                usuario=usuario,
                observacao="Contagem do ensaio ponta a ponta.",
                confirmar_dados=True,
            )
        aplicar_inventario(
            inventario=inventario, usuario=usuario, supervisor=usuario
        )
        inventario.refresh_from_db()
        self.assertEqual(inventario.status, StatusInventario.APLICADO)
        self.assertEqual(
            Estoque.objects.get(produto=produto, filial=filial).quantidade_atual,
            Decimal("6.000"),
        )

        lote_valido.validade = timezone.localdate() - timedelta(days=2)
        lote_valido.tratamento_validade_status = StatusTratamentoValidade.SEPARADO
        lote_valido.save(update_fields=[
            "validade", "tratamento_validade_status", "atualizado_em"
        ])
        alocacao_venda.refresh_from_db()
        self.assertEqual(alocacao_venda.lote_codigo_snapshot, "LOTE-VALIDO-ENSAIO")
        self.assertEqual(
            alocacao_venda.tratamento_status_snapshot,
            StatusTratamentoValidade.NAO_INICIADO,
        )
        self.assertTrue(alocacao_venda.snapshot_integro)

        fechamento, criado_fechamento = capturar_fechamento_estoque_contabil(
            filial=filial, usuario=usuario
        )
        self.assertTrue(criado_fechamento)
        saida = StringIO()
        call_command(
            "verificar_fluxo_estoque_piloto",
            entrada_id=entrada.pk,
            venda_id=venda.pk,
            perda_id=perda.pk,
            inventario_id=inventario.pk,
            fechamento_id=fechamento.pk,
            estrito=True,
            dados_sinteticos=True,
            stdout=saida,
        )
        evidencia = json.loads(saida.getvalue())
        self.assertEqual(evidencia["contrato"], "inventory_pilot_end_to_end_evidence_v2")
        self.assertTrue(evidencia["valida"])
        self.assertTrue(evidencia["verificacoes"]["venda_snapshot_lote_preservado"])
        self.assertTrue(evidencia["verificacoes"]["venda_consumiu_somente_tratamento_liberado"])
        self.assertEqual(
            evidencia["alocacoes_venda_snapshot"][0]["tratamento_status"],
            StatusTratamentoValidade.NAO_INICIADO,
        )
        self.assertTrue(all(evidencia["verificacoes"].values()))
        self.assertEqual(len(evidencia["conteudo_sha256"]), 64)
        self.assertTrue(evidencia["somente_leitura"])
        self.assertFalse(evidencia["comunicacao_externa"])
        self.assertTrue(evidencia["dados_sinteticos"])
        self.assertFalse(DocumentoFiscal.objects.exists())

        MovimentacaoLoteEstoque.objects.filter(pk=alocacao_venda.pk).update(
            lote_codigo_snapshot="",
            tratamento_status_snapshot="",
            snapshot_sha256="",
        )
        evidencia_legada = gerar_evidencia_fluxo_estoque_piloto(
            entrada_id=entrada.pk,
            venda_id=venda.pk,
            perda_id=perda.pk,
            inventario_id=inventario.pk,
            fechamento_id=fechamento.pk,
            dados_sinteticos=True,
        )
        self.assertFalse(evidencia_legada["valida"])
        self.assertFalse(
            evidencia_legada["verificacoes"]["venda_snapshot_lote_preservado"]
        )

        outra_filial = Filial.objects.create(
            empresa=empresa, nome="Filial fora do ensaio", cnpj="91.111.111/0002-72"
        )
        outro_fechamento, _ = capturar_fechamento_estoque_contabil(
            filial=outra_filial, usuario=usuario
        )
        with self.assertRaisesMessage(ValidationError, "mesma filial"):
            gerar_evidencia_fluxo_estoque_piloto(
                entrada_id=entrada.pk,
                venda_id=venda.pk,
                perda_id=perda.pk,
                inventario_id=inventario.pk,
                fechamento_id=outro_fechamento.pk,
            )
