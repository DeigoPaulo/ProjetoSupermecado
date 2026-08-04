from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.test import Client, TestCase
from django.utils import timezone

from apps.auditoria.models import LogAuditoria
from apps.accounts.models import PerfilUsuario, TipoPerfil
from apps.empresas.models import Empresa, Filial
from apps.estoque.models import (
    AlertaSLAOrdemProducao,
    ComposicaoProduto,
    ConfiguracaoSLASetorProducao,
    DesmembramentoProduto,
    Estoque,
    HistoricoEtapaOrdemProducaoComposicao,
    InventarioEstoque,
    ItemComposicaoProduto,
    ItemDesmembramentoProduto,
    ItemInventarioEstoque,
    LoteEstoque,
    MovimentacaoEstoque,
    MovimentacaoLoteEstoque,
    OrdemProducaoComposicao,
    PerdaEstoque,
    ProducaoComposicaoProduto,
    ReceitaDesmembramento,
    StatusDesmembramentoProduto,
    StatusInventario,
    StatusOrdemProducaoComposicao,
    StatusProducaoComposicao,
    TipoDesmembramentoProduto,
    TipoMovimentacaoEstoque,
    TipoSaidaDesmembramento,
    movimentar_estoque,
)
from apps.estoque.services import (
    aplicar_inventario,
    atribuir_saldo_historico_lote,
    cancelar_desmembramento_produto,
    cancelar_producao_composicao,
    confirmar_desmembramento_multidestino,
    confirmar_desmembramento_simples,
    confirmar_producao_composicao,
    simular_desmembramento_multidestino,
    simular_desmembramento_simples,
)
from apps.produtos.models import Categoria, Produto, UnidadeMedida


class EstoqueViewsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser("admin", "admin@example.com", "123")
        self.client = Client(HTTP_HOST="localhost")
        self.client.force_login(self.user)
        self.empresa = Empresa.objects.create(
            razao_social="Mercado Estoque",
            nome_fantasia="Mercado Estoque",
            cnpj="22.222.222/0001-22",
        )
        self.filial = Filial.objects.create(empresa=self.empresa, nome="Matriz", cnpj=self.empresa.cnpj)
        self.categoria = Categoria.all_objects.create(nome="Estoque Teste")
        self.produto = Produto.objects.create(
            codigo_barras="7892222222222",
            nome="Produto Estoque",
            categoria=self.categoria,
            preco_custo="3.00",
            preco_venda="5.00",
        )

    def test_form_movimentacao_exibe_operacao_e_autorizacao(self):
        response = self.client.get("/estoque/movimentar/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Operacao")
        self.assertContains(response, "Autorizacao")
        self.assertContains(response, "Movimentacoes manuais ficam registradas")
        self.assertContains(response, "select2-field")


    def test_form_perda_exibe_rastreabilidade_e_autorizacao(self):
        response = self.client.get("/estoque/perdas/nova/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Perda")
        self.assertContains(response, "Registre avaria")
        self.assertContains(response, "A baixa reduz estoque")
        self.assertContains(response, "select2-field")

    def test_form_inventario_exibe_abertura_da_contagem(self):
        response = self.client.get("/estoque/inventarios/novo/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Abertura da contagem")
        self.assertContains(response, "antes de adicionar os produtos contados")

    def test_desmembramento_simples_baixa_origem_gera_destino_custo_e_auditoria(self):
        destino = Produto.objects.create(
            codigo_barras="7893333333333",
            nome="Produto Avulso",
            categoria=self.categoria,
            preco_custo="0.00",
            preco_venda="0.80",
        )
        Estoque.objects.create(produto=self.produto, filial=self.filial, quantidade_atual=Decimal("2.000"))
        Estoque.objects.create(produto=destino, filial=self.filial, quantidade_atual=Decimal("5.000"))

        desmembramento = confirmar_desmembramento_simples(
            filial=self.filial,
            produto_origem=self.produto,
            quantidade_origem=Decimal("1.000"),
            produto_destino=destino,
            quantidade_destino=Decimal("30.000"),
            usuario=self.user,
            motivo="Abrir pacote para venda avulsa",
        )

        self.assertEqual(DesmembramentoProduto.objects.count(), 1)
        item = desmembramento.itens.get()
        self.assertEqual(item.quantidade_gerada, Decimal("30.000"))
        self.assertEqual(item.tipo_saida, TipoSaidaDesmembramento.VENDAVEL)
        self.assertEqual(item.custo_unitario_calculado, Decimal("0.10"))
        self.assertEqual(Estoque.objects.get(produto=self.produto, filial=self.filial).quantidade_atual, Decimal("1.000"))
        self.assertEqual(Estoque.objects.get(produto=destino, filial=self.filial).quantidade_atual, Decimal("35.000"))
        self.assertEqual(MovimentacaoEstoque.objects.filter(tipo=TipoMovimentacaoEstoque.DESMEMBRAMENTO).count(), 2)
        self.assertTrue(LogAuditoria.objects.filter(acao="DESMEMBRAMENTO_PRODUTO", objeto_id=str(desmembramento.id)).exists())

    def test_desmembramento_multidestino_distribui_custo_e_movimenta_todos_destinos(self):
        destino_a = Produto.objects.create(
            codigo_barras="7893333333301",
            nome="Corte A",
            categoria=self.categoria,
            preco_custo="0.00",
            preco_venda="15.00",
        )
        destino_b = Produto.objects.create(
            codigo_barras="7893333333302",
            nome="Corte B",
            categoria=self.categoria,
            preco_custo="0.00",
            preco_venda="12.00",
        )
        Estoque.objects.create(produto=self.produto, filial=self.filial, quantidade_atual=Decimal("2.000"))

        desmembramento = confirmar_desmembramento_multidestino(
            filial=self.filial,
            produto_origem=self.produto,
            quantidade_origem=Decimal("1.000"),
            destinos=[
                {
                    "produto": destino_a,
                    "quantidade": Decimal("2.000"),
                    "percentual_rendimento_esperado": Decimal("65.00"),
                    "lote": "LOTE-CORTE-A",
                    "validade": date(2026, 7, 20),
                },
                {"produto": destino_b, "quantidade": Decimal("1.000")},
            ],
            usuario=self.user,
            motivo="Gerar dois destinos",
            tipo="ACOUGUE",
        )

        itens = list(desmembramento.itens.order_by("produto_destino__nome"))
        self.assertEqual(len(itens), 2)
        self.assertEqual(itens[0].custo_unitario_calculado, Decimal("1.00"))
        self.assertEqual(itens[0].custo_total, Decimal("2.00"))
        self.assertEqual(itens[0].percentual_rendimento_esperado, Decimal("65.00"))
        self.assertEqual(itens[0].lote, "LOTE-CORTE-A")
        self.assertEqual(str(itens[0].validade), "2026-07-20")
        self.assertEqual(itens[1].custo_total, Decimal("1.00"))
        self.assertEqual(Estoque.objects.get(produto=self.produto, filial=self.filial).quantidade_atual, Decimal("1.000"))
        self.assertEqual(Estoque.objects.get(produto=destino_a, filial=self.filial).quantidade_atual, Decimal("2.000"))
        self.assertEqual(Estoque.objects.get(produto=destino_b, filial=self.filial).quantidade_atual, Decimal("1.000"))
        self.assertEqual(MovimentacaoEstoque.objects.filter(tipo=TipoMovimentacaoEstoque.DESMEMBRAMENTO).count(), 3)

    def test_desmembramento_simples_classifica_destino_como_perda_ou_subproduto(self):
        destino = Produto.objects.create(
            codigo_barras="7893333333321",
            nome="Apara de carne",
            categoria=self.categoria,
            preco_custo="0.00",
            preco_venda="3.00",
        )
        Estoque.objects.create(produto=self.produto, filial=self.filial, quantidade_atual=Decimal("2.000"))

        desmembramento = confirmar_desmembramento_simples(
            filial=self.filial,
            produto_origem=self.produto,
            quantidade_origem=Decimal("1.000"),
            produto_destino=destino,
            quantidade_destino=Decimal("0.200"),
            tipo_saida_destino=TipoSaidaDesmembramento.SUBPRODUTO,
            usuario=self.user,
            motivo="Separar subproduto aproveitavel",
        )

        item = desmembramento.itens.get()
        self.assertEqual(item.tipo_saida, TipoSaidaDesmembramento.SUBPRODUTO)
        self.assertEqual(item.get_tipo_saida_display(), "Subproduto")

    def test_desmembramento_com_destino_perda_nao_aumenta_estoque_e_gera_perda(self):
        destino = Produto.objects.create(
            codigo_barras="7893333333398",
            nome="Apara descartada",
            categoria=self.categoria,
            preco_custo="0.00",
            preco_venda="2.00",
        )
        Estoque.objects.create(produto=self.produto, filial=self.filial, quantidade_atual=Decimal("2.000"))

        desmembramento = confirmar_desmembramento_simples(
            filial=self.filial,
            produto_origem=self.produto,
            quantidade_origem=Decimal("1.000"),
            produto_destino=destino,
            quantidade_destino=Decimal("0.150"),
            tipo_saida_destino=TipoSaidaDesmembramento.PERDA,
            usuario=self.user,
            motivo="Apara sem aproveitamento",
        )
        item = desmembramento.itens.get()

        self.assertEqual(item.tipo_saida, TipoSaidaDesmembramento.PERDA)
        self.assertFalse(Estoque.objects.filter(produto=destino, filial=self.filial).exists())
        perda = PerdaEstoque.objects.get(desmembramento_item=item)
        self.assertEqual(perda.quantidade, Decimal("0.150"))
        self.assertTrue(
            MovimentacaoEstoque.objects.filter(
                produto=destino,
                tipo=TipoMovimentacaoEstoque.PERDA,
                referencia=f"desmembramento:{desmembramento.id}:perda:item:{item.id}",
            ).exists()
        )

        cancelado = cancelar_desmembramento_produto(
            desmembramento=desmembramento,
            usuario=self.user,
            motivo="Lancamento incorreto",
        )

        self.assertEqual(cancelado.status, StatusDesmembramentoProduto.CANCELADO)
        self.assertFalse(PerdaEstoque.objects.filter(desmembramento_item=item).exists())
        self.assertEqual(Estoque.objects.get(produto=self.produto, filial=self.filial).quantidade_atual, Decimal("2.000"))

    def test_desmembramento_alerta_rendimento_abaixo_do_esperado(self):
        destino = Produto.objects.create(
            codigo_barras="7893333333322",
            nome="Corte com rendimento baixo",
            categoria=self.categoria,
            preco_custo="0.00",
            preco_venda="18.00",
        )
        Estoque.objects.create(produto=self.produto, filial=self.filial, quantidade_atual=Decimal("2.000"))

        desmembramento = confirmar_desmembramento_multidestino(
            filial=self.filial,
            produto_origem=self.produto,
            quantidade_origem=Decimal("1.000"),
            destinos=[
                {
                    "produto": destino,
                    "quantidade": Decimal("0.700"),
                    "percentual_rendimento_esperado": Decimal("80.00"),
                }
            ],
            usuario=self.user,
            motivo="Rendimento abaixo",
            tipo="ACOUGUE",
        )

        item = desmembramento.itens.get()
        self.assertEqual(item.percentual_rendimento, Decimal("70.00"))
        self.assertTrue(item.rendimento_abaixo_esperado)
        self.assertEqual(item.diferenca_rendimento, Decimal("-10.00"))

        detalhe = self.client.get(f"/estoque/desmembramentos/{desmembramento.id}/")
        csv_response = self.client.get("/estoque/desmembramentos/exportar.csv", {"q": "rendimento baixo"})

        self.assertContains(detalhe, "Abaixo do esperado")
        self.assertIn("Alerta rendimento", csv_response.content.decode("utf-8-sig"))
        self.assertIn("Abaixo do esperado", csv_response.content.decode("utf-8-sig"))

    def test_relatorio_rendimento_filtra_alertas_e_exporta_csv(self):
        destino_baixo = Produto.objects.create(
            codigo_barras="7893333333323",
            nome="Corte baixo relatório",
            categoria=self.categoria,
            preco_custo="0.00",
            preco_venda="19.00",
        )
        destino_ok = Produto.objects.create(
            codigo_barras="7893333333324",
            nome="Corte ok relatório",
            categoria=self.categoria,
            preco_custo="0.00",
            preco_venda="17.00",
        )
        Estoque.objects.create(produto=self.produto, filial=self.filial, quantidade_atual=Decimal("4.000"))
        confirmar_desmembramento_multidestino(
            filial=self.filial,
            produto_origem=self.produto,
            quantidade_origem=Decimal("1.000"),
            destinos=[
                {
                    "produto": destino_baixo,
                    "quantidade": Decimal("0.700"),
                    "percentual_rendimento_esperado": Decimal("80.00"),
                    "lote": "LOTE-BAIXO",
                }
            ],
            usuario=self.user,
            motivo="Relatório abaixo",
            tipo="ACOUGUE",
        )
        confirmar_desmembramento_multidestino(
            filial=self.filial,
            produto_origem=self.produto,
            quantidade_origem=Decimal("1.000"),
            destinos=[
                {
                    "produto": destino_ok,
                    "quantidade": Decimal("0.900"),
                    "percentual_rendimento_esperado": Decimal("80.00"),
                    "lote": "LOTE-OK",
                }
            ],
            usuario=self.user,
            motivo="Relatório ok",
            tipo="ACOUGUE",
        )

        pagina = self.client.get("/estoque/desmembramentos/relatorio/", {"alerta": "abaixo"})
        csv_response = self.client.get("/estoque/desmembramentos/relatorio/exportar.csv", {"alerta": "abaixo"})

        self.assertEqual(pagina.status_code, 200)
        self.assertContains(pagina, "Relatório de rendimento")
        self.assertContains(pagina, "rendimento-chart-data")
        self.assertContains(pagina, "rendimento-destinos-chart")
        self.assertContains(pagina, "rendimento-custos-chart")
        self.assertContains(pagina, "rendimento-alertas-chart")
        self.assertContains(pagina, "Corte baixo relatório")
        self.assertContains(pagina, "Abaixo do esperado")
        self.assertNotContains(pagina, "Corte ok relatório")
        self.assertEqual(csv_response.status_code, 200)
        conteudo = csv_response.content.decode("utf-8-sig")
        self.assertIn("Diferenca %", conteudo)
        self.assertIn("Corte baixo relatório", conteudo)
        self.assertIn("Abaixo do esperado", conteudo)
        self.assertNotIn("Corte ok relatório", conteudo)

    def test_desmembramento_hortifruti_reembalado_movimenta_e_filtra_relatorio(self):
        destino = Produto.objects.create(
            codigo_barras="7893333333355",
            nome="Bandeja banana prata",
            categoria=self.categoria,
            preco_custo="0.00",
            preco_venda="7.99",
        )
        outro_destino = Produto.objects.create(
            codigo_barras="7893333333356",
            nome="Corte carne filtro",
            categoria=self.categoria,
            preco_custo="0.00",
            preco_venda="22.00",
        )
        Estoque.objects.create(produto=self.produto, filial=self.filial, quantidade_atual=Decimal("10.000"))
        desmembramento = confirmar_desmembramento_multidestino(
            filial=self.filial,
            produto_origem=self.produto,
            quantidade_origem=Decimal("5.000"),
            destinos=[
                {
                    "produto": destino,
                    "quantidade": Decimal("4.500"),
                    "percentual_rendimento_esperado": Decimal("90.00"),
                    "lote": "HORTI-001",
                    "validade": date(2026, 7, 12),
                }
            ],
            usuario=self.user,
            motivo="Reembalar hortifruti para bandejas",
            tipo=TipoDesmembramentoProduto.HORTIFRUTI,
        )
        confirmar_desmembramento_multidestino(
            filial=self.filial,
            produto_origem=self.produto,
            quantidade_origem=Decimal("1.000"),
            destinos=[{"produto": outro_destino, "quantidade": Decimal("0.800")}],
            usuario=self.user,
            motivo="Outro tipo para filtro",
            tipo=TipoDesmembramentoProduto.ACOUGUE,
        )

        item = desmembramento.itens.get()
        pagina = self.client.get(
            "/estoque/desmembramentos/relatorio/",
            {"tipo": TipoDesmembramentoProduto.HORTIFRUTI},
        )
        csv_response = self.client.get(
            "/estoque/desmembramentos/relatorio/exportar.csv",
            {"tipo": TipoDesmembramentoProduto.HORTIFRUTI},
        )

        self.assertEqual(desmembramento.get_tipo_display(), "Hortifruti reembalado")
        self.assertEqual(item.percentual_rendimento, Decimal("90.00"))
        self.assertEqual(Estoque.objects.get(produto=destino, filial=self.filial).quantidade_atual, Decimal("4.500"))
        self.assertContains(pagina, "Bandeja banana prata")
        self.assertContains(pagina, "Hortifruti reembalado")
        self.assertNotContains(pagina, "Corte carne filtro")
        conteudo = csv_response.content.decode("utf-8-sig")
        self.assertIn("Bandeja banana prata", conteudo)
        self.assertIn("Hortifruti reembalado", conteudo)
        self.assertNotIn("Corte carne filtro", conteudo)

    def test_cancelar_desmembramento_multidestino_reverte_todos_destinos(self):
        destino_a = Produto.objects.create(
            codigo_barras="7893333333311",
            nome="Destino multi A",
            categoria=self.categoria,
            preco_custo="0.00",
            preco_venda="10.00",
        )
        destino_b = Produto.objects.create(
            codigo_barras="7893333333312",
            nome="Destino multi B",
            categoria=self.categoria,
            preco_custo="0.00",
            preco_venda="11.00",
        )
        Estoque.objects.create(produto=self.produto, filial=self.filial, quantidade_atual=Decimal("3.000"))
        desmembramento = confirmar_desmembramento_multidestino(
            filial=self.filial,
            produto_origem=self.produto,
            quantidade_origem=Decimal("1.000"),
            destinos=[
                {"produto": destino_a, "quantidade": Decimal("2.000")},
                {"produto": destino_b, "quantidade": Decimal("1.000")},
            ],
            usuario=self.user,
            motivo="Multi reversivel",
        )

        cancelar_desmembramento_produto(
            desmembramento=desmembramento,
            usuario=self.user,
            motivo="Cancelar multi",
        )

        self.assertEqual(Estoque.objects.get(produto=self.produto, filial=self.filial).quantidade_atual, Decimal("3.000"))
        self.assertEqual(Estoque.objects.get(produto=destino_a, filial=self.filial).quantidade_atual, Decimal("0.000"))
        self.assertEqual(Estoque.objects.get(produto=destino_b, filial=self.filial).quantidade_atual, Decimal("0.000"))

    def test_composicao_kit_consumindo_componentes_gera_produto_final(self):
        componente_a = Produto.objects.create(
            codigo_barras="7893333333401",
            nome="Cesta componente A",
            categoria=self.categoria,
            preco_custo="2.00",
            preco_venda="3.00",
        )
        componente_b = Produto.objects.create(
            codigo_barras="7893333333402",
            nome="Cesta componente B",
            categoria=self.categoria,
            preco_custo="4.00",
            preco_venda="6.00",
        )
        produto_final = Produto.objects.create(
            codigo_barras="7893333333403",
            nome="Kit cesta pronta",
            categoria=self.categoria,
            preco_custo="0.00",
            preco_venda="15.00",
        )
        composicao = ComposicaoProduto.objects.create(
            empresa=self.empresa,
            filial=self.filial,
            produto_final=produto_final,
            quantidade_final=Decimal("1.000"),
            tipo=TipoDesmembramentoProduto.KIT,
        )
        ItemComposicaoProduto.objects.create(composicao=composicao, produto_componente=componente_a, quantidade=Decimal("2.000"))
        ItemComposicaoProduto.objects.create(composicao=composicao, produto_componente=componente_b, quantidade=Decimal("1.000"))
        Estoque.objects.create(produto=componente_a, filial=self.filial, quantidade_atual=Decimal("10.000"))
        Estoque.objects.create(produto=componente_b, filial=self.filial, quantidade_atual=Decimal("5.000"))

        producao = confirmar_producao_composicao(
            composicao=composicao,
            filial=self.filial,
            quantidade_final=Decimal("2.000"),
            usuario=self.user,
            motivo="Montar kits promocionais",
        )

        self.assertEqual(ProducaoComposicaoProduto.objects.count(), 1)
        self.assertEqual(producao.quantidade_final, Decimal("2.000"))
        self.assertEqual(producao.custo_total, Decimal("16.000000"))
        self.assertEqual(producao.itens.count(), 2)
        self.assertEqual(Estoque.objects.get(produto=componente_a, filial=self.filial).quantidade_atual, Decimal("6.000"))
        self.assertEqual(Estoque.objects.get(produto=componente_b, filial=self.filial).quantidade_atual, Decimal("3.000"))
        self.assertEqual(Estoque.objects.get(produto=produto_final, filial=self.filial).quantidade_atual, Decimal("2.000"))
        self.assertEqual(MovimentacaoEstoque.objects.filter(referencia__startswith=f"composicao:{producao.id}:").count(), 3)
        self.assertTrue(LogAuditoria.objects.filter(acao="PRODUCAO_COMPOSICAO", objeto_id=str(producao.id)).exists())

    def test_composicao_bloqueia_estoque_insuficiente_de_componente(self):
        componente = Produto.objects.create(
            codigo_barras="7893333333404",
            nome="Componente sem saldo",
            categoria=self.categoria,
            preco_custo="2.00",
            preco_venda="3.00",
        )
        produto_final = Produto.objects.create(
            codigo_barras="7893333333405",
            nome="Kit sem saldo",
            categoria=self.categoria,
            preco_custo="0.00",
            preco_venda="15.00",
        )
        composicao = ComposicaoProduto.objects.create(
            empresa=self.empresa,
            filial=self.filial,
            produto_final=produto_final,
            quantidade_final=Decimal("1.000"),
        )
        ItemComposicaoProduto.objects.create(composicao=composicao, produto_componente=componente, quantidade=Decimal("3.000"))
        Estoque.objects.create(produto=componente, filial=self.filial, quantidade_atual=Decimal("0.000"))

        with self.assertRaises(ValidationError):
            confirmar_producao_composicao(
                composicao=composicao,
                filial=self.filial,
                quantidade_final=Decimal("1.000"),
                usuario=self.user,
                motivo="Sem saldo",
            )

        self.assertEqual(ProducaoComposicaoProduto.objects.count(), 0)
        self.assertFalse(Estoque.objects.filter(produto=produto_final, filial=self.filial).exists())

    def test_cancelar_composicao_reverte_produto_final_e_componentes(self):
        componente = Produto.objects.create(
            codigo_barras="7893333333406",
            nome="Componente reversivel",
            categoria=self.categoria,
            preco_custo="5.00",
            preco_venda="8.00",
        )
        produto_final = Produto.objects.create(
            codigo_barras="7893333333407",
            nome="Kit reversivel",
            categoria=self.categoria,
            preco_custo="0.00",
            preco_venda="15.00",
        )
        composicao = ComposicaoProduto.objects.create(
            empresa=self.empresa,
            filial=self.filial,
            produto_final=produto_final,
            quantidade_final=Decimal("1.000"),
        )
        ItemComposicaoProduto.objects.create(composicao=composicao, produto_componente=componente, quantidade=Decimal("2.000"))
        Estoque.objects.create(produto=componente, filial=self.filial, quantidade_atual=Decimal("4.000"))
        producao = confirmar_producao_composicao(
            composicao=composicao,
            filial=self.filial,
            quantidade_final=Decimal("1.000"),
            usuario=self.user,
            motivo="Montar kit",
        )

        cancelada = cancelar_producao_composicao(
            producao=producao,
            usuario=self.user,
            motivo="Desfazer kit",
        )

        self.assertEqual(cancelada.status, StatusProducaoComposicao.CANCELADO)
        self.assertEqual(Estoque.objects.get(produto=componente, filial=self.filial).quantidade_atual, Decimal("4.000"))
        self.assertEqual(Estoque.objects.get(produto=produto_final, filial=self.filial).quantidade_atual, Decimal("0.000"))
        self.assertTrue(LogAuditoria.objects.filter(acao="CANCELAMENTO_COMPOSICAO", objeto_id=str(producao.id)).exists())

    def test_telas_de_composicao_criam_produzem_e_cancelam_kit(self):
        componente = Produto.objects.create(
            codigo_barras="7893333333408",
            nome="Componente tela",
            categoria=self.categoria,
            preco_custo="2.00",
            preco_venda="3.00",
        )
        produto_final = Produto.objects.create(
            codigo_barras="7893333333409",
            nome="Kit tela",
            categoria=self.categoria,
            preco_custo="0.00",
            preco_venda="12.00",
        )
        Estoque.objects.create(produto=componente, filial=self.filial, quantidade_atual=Decimal("5.000"))

        lista = self.client.get("/estoque/composicoes/")
        form = self.client.get("/estoque/composicoes/nova/")
        self.assertContains(lista, "Composições")
        self.assertContains(form, "Nova composição")
        self.assertContains(form, "componentes-0-produto_componente")

        response = self.client.post(
            "/estoque/composicoes/nova/",
            {
                "empresa": self.empresa.id,
                "filial": self.filial.id,
                "produto_final": produto_final.id,
                "quantidade_final": "1.000",
                "tipo": TipoDesmembramentoProduto.KIT,
                "observacao": "Kit pela tela",
                "is_active": "on",
                "componentes-TOTAL_FORMS": "1",
                "componentes-INITIAL_FORMS": "0",
                "componentes-MIN_NUM_FORMS": "1",
                "componentes-MAX_NUM_FORMS": "1000",
                "componentes-0-produto_componente": componente.id,
                "componentes-0-quantidade": "2.000",
            },
            follow=True,
        )
        self.assertContains(response, "Composicao salva com sucesso")
        self.assertContains(response, "Visão operacional")
        self.assertContains(response, "Custo previsto")
        self.assertContains(response, "Capacidade atual")
        self.assertContains(response, "Componente tela")
        composicao = ComposicaoProduto.objects.get(produto_final=produto_final)
        self.assertEqual(composicao.itens.count(), 1)

        response = self.client.post(
            f"/estoque/composicoes/{composicao.id}/produzir/",
            {
                "filial": self.filial.id,
                "quantidade_final": "1.000",
                "motivo": "Produzir pela tela",
                "observacao": "",
                "supervisor_usuario": "admin",
                "supervisor_senha": "123",
            },
            follow=True,
        )
        self.assertContains(response, "produzida e estoque atualizado")
        producao = ProducaoComposicaoProduto.objects.get(composicao=composicao)
        self.assertEqual(Estoque.objects.get(produto=componente, filial=self.filial).quantidade_atual, Decimal("3.000"))
        self.assertEqual(Estoque.objects.get(produto=produto_final, filial=self.filial).quantidade_atual, Decimal("1.000"))

        response = self.client.post(
            f"/estoque/composicoes/producoes/{producao.id}/cancelar/",
            {
                "motivo": "Cancelar pela tela",
                "supervisor_usuario": "admin",
                "supervisor_senha": "123",
            },
            follow=True,
        )
        self.assertContains(response, "Producao cancelada e estoque revertido")
        producao.refresh_from_db()
        self.assertEqual(producao.status, StatusProducaoComposicao.CANCELADO)
        self.assertEqual(Estoque.objects.get(produto=componente, filial=self.filial).quantidade_atual, Decimal("5.000"))

    def test_lista_de_composicoes_exibe_alerta_de_insumo_baixo(self):
        componente = Produto.objects.create(
            codigo_barras="7893333333410",
            nome="Componente baixo",
            categoria=self.categoria,
            preco_custo="2.00",
            preco_venda="3.00",
        )
        produto_final = Produto.objects.create(
            codigo_barras="7893333333411",
            nome="Kit com alerta",
            categoria=self.categoria,
            preco_custo="0.00",
            preco_venda="12.00",
        )
        Estoque.objects.create(produto=componente, filial=self.filial, quantidade_atual=Decimal("1.000"))
        composicao = ComposicaoProduto.objects.create(
            empresa=self.empresa,
            filial=self.filial,
            produto_final=produto_final,
            quantidade_final=Decimal("1.000"),
            tipo=TipoDesmembramentoProduto.KIT,
        )
        ItemComposicaoProduto.objects.create(
            composicao=composicao,
            produto_componente=componente,
            quantidade=Decimal("2.000"),
        )

        response = self.client.get("/estoque/composicoes/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alertas")
        self.assertContains(response, "Insumo baixo")
        self.assertContains(response, "Kit com alerta")
        self.assertContains(response, "<strong>0,500</strong>", html=True)
        self.assertContains(response, "Produzir capacidade")

        detalhe = self.client.get(f"/estoque/composicoes/{composicao.pk}/", {"quantidade": "0.500"})

        self.assertContains(detalhe, 'value="0.500"')

    def test_lista_de_composicoes_sugere_producao_por_demanda_minima(self):
        componente = Produto.objects.create(
            codigo_barras="7893333333412",
            nome="Componente demanda",
            categoria=self.categoria,
            preco_custo="2.00",
            preco_venda="3.00",
        )
        produto_final = Produto.objects.create(
            codigo_barras="7893333333413",
            nome="Kit demanda",
            categoria=self.categoria,
            preco_custo="0.00",
            preco_venda="12.00",
            estoque_minimo=Decimal("5.000"),
        )
        Estoque.objects.create(produto=componente, filial=self.filial, quantidade_atual=Decimal("6.000"))
        Estoque.objects.create(produto=produto_final, filial=self.filial, quantidade_atual=Decimal("1.000"))
        composicao = ComposicaoProduto.objects.create(
            empresa=self.empresa,
            filial=self.filial,
            produto_final=produto_final,
            quantidade_final=Decimal("1.000"),
            tipo=TipoDesmembramentoProduto.KIT,
        )
        ItemComposicaoProduto.objects.create(
            composicao=composicao,
            produto_componente=componente,
            quantidade=Decimal("2.000"),
        )

        response = self.client.get("/estoque/composicoes/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Demanda mínima")
        self.assertContains(response, "Produção sugerida")
        self.assertContains(response, "Kit demanda")
        self.assertContains(response, "Produzir")
        self.assertContains(response, "<strong>3</strong>", html=True)
        self.assertContains(response, "?quantidade=3.000")
        self.assertContains(response, "Produzir sugestão")
        self.assertContains(response, "Programar sugest")

        detalhe = self.client.get(f"/estoque/composicoes/{composicao.pk}/", {"quantidade": "3.000"})

        self.assertContains(detalhe, 'value="3.000"')
        self.assertContains(detalhe, "Reposição até estoque mínimo")
        self.assertContains(detalhe, "Demanda de reposição")

        data_programada = timezone.localdate() + timedelta(days=1)
        programacao = self.client.post(
            "/estoque/composicoes/programar-sugestoes/",
            {"data_programada": data_programada.isoformat()},
            follow=True,
        )

        self.assertContains(programacao, "ordem(ns) de produção programada(s) por demanda")
        ordem = OrdemProducaoComposicao.objects.get(composicao=composicao)
        self.assertEqual(ordem.quantidade_planejada, Decimal("3.000"))
        self.assertEqual(ordem.data_programada, data_programada)
        self.assertEqual(ordem.status, StatusOrdemProducaoComposicao.PLANEJADA)
        self.assertEqual(ordem.motivo, "Reposicao automática ate estoque mínimo")
        self.assertTrue(
            LogAuditoria.objects.filter(
                acao="ORDEM_PRODUCAO_COMPOSICAO_SUGERIDA",
                objeto_id=str(ordem.id),
            ).exists()
        )

        repetir = self.client.post(
            "/estoque/composicoes/programar-sugestoes/",
            {"data_programada": data_programada.isoformat()},
            follow=True,
        )

        self.assertContains(repetir, "ja tinham ordem planejada")
        self.assertEqual(OrdemProducaoComposicao.objects.filter(composicao=composicao).count(), 1)

    def test_exportacao_csv_de_composicoes_respeita_busca_e_planejamento(self):
        componente = Produto.objects.create(
            codigo_barras="7893333333414",
            nome="Componente CSV",
            categoria=self.categoria,
            preco_custo="2.00",
            preco_venda="3.00",
        )
        produto_final = Produto.objects.create(
            codigo_barras="7893333333415",
            nome="Kit CSV planejamento",
            categoria=self.categoria,
            preco_custo="0.00",
            preco_venda="12.00",
            estoque_minimo=Decimal("5.000"),
        )
        fora = Produto.objects.create(
            codigo_barras="7893333333416",
            nome="Kit fora CSV",
            categoria=self.categoria,
            preco_custo="0.00",
            preco_venda="9.00",
        )
        Estoque.objects.create(produto=componente, filial=self.filial, quantidade_atual=Decimal("6.000"))
        Estoque.objects.create(produto=produto_final, filial=self.filial, quantidade_atual=Decimal("1.000"))
        composicao = ComposicaoProduto.objects.create(
            empresa=self.empresa,
            filial=self.filial,
            produto_final=produto_final,
            quantidade_final=Decimal("1.000"),
            tipo=TipoDesmembramentoProduto.KIT,
        )
        ItemComposicaoProduto.objects.create(composicao=composicao, produto_componente=componente, quantidade=Decimal("2.000"))
        ComposicaoProduto.objects.create(
            empresa=self.empresa,
            filial=self.filial,
            produto_final=fora,
            quantidade_final=Decimal("1.000"),
            tipo=TipoDesmembramentoProduto.KIT,
        )

        lista = self.client.get("/estoque/composicoes/", {"q": "planejamento"})
        csv_response = self.client.get("/estoque/composicoes/exportar.csv", {"q": "planejamento"})

        self.assertContains(lista, "Excel/CSV")
        self.assertEqual(csv_response.status_code, 200)
        conteudo = csv_response.content.decode("utf-8-sig")
        self.assertIn("Producao sugerida", conteudo)
        self.assertIn("Demanda reposicao", conteudo)
        self.assertIn("Kit CSV planejamento", conteudo)
        self.assertIn("Produzir", conteudo)
        self.assertNotIn("Kit fora CSV", conteudo)

    def test_relatorio_de_producoes_de_composicao_filtra_e_exporta_csv(self):
        componente = Produto.objects.create(
            codigo_barras="7893333333417",
            nome="Componente produção relatório",
            categoria=self.categoria,
            preco_custo="2.00",
            preco_venda="3.00",
        )
        produto_final = Produto.objects.create(
            codigo_barras="7893333333418",
            nome="Kit produção relatório",
            categoria=self.categoria,
            preco_custo="0.00",
            preco_venda="12.00",
        )
        outro_final = Produto.objects.create(
            codigo_barras="7893333333419",
            nome="Kit fora relatório produção",
            categoria=self.categoria,
            preco_custo="0.00",
            preco_venda="10.00",
        )
        Estoque.objects.create(produto=componente, filial=self.filial, quantidade_atual=Decimal("8.000"))
        composicao = ComposicaoProduto.objects.create(
            empresa=self.empresa,
            filial=self.filial,
            produto_final=produto_final,
            quantidade_final=Decimal("1.000"),
            tipo=TipoDesmembramentoProduto.KIT,
        )
        outra_composicao = ComposicaoProduto.objects.create(
            empresa=self.empresa,
            filial=self.filial,
            produto_final=outro_final,
            quantidade_final=Decimal("1.000"),
            tipo=TipoDesmembramentoProduto.KIT,
        )
        ItemComposicaoProduto.objects.create(composicao=composicao, produto_componente=componente, quantidade=Decimal("2.000"))
        ItemComposicaoProduto.objects.create(composicao=outra_composicao, produto_componente=componente, quantidade=Decimal("1.000"))
        confirmar_producao_composicao(
            composicao=composicao,
            filial=self.filial,
            quantidade_final=Decimal("2.000"),
            usuario=self.user,
            motivo="Produção relatório alvo",
        )
        confirmar_producao_composicao(
            composicao=outra_composicao,
            filial=self.filial,
            quantidade_final=Decimal("1.000"),
            usuario=self.user,
            motivo="Produção fora",
        )

        ordem = OrdemProducaoComposicao.objects.create(
            composicao=composicao,
            empresa=self.empresa,
            filial=self.filial,
            produto_final=produto_final,
            quantidade_planejada=Decimal("2.000"),
            data_programada=timezone.localdate(),
            setor_responsavel="Padaria",
            etapa_operacional="CONFERENCIA",
            status=StatusOrdemProducaoComposicao.PRODUZIDA,
            usuario=self.user,
            motivo="Producao relatório alvo",
            concluido_em=timezone.now(),
        )
        historico_separacao = HistoricoEtapaOrdemProducaoComposicao.objects.create(
            ordem=ordem,
            etapa_anterior="SEPARACAO",
            etapa_nova="PRODUCAO",
            usuario=self.user,
        )
        historico_producao = HistoricoEtapaOrdemProducaoComposicao.objects.create(
            ordem=ordem,
            etapa_anterior="PRODUCAO",
            etapa_nova="CONFERENCIA",
            usuario=self.user,
        )
        inicio = timezone.now() - timedelta(minutes=105)
        OrdemProducaoComposicao.objects.filter(pk=ordem.pk).update(
            criado_em=inicio,
            concluido_em=inicio + timedelta(minutes=105),
        )
        HistoricoEtapaOrdemProducaoComposicao.objects.filter(pk=historico_separacao.pk).update(
            criado_em=inicio + timedelta(minutes=45)
        )
        HistoricoEtapaOrdemProducaoComposicao.objects.filter(pk=historico_producao.pk).update(
            criado_em=inicio + timedelta(minutes=75)
        )
        ConfiguracaoSLASetorProducao.objects.create(
            empresa=self.empresa,
            filial=self.filial,
            setor="Padaria",
            meta_minutos=60,
        )

        pagina = self.client.get("/estoque/composicoes/producoes/relatorio/", {"q": "alvo"})
        csv_response = self.client.get("/estoque/composicoes/producoes/relatorio/exportar.csv", {"q": "alvo"})

        self.assertEqual(pagina.status_code, 200)
        self.assertContains(pagina, "Relatório de produções")
        self.assertContains(pagina, "producao-chart-data")
        self.assertContains(pagina, "Duracao por etapa das ordens")
        self.assertContains(pagina, "SLA por setor")
        self.assertContains(pagina, "Fora da meta")
        self.assertContains(pagina, "45 min")
        self.assertContains(pagina, f"Ordem #{ordem.id}")
        self.assertContains(pagina, "Kit produção relatório")
        self.assertContains(pagina, "Produção relatório alvo")
        self.assertNotContains(pagina, "Kit fora relatório produção")
        self.assertEqual(csv_response.status_code, 200)
        conteudo = csv_response.content.decode("utf-8-sig")
        self.assertIn("Componentes consumidos", conteudo)
        self.assertIn("Resumo de duracao por etapa das ordens", conteudo)
        self.assertIn("Resumo de SLA por setor", conteudo)
        self.assertIn("Fora da meta", conteudo)
        self.assertIn("1h 00min", conteudo)
        self.assertIn("Ordem critica", conteudo)
        self.assertIn(f"Ordem #{ordem.id}", conteudo)
        self.assertIn("Kit produção relatório", conteudo)
        self.assertIn("Componente produção relatório: 4.000", conteudo)
        self.assertNotIn("Kit fora relatório produção", conteudo)

    def test_configuracao_sla_setor_producao_cadastra_e_lista(self):
        response = self.client.post(
            "/estoque/composicoes/slas-setor/nova/",
            {
                "empresa": self.empresa.id,
                "filial": self.filial.id,
                "setor": "Padaria",
                "meta_minutos": 75,
                "observacao": "Meta para produção diaria",
                "is_active": "on",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Padaria")
        configuracao = ConfiguracaoSLASetorProducao.objects.get(setor="Padaria")
        self.assertEqual(configuracao.meta_minutos, 75)

        lista = self.client.get("/estoque/composicoes/slas-setor/", {"q": "Padaria"})
        self.assertContains(lista, "SLAs de produção por setor")
        self.assertContains(lista, "75 min")
        self.assertContains(lista, self.filial.nome)

        editar = self.client.post(
            f"/estoque/composicoes/slas-setor/{configuracao.id}/editar/",
            {
                "empresa": self.empresa.id,
                "filial": "",
                "setor": "Padaria",
                "meta_minutos": 90,
                "observacao": "Meta geral",
                "is_active": "on",
            },
            follow=True,
        )
        self.assertContains(editar, "90 min")
        configuracao.refresh_from_db()
        self.assertIsNone(configuracao.filial)

    def test_ordem_de_producao_de_composicao_programa_e_confirma_estoque(self):
        componente = Produto.objects.create(
            codigo_barras="7893333333420",
            nome="Componente ordem",
            categoria=self.categoria,
            preco_custo="2.00",
            preco_venda="3.00",
        )
        produto_final = Produto.objects.create(
            codigo_barras="7893333333421",
            nome="Kit ordem",
            categoria=self.categoria,
            preco_custo="0.00",
            preco_venda="12.00",
        )
        Estoque.objects.create(produto=componente, filial=self.filial, quantidade_atual=Decimal("8.000"))
        composicao = ComposicaoProduto.objects.create(
            empresa=self.empresa,
            filial=self.filial,
            produto_final=produto_final,
            quantidade_final=Decimal("1.000"),
            tipo=TipoDesmembramentoProduto.KIT,
        )
        ItemComposicaoProduto.objects.create(composicao=composicao, produto_componente=componente, quantidade=Decimal("2.000"))
        data_programada = timezone.localdate() + timedelta(days=1)
        responsavel = get_user_model().objects.create_user(username="operador_producao", password="123")

        response = self.client.post(
            "/estoque/composicoes/ordens/nova/",
            {
                "composicao": composicao.id,
                "filial": self.filial.id,
                "quantidade_planejada": "2.000",
                "data_programada": data_programada.isoformat(),
                "prioridade": "URGENTE",
                "setor_responsavel": "Padaria",
                "etapa_operacional": "SEPARACAO",
                "responsavel_operacional": responsavel.id,
                "motivo": "Programar kits para fim de semana",
                "observacao": "",
            },
            follow=True,
        )

        self.assertContains(response, "Ordem de produção criada com sucesso")
        ordem = OrdemProducaoComposicao.objects.get()
        self.assertEqual(ordem.status, StatusOrdemProducaoComposicao.PLANEJADA)
        self.assertContains(response, "Excel/CSV")
        self.assertContains(response, "Kit ordem")
        self.assertContains(response, "Programar kits para fim de semana")
        self.assertContains(response, f"/estoque/composicoes/ordens/{ordem.id}/imprimir/")
        self.assertContains(response, "Próximas ordens")
        self.assertContains(response, f"inicio={data_programada.isoformat()}")
        self.assertContains(response, "Urgente")
        self.assertContains(response, "Urgentes")
        self.assertContains(response, "Padaria")
        self.assertContains(response, "setor=Padaria")
        self.assertContains(response, "operador_producao")
        self.assertContains(response, "Separação")

        etapa_response = self.client.post(
            f"/estoque/composicoes/ordens/{ordem.id}/etapa/",
            {"etapa_operacional": "PRODUCAO"},
            follow=True,
        )
        self.assertContains(etapa_response, "Etapa da ordem atualizada")
        ordem.refresh_from_db()
        self.assertEqual(ordem.etapa_operacional, "PRODUCAO")
        historico = HistoricoEtapaOrdemProducaoComposicao.objects.get(ordem=ordem)
        self.assertEqual(historico.etapa_anterior, "SEPARACAO")
        self.assertEqual(historico.etapa_nova, "PRODUCAO")
        self.assertTrue(LogAuditoria.objects.filter(acao="ORDEM_PRODUCAO_COMPOSICAO_ETAPA", objeto_id=str(ordem.id)).exists())

        lista_com_apontamento = self.client.get("/estoque/composicoes/ordens/", {"etapa": "PRODUCAO"})
        self.assertContains(lista_com_apontamento, "por admin")
        self.assertContains(lista_com_apontamento, "Tempo na etapa")

        impressao = self.client.get(f"/estoque/composicoes/ordens/{ordem.id}/imprimir/")
        self.assertEqual(impressao.status_code, 200)
        self.assertContains(impressao, f"Ordem de produção #{ordem.id}")
        self.assertContains(impressao, "Componentes previstos")
        self.assertContains(impressao, "Componente ordem")
        self.assertContains(impressao, "4")
        self.assertContains(impressao, "Urgente")
        self.assertContains(impressao, "Padaria")
        self.assertContains(impressao, "Produção")
        self.assertContains(impressao, "operador_producao")

        csv_response = self.client.get("/estoque/composicoes/ordens/exportar.csv", {"q": "fim de semana"})
        self.assertEqual(csv_response.status_code, 200)
        conteudo = csv_response.content.decode("utf-8-sig")
        self.assertIn("Data programada", conteudo)
        self.assertIn("Kit ordem", conteudo)
        self.assertIn("Urgente", conteudo)
        self.assertIn("Padaria", conteudo)
        self.assertIn("Produção", conteudo)
        self.assertIn("operador_producao", conteudo)
        self.assertIn("Planejada", conteudo)
        self.assertIn("Status SLA", conteudo)
        self.assertIn("Meta SLA", conteudo)
        self.assertIn("Programar kits para fim de semana", conteudo)

        filtro_setor = self.client.get("/estoque/composicoes/ordens/", {"setor": "Padaria"})
        self.assertContains(filtro_setor, "Kit ordem")

        filtro_etapa = self.client.get("/estoque/composicoes/ordens/", {"etapa": "PRODUCAO"})
        self.assertContains(filtro_etapa, "Kit ordem")

        filtro_responsavel = self.client.get("/estoque/composicoes/ordens/", {"responsavel": responsavel.id})
        self.assertContains(filtro_responsavel, "Kit ordem")

        ordem_hoje = OrdemProducaoComposicao.objects.create(
            composicao=composicao,
            empresa=self.empresa,
            filial=self.filial,
            produto_final=produto_final,
            quantidade_planejada=Decimal("1.000"),
            data_programada=timezone.localdate(),
            prioridade="ALTA",
            setor_responsavel="Padaria",
            etapa_operacional="SEPARACAO",
            responsavel_operacional=responsavel,
            usuario=self.user,
            motivo="Fila do dia",
        )
        ConfiguracaoSLASetorProducao.objects.update_or_create(
            empresa=self.empresa,
            filial=self.filial,
            setor="Padaria",
            defaults={"meta_minutos": 1, "is_active": True},
        )
        OrdemProducaoComposicao.objects.filter(pk=ordem_hoje.pk).update(
            criado_em=timezone.now() - timedelta(minutes=15)
        )
        gerente = get_user_model().objects.create_user(username="gerente_producao", password="123")
        PerfilUsuario.objects.create(usuario=gerente, filial=self.filial, tipo=TipoPerfil.GERENTE)
        fila_dia = self.client.get("/estoque/composicoes/ordens/fila/")
        fila_todas = self.client.get("/estoque/composicoes/ordens/fila/", {"modo": "todas"})
        self.assertContains(fila_dia, "Fila de produção")
        self.assertContains(fila_dia, "Padaria")
        self.assertContains(fila_dia, "Fila do dia")
        self.assertContains(fila_dia, "operador_producao")
        self.assertContains(fila_dia, "Fora do SLA")
        self.assertContains(fila_dia, "Meta SLA")
        self.assertContains(fila_dia, "Alertas de SLA enviados")
        self.assertContains(fila_dia, "gerente_producao")
        self.assertNotContains(fila_dia, "Programar kits para fim de semana")
        self.assertEqual(AlertaSLAOrdemProducao.objects.filter(ordem=ordem_hoje).count(), 2)
        self.client.get("/estoque/composicoes/ordens/fila/")
        self.assertEqual(AlertaSLAOrdemProducao.objects.filter(ordem=ordem_hoje).count(), 2)
        self.assertTrue(LogAuditoria.objects.filter(acao="ALERTA_SLA_ORDEM_PRODUCAO", objeto_id=str(ordem_hoje.id)).exists())
        alerta_gerente = AlertaSLAOrdemProducao.objects.get(ordem=ordem_hoje, usuario=gerente)
        self.client.force_login(gerente)
        central_alertas = self.client.get("/estoque/composicoes/alertas-sla/")
        self.assertContains(central_alertas, "Alertas de SLA")
        self.assertContains(central_alertas, "Somente abertos")
        self.assertContains(central_alertas, f"Ordem #{ordem_hoje.id}")
        self.assertContains(central_alertas, "Marcar visto")
        visualizar_alerta = self.client.post(
            f"/estoque/composicoes/alertas-sla/{alerta_gerente.id}/visualizar/",
            follow=True,
        )
        self.assertContains(visualizar_alerta, "Alerta marcado como visualizado")
        alerta_gerente.refresh_from_db()
        self.assertIsNotNone(alerta_gerente.visualizado_em)
        self.assertTrue(
            LogAuditoria.objects.filter(
                acao="VISUALIZAR_ALERTA_SLA_ORDEM_PRODUCAO",
                objeto_id=str(alerta_gerente.id),
            ).exists()
        )
        self.client.force_login(self.user)
        fila_sla = self.client.get("/estoque/composicoes/ordens/fila/", {"modo": "todas", "sla": "fora"})
        self.assertContains(fila_sla, "Somente fora do SLA")
        self.assertContains(fila_sla, "Fila do dia")
        self.assertNotContains(fila_sla, "Programar kits para fim de semana")
        self.assertContains(fila_todas, "Programar kits para fim de semana")
        self.assertContains(fila_todas, f"/estoque/composicoes/ordens/{ordem_hoje.id}/imprimir/")

        fila_responsavel = self.client.get("/estoque/composicoes/ordens/fila/", {"modo": "todas", "responsavel": responsavel.id})
        self.assertContains(fila_responsavel, "operador_producao")
        self.assertContains(fila_responsavel, "por admin")
        self.assertContains(fila_responsavel, "Tempo na etapa")
        self.assertContains(fila_responsavel, "Maior tempo parado")
        self.assertContains(fila_responsavel, "Maior tempo")
        self.assertContains(fila_responsavel, "Gargalos por respons")
        self.assertContains(fila_responsavel, f"Ordem #{ordem_hoje.id}")

        response = self.client.post(
            f"/estoque/composicoes/ordens/{ordem.id}/confirmar/",
            {"supervisor_usuario": "admin", "supervisor_senha": "123"},
            follow=True,
        )

        self.assertContains(response, "Ordem produzida e estoque atualizado")
        ordem.refresh_from_db()
        self.assertEqual(ordem.status, StatusOrdemProducaoComposicao.PRODUZIDA)
        self.assertIsNotNone(ordem.producao_gerada)
        self.assertEqual(Estoque.objects.get(produto=componente, filial=self.filial).quantidade_atual, Decimal("4.000"))
        self.assertEqual(Estoque.objects.get(produto=produto_final, filial=self.filial).quantidade_atual, Decimal("2.000"))

    def test_desmembramento_nao_permite_estoque_insuficiente(self):
        destino = Produto.objects.create(
            codigo_barras="7894444444444",
            nome="Destino sem saldo",
            categoria=self.categoria,
            preco_custo="0.00",
            preco_venda="1.00",
        )
        Estoque.objects.create(produto=self.produto, filial=self.filial, quantidade_atual=Decimal("0.500"))

        with self.assertRaises(ValidationError):
            confirmar_desmembramento_simples(
                filial=self.filial,
                produto_origem=self.produto,
                quantidade_origem=Decimal("1.000"),
                produto_destino=destino,
                quantidade_destino=Decimal("10.000"),
                usuario=self.user,
                motivo="Tentativa inválida",
            )

        self.assertEqual(DesmembramentoProduto.objects.count(), 0)
        self.assertEqual(Estoque.objects.get(produto=self.produto, filial=self.filial).quantidade_atual, Decimal("0.500"))

    def test_simular_desmembramento_nao_grava_movimentacao(self):
        destino = Produto.objects.create(
            codigo_barras="7894545454545",
            nome="Destino simulacao",
            categoria=self.categoria,
            preco_custo="0.00",
            preco_venda="1.00",
        )
        Estoque.objects.create(produto=self.produto, filial=self.filial, quantidade_atual=Decimal("2.000"))

        previa = simular_desmembramento_simples(
            filial=self.filial,
            produto_origem=self.produto,
            quantidade_origem=Decimal("1.000"),
            produto_destino=destino,
            quantidade_destino=Decimal("30.000"),
            motivo="Simular custo",
        )

        self.assertTrue(previa["estoque_suficiente"])
        self.assertEqual(previa["saldo_origem_apos"], Decimal("1.000"))
        self.assertEqual(previa["custo_unitario_destino"], Decimal("0.10"))
        self.assertFalse(previa["conservacao_massa_aplicada"])
        self.assertEqual(DesmembramentoProduto.objects.count(), 0)
        self.assertEqual(MovimentacaoEstoque.objects.count(), 0)

    def test_desmembramento_acougue_em_kg_bloqueia_destinos_acima_da_origem(self):
        self.produto.unidade = UnidadeMedida.QUILO
        self.produto.save(update_fields=["unidade"])
        destino_a = Produto.objects.create(
            codigo_barras="7894545454501",
            nome="Corte bovino A",
            categoria=self.categoria,
            unidade=UnidadeMedida.QUILO,
            preco_custo="0.00",
            preco_venda="20.00",
        )
        destino_b = Produto.objects.create(
            codigo_barras="7894545454502",
            nome="Corte bovino B",
            categoria=self.categoria,
            unidade=UnidadeMedida.QUILO,
            preco_custo="0.00",
            preco_venda="15.00",
        )
        Estoque.objects.create(produto=self.produto, filial=self.filial, quantidade_atual=Decimal("10.000"))
        destinos = [
            {"produto": destino_a, "quantidade": Decimal("3.500")},
            {"produto": destino_b, "quantidade": Decimal("1.501")},
        ]

        previa = simular_desmembramento_multidestino(
            filial=self.filial,
            produto_origem=self.produto,
            quantidade_origem=Decimal("5.000"),
            destinos=destinos,
            tipo=TipoDesmembramentoProduto.ACOUGUE,
        )

        self.assertTrue(previa["conservacao_massa_aplicada"])
        self.assertFalse(previa["conservacao_massa_valida"])
        self.assertEqual(previa["excesso_quantidade"], Decimal("0.001"))
        self.assertEqual(previa["rendimento_total"], Decimal("100.02"))
        with self.assertRaisesMessage(ValidationError, "Conservacao de massa inválida"):
            confirmar_desmembramento_multidestino(
                filial=self.filial,
                produto_origem=self.produto,
                quantidade_origem=Decimal("5.000"),
                destinos=destinos,
                usuario=self.user,
                motivo="Teste de massa",
                tipo=TipoDesmembramentoProduto.ACOUGUE,
            )

        self.assertEqual(DesmembramentoProduto.objects.count(), 0)
        self.assertEqual(MovimentacaoEstoque.objects.count(), 0)
        self.assertEqual(
            Estoque.objects.get(produto=self.produto, filial=self.filial).quantidade_atual,
            Decimal("10.000"),
        )

    def test_desmembramento_em_kg_exige_classificar_diferenca_como_perda(self):
        self.produto.unidade = UnidadeMedida.QUILO
        self.produto.save(update_fields=["unidade"])
        destino = Produto.objects.create(
            codigo_barras="7894545454503",
            nome="Corte aproveitavel",
            categoria=self.categoria,
            unidade=UnidadeMedida.QUILO,
            preco_custo="0.00",
            preco_venda="25.00",
        )
        descarte = Produto.objects.create(
            codigo_barras="7894545454504",
            nome="Apara para descarte",
            categoria=self.categoria,
            unidade=UnidadeMedida.QUILO,
            preco_custo="0.00",
            preco_venda="0.00",
        )
        Estoque.objects.create(produto=self.produto, filial=self.filial, quantidade_atual=Decimal("10.000"))
        destino_vendavel = {"produto": destino, "quantidade": Decimal("4.500")}

        previa = simular_desmembramento_multidestino(
            filial=self.filial,
            produto_origem=self.produto,
            quantidade_origem=Decimal("5.000"),
            destinos=[destino_vendavel],
            tipo=TipoDesmembramentoProduto.HORTIFRUTI,
        )

        self.assertFalse(previa["conservacao_massa_valida"])
        self.assertEqual(previa["quantidade_nao_classificada"], Decimal("0.500"))
        with self.assertRaisesMessage(ValidationError, "Quantidade não classificada: 0.500 KG"):
            confirmar_desmembramento_multidestino(
                filial=self.filial,
                produto_origem=self.produto,
                quantidade_origem=Decimal("5.000"),
                destinos=[destino_vendavel],
                usuario=self.user,
                motivo="Teste sem perda classificada",
                tipo=TipoDesmembramentoProduto.HORTIFRUTI,
            )

        desmembramento = confirmar_desmembramento_multidestino(
            filial=self.filial,
            produto_origem=self.produto,
            quantidade_origem=Decimal("5.000"),
            destinos=[
                destino_vendavel,
                {
                    "produto": descarte,
                    "quantidade": Decimal("0.500"),
                    "tipo_saida": TipoSaidaDesmembramento.PERDA,
                },
            ],
            usuario=self.user,
            motivo="Teste com perda classificada",
            tipo=TipoDesmembramentoProduto.HORTIFRUTI,
        )

        self.assertEqual(desmembramento.itens.count(), 2)
        self.assertEqual(desmembramento.itens.filter(tipo_saida=TipoSaidaDesmembramento.PERDA).count(), 1)
        self.assertEqual(PerdaEstoque.objects.filter(desmembramento_item__desmembramento=desmembramento).count(), 1)
        self.assertEqual(Estoque.objects.get(produto=destino, filial=self.filial).quantidade_atual, Decimal("4.500"))
        self.assertFalse(Estoque.objects.filter(produto=descarte, filial=self.filial).exists())
        self.assertEqual(Estoque.objects.get(produto=self.produto, filial=self.filial).quantidade_atual, Decimal("5.000"))

    def test_cancelar_desmembramento_reverte_saldos_e_audita(self):
        destino = Produto.objects.create(
            codigo_barras="7895555555555",
            nome="Destino cancelavel",
            categoria=self.categoria,
            preco_custo="0.00",
            preco_venda="1.00",
        )
        Estoque.objects.create(produto=self.produto, filial=self.filial, quantidade_atual=Decimal("3.000"))
        desmembramento = confirmar_desmembramento_simples(
            filial=self.filial,
            produto_origem=self.produto,
            quantidade_origem=Decimal("1.000"),
            produto_destino=destino,
            quantidade_destino=Decimal("12.000"),
            usuario=self.user,
            motivo="Abrir caixa",
        )

        cancelado = cancelar_desmembramento_produto(
            desmembramento=desmembramento,
            usuario=self.user,
            motivo="Lancado no produto errado",
        )

        self.assertEqual(cancelado.status, StatusDesmembramentoProduto.CANCELADO)
        self.assertEqual(Estoque.objects.get(produto=self.produto, filial=self.filial).quantidade_atual, Decimal("3.000"))
        self.assertEqual(Estoque.objects.get(produto=destino, filial=self.filial).quantidade_atual, Decimal("0.000"))
        self.assertEqual(MovimentacaoEstoque.objects.filter(tipo=TipoMovimentacaoEstoque.DESMEMBRAMENTO).count(), 4)
        self.assertTrue(LogAuditoria.objects.filter(acao="CANCELAMENTO_DESMEMBRAMENTO", objeto_id=str(desmembramento.id)).exists())

    def test_cancelar_desmembramento_bloqueia_se_destino_foi_consumido(self):
        destino = Produto.objects.create(
            codigo_barras="7896666666666",
            nome="Destino consumido",
            categoria=self.categoria,
            preco_custo="0.00",
            preco_venda="1.00",
        )
        Estoque.objects.create(produto=self.produto, filial=self.filial, quantidade_atual=Decimal("2.000"))
        desmembramento = confirmar_desmembramento_simples(
            filial=self.filial,
            produto_origem=self.produto,
            quantidade_origem=Decimal("1.000"),
            produto_destino=destino,
            quantidade_destino=Decimal("10.000"),
            usuario=self.user,
            motivo="Fracionar",
        )
        estoque_destino = Estoque.objects.get(produto=destino, filial=self.filial)
        estoque_destino.quantidade_atual = Decimal("4.000")
        estoque_destino.save()

        with self.assertRaises(ValidationError):
            cancelar_desmembramento_produto(
                desmembramento=desmembramento,
                usuario=self.user,
                motivo="Sem saldo para voltar",
            )

        desmembramento.refresh_from_db()
        self.assertEqual(desmembramento.status, StatusDesmembramentoProduto.CONFIRMADO)

    def test_telas_de_desmembramento_estao_disponiveis(self):
        lista = self.client.get("/estoque/desmembramentos/")
        form = self.client.get("/estoque/desmembramentos/novo/")
        estoque = self.client.get("/estoque/")

        self.assertEqual(lista.status_code, 200)
        self.assertContains(lista, "Desmembramentos")
        self.assertContains(lista, "Relatório de rendimento")
        self.assertEqual(form.status_code, 200)
        self.assertContains(form, "Produto origem")
        self.assertContains(form, "Produto destino")
        self.assertContains(form, "Adicionar destino")
        self.assertContains(form, "destinos-TOTAL_FORMS")
        self.assertContains(form, "Simular")
        self.assertContains(form, "select2-field")
        self.assertContains(form, 'data-ajax-url="/estoque/produtos/busca.json"')
        self.assertContains(estoque, "Desmembramentos")

    def test_busca_produtos_desmembramento_prioriza_codigo_exato_sku_e_nome(self):
        sku = Produto.objects.create(
            codigo_barras="7898888888888",
            codigo_interno="SKU-BALA-30",
            nome="Bala pacote fechado",
            categoria=self.categoria,
            preco_custo="12.00",
            preco_venda="15.00",
        )
        nome = Produto.objects.create(
            codigo_barras="7899999999999",
            codigo_interno="REF-AVULSA",
            nome="Bala avulsa unidade",
            categoria=self.categoria,
            preco_custo="0.40",
            preco_venda="0.80",
        )
        Produto.objects.create(
            codigo_barras="7897777777777",
            codigo_interno="REF-MARKET-BLOQ",
            nome="Bala marketplace bloqueada",
            categoria=self.categoria,
            preco_custo="0.40",
            preco_venda="0.80",
            vendido_no_marketplace=False,
        )

        por_codigo = self.client.get("/estoque/produtos/busca.json", {"q": sku.codigo_barras})
        por_sku = self.client.get("/estoque/produtos/busca.json", {"q": "SKU-BALA-30"})
        por_nome = self.client.get("/estoque/produtos/busca.json", {"q": "avulsa"})
        marketplace = self.client.get("/estoque/produtos/busca.json", {"q": "marketplace", "marketplace": "1"})

        self.assertEqual(por_codigo.status_code, 200)
        self.assertEqual(por_codigo.json()["results"][0]["id"], sku.id)
        self.assertEqual(por_sku.json()["results"][0]["id"], sku.id)
        self.assertEqual(por_nome.json()["results"][0]["id"], nome.id)
        self.assertEqual(por_nome.json()["results"][0]["unidade"], "UN")
        self.assertEqual(marketplace.json()["results"], [])

    def test_post_simular_desmembramento_mostra_previa_sem_supervisor(self):
        destino = Produto.objects.create(
            codigo_barras="7896767676767",
            nome="Destino previa",
            categoria=self.categoria,
            preco_custo="0.00",
            preco_venda="1.00",
        )
        Estoque.objects.create(produto=self.produto, filial=self.filial, quantidade_atual=Decimal("2.000"))

        response = self.client.post(
            "/estoque/desmembramentos/novo/",
            {
                "filial": self.filial.id,
                "tipo": "SIMPLES",
                "produto_origem": self.produto.id,
                "quantidade_origem": "1.000",
                "destinos-TOTAL_FORMS": "1",
                "destinos-INITIAL_FORMS": "0",
                "destinos-MIN_NUM_FORMS": "1",
                "destinos-MAX_NUM_FORMS": "1000",
                "destinos-0-produto_destino": destino.id,
                "destinos-0-quantidade_destino": "30.000",
                "destinos-0-tipo_saida_destino": "VENDAVEL",
                "motivo": "Conferir antes",
                "acao": "simular",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Previa da operação")
        self.assertContains(response, "Estoque suficiente para confirmar")
        self.assertEqual(DesmembramentoProduto.objects.count(), 0)
        self.assertEqual(MovimentacaoEstoque.objects.count(), 0)

    def test_post_simular_desmembramento_com_multiplos_destinos(self):
        destino_a = Produto.objects.create(
            codigo_barras="7896767676701",
            nome="Corte simulado A",
            categoria=self.categoria,
            unidade=UnidadeMedida.QUILO,
            preco_custo="0.00",
            preco_venda="12.00",
        )
        destino_b = Produto.objects.create(
            codigo_barras="7896767676702",
            nome="Apara simulada",
            categoria=self.categoria,
            unidade=UnidadeMedida.QUILO,
            preco_custo="0.00",
            preco_venda="4.00",
        )
        self.produto.unidade = UnidadeMedida.QUILO
        self.produto.save(update_fields=["unidade"])
        Estoque.objects.create(produto=self.produto, filial=self.filial, quantidade_atual=Decimal("3.000"))

        response = self.client.post(
            "/estoque/desmembramentos/novo/",
            {
                "filial": self.filial.id,
                "tipo": "ACOUGUE",
                "produto_origem": self.produto.id,
                "quantidade_origem": "1.000",
                "destinos-TOTAL_FORMS": "2",
                "destinos-INITIAL_FORMS": "0",
                "destinos-MIN_NUM_FORMS": "1",
                "destinos-MAX_NUM_FORMS": "1000",
                "destinos-0-produto_destino": destino_a.id,
                "destinos-0-quantidade_destino": "0.800",
                "destinos-0-tipo_saida_destino": "VENDAVEL",
                "destinos-0-percentual_rendimento_esperado": "80.00",
                "destinos-0-lote": "LOTE-SIM-A",
                "destinos-0-validade": "2026-07-25",
                "destinos-1-produto_destino": destino_b.id,
                "destinos-1-quantidade_destino": "0.200",
                "destinos-1-tipo_saida_destino": "SUBPRODUTO",
                "destinos-1-percentual_rendimento_esperado": "30.00",
                "destinos-1-lote": "LOTE-SIM-B",
                "destinos-1-validade": "2026-07-18",
                "motivo": "Simular rendimento",
                "acao": "simular",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Corte simulado A")
        self.assertContains(response, "Rendimento total")
        self.assertContains(response, "Conservação de massa conferida")
        self.assertContains(response, "Apara simulada")
        self.assertContains(response, "SUBPRODUTO")
        self.assertContains(response, "LOTE-SIM-A")
        self.assertContains(response, "80,00%")
        self.assertContains(response, "Abaixo do esperado")
        self.assertEqual(DesmembramentoProduto.objects.count(), 0)

    def test_detalhe_exibe_cancelamento_de_desmembramento(self):
        destino = Produto.objects.create(
            codigo_barras="7897777777777",
            nome="Destino detalhe",
            categoria=self.categoria,
            preco_custo="0.00",
            preco_venda="1.00",
        )
        Estoque.objects.create(produto=self.produto, filial=self.filial, quantidade_atual=Decimal("2.000"))
        desmembramento = confirmar_desmembramento_simples(
            filial=self.filial,
            produto_origem=self.produto,
            quantidade_origem=Decimal("1.000"),
            produto_destino=destino,
            quantidade_destino=Decimal("10.000"),
            usuario=self.user,
            motivo="Detalhar",
        )

        response = self.client.get(f"/estoque/desmembramentos/{desmembramento.id}/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cancelar desmembramento")
        self.assertContains(response, "saldo suficiente para voltar")
        self.assertContains(response, ">1</strong>")
        self.assertContains(response, ">10</td>")
        self.assertNotContains(response, "1,000")
        self.assertNotContains(response, "10,000")

        lista = self.client.get("/estoque/desmembramentos/")
        self.assertContains(lista, "Saida: 1")
        self.assertContains(lista, "Entrada: 10 UN")
        self.assertNotContains(lista, "Saida: 1,000")
        self.assertNotContains(lista, "Entrada: 10,000")

    def test_exportacao_csv_de_desmembramentos_respeita_busca_por_destino(self):
        destino = Produto.objects.create(
            codigo_barras="7891010101010",
            nome="Bala avulsa CSV",
            categoria=self.categoria,
            preco_custo="0.00",
            preco_venda="0.80",
        )
        outro = Produto.objects.create(
            codigo_barras="7892020202020",
            nome="Outro destino",
            categoria=self.categoria,
            preco_custo="0.00",
            preco_venda="1.00",
        )
        Estoque.objects.create(produto=self.produto, filial=self.filial, quantidade_atual=Decimal("4.000"))
        confirmar_desmembramento_simples(
            filial=self.filial,
            produto_origem=self.produto,
            quantidade_origem=Decimal("1.000"),
            produto_destino=destino,
            quantidade_destino=Decimal("30.000"),
            usuario=self.user,
            motivo="CSV destino certo",
        )
        confirmar_desmembramento_simples(
            filial=self.filial,
            produto_origem=self.produto,
            quantidade_origem=Decimal("1.000"),
            produto_destino=outro,
            quantidade_destino=Decimal("5.000"),
            usuario=self.user,
            motivo="CSV destino fora",
        )

        lista = self.client.get("/estoque/desmembramentos/", {"q": "avulsa"})
        csv_response = self.client.get("/estoque/desmembramentos/exportar.csv", {"q": "avulsa"})

        self.assertContains(lista, "Excel/CSV")
        self.assertContains(lista, "Bala avulsa CSV")
        self.assertNotContains(lista, "Outro destino")
        self.assertEqual(csv_response.status_code, 200)
        conteudo = csv_response.content.decode("utf-8-sig")
        self.assertIn("Bala avulsa CSV", conteudo)
        self.assertIn("CSV destino certo", conteudo)
        self.assertIn("Rendimento real %", conteudo)
        self.assertNotIn("Outro destino", conteudo)

    def test_receita_desmembramento_cadastra_conversao_padrao(self):
        destino = Produto.objects.create(
            codigo_barras="7893030303030",
            codigo_interno="BALA-UN",
            nome="Bala avulsa receita",
            categoria=self.categoria,
            preco_custo="0.40",
            preco_venda="0.80",
        )

        response = self.client.post(
            "/estoque/receitas-desmembramento/nova/",
            {
                "empresa": self.empresa.id,
                "filial": self.filial.id,
                "produto_origem": self.produto.id,
                "quantidade_origem": "1.000",
                "produto_destino": destino.id,
                "quantidade_destino": "30.000",
                "tipo": "SIMPLES",
                "tipo_saida": "SUBPRODUTO",
                "observacao": "Pacote padrão com trinta unidades",
                "is_active": "on",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ReceitaDesmembramento.objects.count(), 1)
        receita = ReceitaDesmembramento.objects.get()
        self.assertEqual(receita.quantidade_destino, Decimal("30.000"))
        self.assertEqual(receita.tipo_saida, TipoSaidaDesmembramento.SUBPRODUTO)
        self.assertContains(response, "Bala avulsa receita")
        self.assertContains(response, "Subproduto")
        self.assertContains(response, "1 -> 30")
        self.assertContains(response, f"/estoque/desmembramentos/novo/?receita={receita.id}")

    def test_tela_receita_desmembramento_usa_busca_remota_de_produtos(self):
        response = self.client.get("/estoque/receitas-desmembramento/nova/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Conversao padrão")
        self.assertContains(response, 'data-ajax-url="/estoque/produtos/busca.json"')

    def test_receita_desmembramento_nao_permite_origem_igual_destino(self):
        response = self.client.post(
            "/estoque/receitas-desmembramento/nova/",
            {
                "empresa": self.empresa.id,
                "filial": self.filial.id,
                "produto_origem": self.produto.id,
                "quantidade_origem": "1.000",
                "produto_destino": self.produto.id,
                "quantidade_destino": "1.000",
                "tipo": "SIMPLES",
                "tipo_saida": "VENDAVEL",
                "is_active": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Produto origem e produto destino devem ser diferentes")
        self.assertEqual(ReceitaDesmembramento.objects.count(), 0)

    def test_receita_preenche_desmembramento_por_querystring_e_endpoint_json(self):
        destino = Produto.objects.create(
            codigo_barras="7894040404040",
            codigo_interno="BALA-APLICAR",
            nome="Bala avulsa aplicar",
            categoria=self.categoria,
            preco_custo="0.40",
            preco_venda="0.80",
        )
        receita = ReceitaDesmembramento.objects.create(
            empresa=self.empresa,
            filial=self.filial,
            produto_origem=self.produto,
            quantidade_origem=Decimal("1.000"),
            produto_destino=destino,
            quantidade_destino=Decimal("30.000"),
            tipo="SIMPLES",
            tipo_saida=TipoSaidaDesmembramento.PERDA,
            observacao="Receita aplicada no formulario",
        )

        form = self.client.get("/estoque/desmembramentos/novo/", {"receita": receita.id})
        payload = self.client.get(f"/estoque/receitas-desmembramento/{receita.id}.json")

        self.assertEqual(form.status_code, 200)
        self.assertContains(form, 'data-recipe-select="true"')
        self.assertContains(form, 'value="1.000"')
        self.assertContains(form, 'value="30.000"')
        self.assertContains(form, 'name="destinos-0-tipo_saida_destino"')
        self.assertContains(form, "Receita aplicada no formulario")
        self.assertEqual(payload.status_code, 200)
        self.assertEqual(payload.json()["receita"]["produto_origem_id"], self.produto.id)
        self.assertEqual(payload.json()["receita"]["produto_destino_id"], destino.id)
        self.assertEqual(payload.json()["receita"]["tipo_saida"], TipoSaidaDesmembramento.PERDA)
class RastreioLoteEstoqueTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_superuser("lotes", "lotes@example.com", "123")
        self.empresa = Empresa.objects.create(
            razao_social="Mercado Lotes",
            nome_fantasia="Mercado Lotes",
            cnpj="63.456.789/0001-10",
        )
        self.filial = Filial.objects.create(empresa=self.empresa, nome="Matriz Lotes", cnpj=self.empresa.cnpj)
        self.categoria = Categoria.all_objects.create(nome="Categoria Lotes")
        self.produto = Produto.objects.create(
            codigo_barras="7896345678901",
            nome="Produto por lote",
            categoria=self.categoria,
            preco_custo=Decimal("5.00"),
            preco_venda=Decimal("9.00"),
        )
        self.client.force_login(self.usuario)

    def _entrada_lote(self, codigo, quantidade, validade, custo):
        return movimentar_estoque(
            produto=self.produto,
            filial=self.filial,
            tipo=TipoMovimentacaoEstoque.ENTRADA,
            quantidade=Decimal(quantidade),
            usuario=self.usuario,
            motivo="Entrada teste",
            referencia=f"teste:{codigo}",
            custo_unitario=Decimal(custo),
            codigo_lote=codigo,
            validade=validade,
        )

    def test_entrada_cria_camada_de_lote_e_historico_de_custo(self):
        movimento = self._entrada_lote("LOTE-A", "5.000", date(2026, 9, 30), "4.50")

        lote = LoteEstoque.objects.get()
        alocacao = MovimentacaoLoteEstoque.objects.get()
        self.assertEqual(lote.quantidade_inicial, Decimal("5.000"))
        self.assertEqual(lote.quantidade_atual, Decimal("5.000"))
        self.assertEqual(lote.custo_unitario, Decimal("4.50"))
        self.assertEqual(lote.origem_referencia, "teste:LOTE-A")
        self.assertEqual(alocacao.movimentacao, movimento)
        self.assertEqual(alocacao.lote, lote)

    def test_saida_consumo_fefo_primeiro_lote_a_vencer(self):
        self._entrada_lote("LOTE-TARDE", "4.000", date(2026, 12, 31), "6.00")
        self._entrada_lote("LOTE-CEDO", "3.000", date(2026, 8, 15), "5.00")

        saida = movimentar_estoque(
            produto=self.produto,
            filial=self.filial,
            tipo=TipoMovimentacaoEstoque.VENDA,
            quantidade=Decimal("5.000"),
            usuario=self.usuario,
            referencia="venda:fefo",
            custo_unitario=Decimal("5.50"),
        )

        cedo = LoteEstoque.objects.get(codigo="LOTE-CEDO")
        tarde = LoteEstoque.objects.get(codigo="LOTE-TARDE")
        self.assertEqual(cedo.quantidade_atual, Decimal("0.000"))
        self.assertEqual(tarde.quantidade_atual, Decimal("2.000"))
        self.assertEqual(
            list(saida.alocacoes_lote.values_list("lote__codigo", "quantidade")),
            [("LOTE-CEDO", Decimal("3.000")), ("LOTE-TARDE", Decimal("2.000"))],
        )

    def test_saldo_legado_sem_lote_continua_utilizavel(self):
        Estoque.objects.create(
            produto=self.produto,
            filial=self.filial,
            quantidade_atual=Decimal("10.000"),
        )
        self._entrada_lote("LOTE-R", "2.000", date(2026, 10, 10), "5.00")

        saida = movimentar_estoque(
            produto=self.produto,
            filial=self.filial,
            tipo=TipoMovimentacaoEstoque.SAIDA,
            quantidade=Decimal("5.000"),
            usuario=self.usuario,
        )

        self.assertEqual(Estoque.objects.get(produto=self.produto, filial=self.filial).quantidade_atual, Decimal("7.000"))
        self.assertEqual(LoteEstoque.objects.get().quantidade_atual, Decimal("0.000"))
        self.assertEqual(saida.alocacoes_lote.aggregate(total=Sum("quantidade"))["total"], Decimal("2.000"))

    def test_saida_de_lote_explicito_sem_saldo_reverte_movimento(self):
        self._entrada_lote("LOTE-X", "2.000", date(2026, 10, 10), "5.00")
        estoque = Estoque.objects.get(produto=self.produto, filial=self.filial)
        estoque.quantidade_atual = Decimal("5.000")
        estoque.save(update_fields=["quantidade_atual", "atualizado_em"])

        with self.assertRaisesMessage(ValidationError, "Saldo insuficiente no lote"):
            movimentar_estoque(
                produto=self.produto,
                filial=self.filial,
                tipo=TipoMovimentacaoEstoque.SAIDA,
                quantidade=Decimal("3.000"),
                usuario=self.usuario,
                codigo_lote="LOTE-X",
            )

        self.assertEqual(Estoque.objects.get(produto=self.produto, filial=self.filial).quantidade_atual, Decimal("5.000"))
        self.assertEqual(LoteEstoque.objects.get().quantidade_atual, Decimal("2.000"))
        self.assertEqual(MovimentacaoEstoque.objects.count(), 1)

    def test_painel_exibe_alertas_de_validade(self):
        self._entrada_lote("LOTE-VENCIDO", "1.000", timezone.localdate() - timedelta(days=1), "5.00")
        self._entrada_lote("LOTE-PROXIMO", "1.000", timezone.localdate() + timedelta(days=10), "5.00")

        response = self.client.get("/estoque/lotes/")

        self.assertContains(response, "Lotes e validades")
        self.assertContains(response, "Vencidos com saldo")
        self.assertContains(response, "Vencem em 30 dias")
        self.assertEqual(response.context["resumo_lotes"]["vencidos"], 1)
        self.assertEqual(response.context["resumo_lotes"]["proximos"], 1)

    def test_atribuicao_historica_nao_altera_saldo_e_respeita_limite_sem_lote(self):
        estoque = Estoque.objects.create(
            produto=self.produto,
            filial=self.filial,
            quantidade_atual=Decimal("10.000"),
        )

        lote = atribuir_saldo_historico_lote(
            estoque=estoque,
            codigo="HIST-01",
            quantidade=Decimal("6.000"),
            custo_unitario=Decimal("4.80"),
            usuario=self.usuario,
            motivo="Contagem fisica por lote",
            validade=date(2026, 12, 31),
        )

        estoque.refresh_from_db()
        self.assertEqual(estoque.quantidade_atual, Decimal("10.000"))
        self.assertEqual(lote.quantidade_atual, Decimal("6.000"))
        self.assertEqual(lote.origem_referencia, f"atribuicao_historico:estoque:{estoque.id}")
        self.assertTrue(LogAuditoria.objects.filter(acao="ATRIBUICAO_SALDO_HISTORICO_LOTE").exists())
        with self.assertRaisesMessage(ValidationError, "excede o saldo sem lote"):
            atribuir_saldo_historico_lote(
                estoque=estoque,
                codigo="HIST-02",
                quantidade=Decimal("5.000"),
                custo_unitario=Decimal("4.90"),
                usuario=self.usuario,
                motivo="Excesso",
            )

    def test_tela_reconciliacao_exige_autorizacao_e_atribui_lote(self):
        estoque = Estoque.objects.create(
            produto=self.produto,
            filial=self.filial,
            quantidade_atual=Decimal("4.000"),
        )
        painel = self.client.get("/estoque/lotes/reconciliacao/")
        self.assertContains(painel, "Reconciliação de lotes")
        self.assertContains(painel, "4")

        response = self.client.post(
            f"/estoque/lotes/reconciliacao/{estoque.pk}/atribuir/",
            {
                "codigo": "TELA-01",
                "quantidade": "2.000",
                "custo_unitario": "5.00",
                "fabricacao": "",
                "validade": "2026-12-31",
                "motivo": "Conferencia no deposito",
                "supervisor_usuario": self.usuario.username,
                "supervisor_senha": "123",
            },
            follow=True,
        )

        self.assertContains(response, "Saldo atribuido ao lote TELA-01")
        self.assertEqual(LoteEstoque.objects.get().quantidade_atual, Decimal("2.000"))
        self.assertEqual(Estoque.objects.get().quantidade_atual, Decimal("4.000"))

    def test_inventario_reduz_lotes_somente_quando_rastreado_excede_novo_saldo(self):
        estoque = Estoque.objects.create(
            produto=self.produto,
            filial=self.filial,
            quantidade_atual=Decimal("10.000"),
        )
        atribuir_saldo_historico_lote(
            estoque=estoque,
            codigo="INV-CEDO",
            quantidade=Decimal("3.000"),
            custo_unitario=Decimal("5.00"),
            usuario=self.usuario,
            motivo="Base inventario",
            validade=date(2026, 8, 31),
        )
        atribuir_saldo_historico_lote(
            estoque=estoque,
            codigo="INV-TARDE",
            quantidade=Decimal("3.000"),
            custo_unitario=Decimal("6.00"),
            usuario=self.usuario,
            motivo="Base inventario",
            validade=date(2026, 12, 31),
        )
        inventario = InventarioEstoque.objects.create(
            filial=self.filial,
            usuario=self.usuario,
            descricao="Contagem com lotes",
        )
        ItemInventarioEstoque.objects.create(
            inventario=inventario,
            produto=self.produto,
            quantidade_sistema=Decimal("10.000"),
            quantidade_contada=Decimal("3.000"),
            diferenca=Decimal("-7.000"),
        )

        aplicar_inventario(inventario=inventario, usuario=self.usuario)

        inventario.refresh_from_db()
        cedo = LoteEstoque.objects.get(codigo="INV-CEDO")
        tarde = LoteEstoque.objects.get(codigo="INV-TARDE")
        movimento = MovimentacaoEstoque.objects.get(referencia=f"inventario:{inventario.id}")
        self.assertEqual(inventario.status, StatusInventario.APLICADO)
        self.assertEqual(cedo.quantidade_atual, Decimal("0.000"))
        self.assertEqual(tarde.quantidade_atual, Decimal("3.000"))
        self.assertEqual(movimento.alocacoes_lote.aggregate(total=Sum("quantidade"))["total"], Decimal("3.000"))

    def test_aumento_de_inventario_permanece_sem_lote(self):
        estoque = Estoque.objects.create(
            produto=self.produto,
            filial=self.filial,
            quantidade_atual=Decimal("2.000"),
        )
        inventario = InventarioEstoque.objects.create(
            filial=self.filial,
            usuario=self.usuario,
            descricao="Aumento sem lote presumido",
        )
        ItemInventarioEstoque.objects.create(
            inventario=inventario,
            produto=self.produto,
            quantidade_sistema=Decimal("2.000"),
            quantidade_contada=Decimal("5.000"),
            diferenca=Decimal("3.000"),
        )

        aplicar_inventario(inventario=inventario, usuario=self.usuario)

        estoque.refresh_from_db()
        self.assertEqual(estoque.quantidade_atual, Decimal("5.000"))
        self.assertEqual(LoteEstoque.objects.count(), 0)

    def test_desmembramento_consome_origem_cria_destino_e_cancela_lotes(self):
        destino = Produto.objects.create(
            codigo_barras="7896345678999",
            nome="Destino rastreado",
            categoria=self.categoria,
            preco_custo=Decimal("0.00"),
            preco_venda=Decimal("3.00"),
        )
        self._entrada_lote("ORIGEM-01", "2.000", date(2026, 9, 30), "5.00")

        desmembramento = confirmar_desmembramento_multidestino(
            filial=self.filial,
            produto_origem=self.produto,
            quantidade_origem=Decimal("1.000"),
            destinos=[{
                "produto": destino,
                "quantidade": Decimal("4.000"),
                "lote": "DESTINO-01",
                "validade": date(2026, 8, 31),
            }],
            usuario=self.usuario,
            motivo="Transformacao rastreada",
        )

        origem = LoteEstoque.objects.get(codigo="ORIGEM-01")
        lote_destino = LoteEstoque.objects.get(codigo="DESTINO-01")
        movimento_origem = MovimentacaoEstoque.objects.get(
            referencia=f"desmembramento:{desmembramento.id}:origem"
        )
        self.assertEqual(origem.quantidade_atual, Decimal("1.000"))
        self.assertEqual(lote_destino.quantidade_atual, Decimal("4.000"))
        self.assertEqual(movimento_origem.alocacoes_lote.get().lote, origem)

        cancelar_desmembramento_produto(
            desmembramento=desmembramento,
            usuario=self.usuario,
            motivo="Cancelar teste rastreado",
        )

        origem.refresh_from_db()
        lote_destino.refresh_from_db()
        self.assertEqual(origem.quantidade_atual, Decimal("2.000"))
        self.assertEqual(lote_destino.quantidade_atual, Decimal("0.000"))
        retorno = MovimentacaoEstoque.objects.get(
            referencia=f"desmembramento:{desmembramento.id}:cancelamento:origem"
        )
        self.assertEqual(retorno.alocacoes_lote.get().lote, origem)

    def test_producao_consome_componentes_fefo_e_cancelamento_restaura_camadas(self):
        produto_final = Produto.objects.create(
            codigo_barras="7896345678988",
            nome="Produto final rastreado",
            categoria=self.categoria,
            preco_custo=Decimal("0.00"),
            preco_venda=Decimal("12.00"),
        )
        composicao = ComposicaoProduto.objects.create(
            empresa=self.empresa,
            filial=self.filial,
            produto_final=produto_final,
            quantidade_final=Decimal("1.000"),
            observacao="Composicao rastreada",
        )
        ItemComposicaoProduto.objects.create(
            composicao=composicao,
            produto_componente=self.produto,
            quantidade=Decimal("1.000"),
        )
        self._entrada_lote("COMP-01", "5.000", date(2026, 10, 31), "5.00")

        producao = confirmar_producao_composicao(
            composicao=composicao,
            filial=self.filial,
            quantidade_final=Decimal("2.000"),
            usuario=self.usuario,
            motivo="Produzir lote de teste",
        )

        lote = LoteEstoque.objects.get(codigo="COMP-01")
        movimento_consumo = MovimentacaoEstoque.objects.get(
            referencia=f"composicao:{producao.id}:componente:{self.produto.id}"
        )
        self.assertEqual(lote.quantidade_atual, Decimal("3.000"))
        self.assertEqual(movimento_consumo.alocacoes_lote.get().quantidade, Decimal("2.000"))

        cancelar_producao_composicao(
            producao=producao,
            usuario=self.usuario,
            motivo="Cancelar produção rastreada",
        )

        lote.refresh_from_db()
        self.assertEqual(lote.quantidade_atual, Decimal("5.000"))
        reversao = MovimentacaoEstoque.objects.get(
            referencia=f"composicao:{producao.id}:cancelamento:componente:{producao.itens.get().id}"
        )
        self.assertEqual(reversao.alocacoes_lote.get().quantidade, Decimal("2.000"))

    def test_politica_opt_in_bloqueia_nova_entrada_sem_afetar_produto_legado(self):
        movimentar_estoque(
            produto=self.produto,
            filial=self.filial,
            tipo=TipoMovimentacaoEstoque.ENTRADA,
            quantidade=Decimal("1.000"),
            custo_unitario=Decimal("5.00"),
        )
        self.produto.exige_lote = True
        self.produto.save(update_fields=["exige_lote", "updated_at"])

        with self.assertRaisesMessage(ValidationError, "exige lote"):
            movimentar_estoque(
                produto=self.produto,
                filial=self.filial,
                tipo=TipoMovimentacaoEstoque.ENTRADA,
                quantidade=Decimal("1.000"),
                custo_unitario=Decimal("5.00"),
            )

        estoque = Estoque.objects.get(produto=self.produto, filial=self.filial)
        self.assertEqual(estoque.quantidade_atual, Decimal("1.000"))

    def test_producao_com_lote_obrigatorio_cria_camada_e_cancelamento_baixa_a_mesma_camada(self):
        produto_final = Produto.objects.create(
            codigo_barras="7896345678977",
            nome="Produto final com lote obrigatório",
            categoria=self.categoria,
            preco_custo=Decimal("0.00"),
            preco_venda=Decimal("12.00"),
            exige_lote=True,
        )
        composicao = ComposicaoProduto.objects.create(
            empresa=self.empresa,
            filial=self.filial,
            produto_final=produto_final,
            quantidade_final=Decimal("1.000"),
        )
        ItemComposicaoProduto.objects.create(
            composicao=composicao,
            produto_componente=self.produto,
            quantidade=Decimal("1.000"),
        )
        self._entrada_lote("COMP-OBRIG-01", "2.000", date(2026, 10, 31), "5.00")

        with self.assertRaisesMessage(ValidationError, "produto final exige lote"):
            confirmar_producao_composicao(
                composicao=composicao,
                filial=self.filial,
                quantidade_final=Decimal("1.000"),
                usuario=self.usuario,
                motivo="Tentativa sem lote",
            )

        movimentar_estoque(
            produto=produto_final,
            filial=self.filial,
            tipo=TipoMovimentacaoEstoque.ENTRADA,
            quantidade=Decimal("2.000"),
            custo_unitario=Decimal("4.00"),
            codigo_lote="FINAL-01",
            validade=date(2027, 1, 31),
        )
        producao = confirmar_producao_composicao(
            composicao=composicao,
            filial=self.filial,
            quantidade_final=Decimal("1.000"),
            usuario=self.usuario,
            motivo="Producao identificada",
            codigo_lote="FINAL-01",
            fabricacao=date(2026, 7, 25),
            validade=date(2026, 12, 31),
        )
        lote_final = LoteEstoque.objects.get(
            produto=produto_final,
            origem_referencia=f"composicao:{producao.id}:final",
        )
        lote_homonimo = LoteEstoque.objects.exclude(pk=lote_final.pk).get(
            produto=produto_final,
            codigo="FINAL-01",
        )
        self.assertEqual(lote_final.quantidade_atual, Decimal("1.000"))

        cancelar_producao_composicao(
            producao=producao,
            usuario=self.usuario,
            motivo="Cancelar produção identificada",
        )
        lote_final.refresh_from_db()
        lote_homonimo.refresh_from_db()
        self.assertEqual(lote_final.quantidade_atual, Decimal("0.000"))
        self.assertEqual(lote_homonimo.quantidade_atual, Decimal("2.000"))

    def test_desmembramento_exige_lote_somente_no_destino_controlado(self):
        destino = Produto.objects.create(
            codigo_barras="7896345678966",
            nome="Destino com lote obrigatório",
            categoria=self.categoria,
            preco_custo=Decimal("0.00"),
            preco_venda=Decimal("3.00"),
            exige_lote=True,
        )
        self._entrada_lote("ORIGEM-OBRIG-01", "2.000", date(2026, 9, 30), "5.00")

        with self.assertRaisesMessage(ValidationError, "destino Destino com lote obrigatório exige lote"):
            confirmar_desmembramento_multidestino(
                filial=self.filial,
                produto_origem=self.produto,
                quantidade_origem=Decimal("1.000"),
                destinos=[{"produto": destino, "quantidade": Decimal("2.000")}],
                usuario=self.usuario,
                motivo="Tentativa sem lote",
            )

        origem = Estoque.objects.get(produto=self.produto, filial=self.filial)
        self.assertEqual(origem.quantidade_atual, Decimal("2.000"))


class EstoqueCoreMultiempresaTests(TestCase):
    def setUp(self):
        self.empresa_a = Empresa.objects.create(
            razao_social="Estoque Empresa A",
            nome_fantasia="Estoque A",
            cnpj="71.111.111/0001-11",
        )
        self.empresa_b = Empresa.objects.create(
            razao_social="Estoque Empresa B",
            nome_fantasia="Estoque B",
            cnpj="72.222.222/0001-22",
        )
        self.filial_a = Filial.objects.create(empresa=self.empresa_a, nome="Matriz A", cnpj=self.empresa_a.cnpj)
        self.filial_b = Filial.objects.create(empresa=self.empresa_b, nome="Matriz B", cnpj=self.empresa_b.cnpj)
        self.usuario_a = get_user_model().objects.create_user("estoque_a", password="123")
        PerfilUsuario.objects.create(
            usuario=self.usuario_a,
            filial=self.filial_a,
            tipo=TipoPerfil.ESTOQUISTA,
        )
        self.usuario_b = get_user_model().objects.create_user("estoque_b", password="123")
        PerfilUsuario.objects.create(
            usuario=self.usuario_b,
            filial=self.filial_b,
            tipo=TipoPerfil.ADMINISTRADOR,
        )
        self.categoria = Categoria.all_objects.create(nome="Categoria multiempresa estoque")
        self.produto = Produto.objects.create(
            codigo_barras="7897111111111",
            nome="Produto multiempresa estoque",
            categoria=self.categoria,
            preco_custo=Decimal("4.00"),
            preco_venda=Decimal("7.00"),
        )
        self.estoque_a = Estoque.objects.create(
            produto=self.produto,
            filial=self.filial_a,
            quantidade_atual=Decimal("5.000"),
        )
        self.estoque_b = Estoque.objects.create(
            produto=self.produto,
            filial=self.filial_b,
            quantidade_atual=Decimal("8.000"),
        )
        self.lote_a = LoteEstoque.objects.create(
            produto=self.produto,
            filial=self.filial_a,
            codigo="LOTE-A",
            quantidade_inicial=Decimal("2.000"),
            quantidade_atual=Decimal("2.000"),
            custo_unitario=Decimal("4.00"),
        )
        self.lote_b = LoteEstoque.objects.create(
            produto=self.produto,
            filial=self.filial_b,
            codigo="LOTE-B",
            quantidade_inicial=Decimal("3.000"),
            quantidade_atual=Decimal("3.000"),
            custo_unitario=Decimal("4.00"),
        )
        self.inventario_a = InventarioEstoque.objects.create(
            filial=self.filial_a,
            usuario=self.usuario_a,
            descricao="Inventario A",
        )
        self.inventario_b = InventarioEstoque.objects.create(
            filial=self.filial_b,
            usuario=self.usuario_b,
            descricao="Inventario B",
        )
        self.perda_a = PerdaEstoque.objects.create(
            produto=self.produto,
            filial=self.filial_a,
            usuario=self.usuario_a,
            tipo="AVARIA",
            quantidade=Decimal("1.000"),
            motivo="Perda A",
            custo_unitario_no_momento=Decimal("4.00"),
            preco_venda_no_momento=Decimal("7.00"),
            valor_custo_estimado=Decimal("4.00"),
            valor_venda_estimado=Decimal("7.00"),
        )
        self.perda_b = PerdaEstoque.objects.create(
            produto=self.produto,
            filial=self.filial_b,
            usuario=self.usuario_b,
            tipo="AVARIA",
            quantidade=Decimal("1.000"),
            motivo="Perda B",
            custo_unitario_no_momento=Decimal("4.00"),
            preco_venda_no_momento=Decimal("7.00"),
            valor_custo_estimado=Decimal("4.00"),
            valor_venda_estimado=Decimal("7.00"),
        )
        self.destino = Produto.objects.create(
            codigo_barras="7897222222222",
            nome="Destino multiempresa estoque",
            categoria=self.categoria,
            preco_custo=Decimal("2.00"),
            preco_venda=Decimal("5.00"),
        )
        self.receita_a = ReceitaDesmembramento.objects.create(
            empresa=self.empresa_a,
            filial=self.filial_a,
            produto_origem=self.produto,
            quantidade_origem=Decimal("1.000"),
            produto_destino=self.destino,
            quantidade_destino=Decimal("2.000"),
            observacao="Receita empresa A",
        )
        self.receita_b = ReceitaDesmembramento.objects.create(
            empresa=self.empresa_b,
            filial=self.filial_b,
            produto_origem=self.produto,
            quantidade_origem=Decimal("1.000"),
            produto_destino=self.destino,
            quantidade_destino=Decimal("3.000"),
            observacao="Receita empresa B",
        )
        self.desmembramento_a = DesmembramentoProduto.objects.create(
            empresa=self.empresa_a,
            filial=self.filial_a,
            produto_origem=self.produto,
            quantidade_origem=Decimal("1.000"),
            custo_total_origem=Decimal("4.00"),
            usuario=self.usuario_a,
            motivo="Desmembramento empresa A",
        )
        self.desmembramento_b = DesmembramentoProduto.objects.create(
            empresa=self.empresa_b,
            filial=self.filial_b,
            produto_origem=self.produto,
            quantidade_origem=Decimal("1.000"),
            custo_total_origem=Decimal("4.00"),
            usuario=self.usuario_b,
            motivo="Desmembramento empresa B",
        )
        ItemDesmembramentoProduto.objects.create(
            desmembramento=self.desmembramento_a,
            produto_destino=self.destino,
            quantidade_gerada=Decimal("2.000"),
            unidade="UN",
            custo_unitario_calculado=Decimal("2.00"),
            custo_total=Decimal("4.00"),
            percentual_rendimento=Decimal("100.00"),
        )
        ItemDesmembramentoProduto.objects.create(
            desmembramento=self.desmembramento_b,
            produto_destino=self.destino,
            quantidade_gerada=Decimal("3.000"),
            unidade="UN",
            custo_unitario_calculado=Decimal("1.33"),
            custo_total=Decimal("4.00"),
            percentual_rendimento=Decimal("100.00"),
        )
        self.client.force_login(self.usuario_a)

    def test_listagens_do_nucleo_mostram_apenas_a_empresa_do_usuario(self):
        estoque = self.client.get("/estoque/")
        lotes = self.client.get("/estoque/lotes/")
        inventarios = self.client.get("/estoque/inventarios/")
        perdas = self.client.get("/estoque/perdas/")
        reconciliacao = self.client.get("/estoque/lotes/reconciliacao/")

        self.assertEqual({item.pk for item in estoque.context["estoques"]}, {self.estoque_a.pk})
        self.assertEqual({item.pk for item in lotes.context["lotes"]}, {self.lote_a.pk})
        self.assertEqual({item.pk for item in inventarios.context["inventarios"]}, {self.inventario_a.pk})
        self.assertEqual({item.pk for item in perdas.context["perdas"]}, {self.perda_a.pk})
        self.assertContains(reconciliacao, "Matriz A")
        self.assertNotContains(reconciliacao, "Matriz B")
        self.assertEqual(lotes.context["resumo_lotes"]["com_saldo"], 1)

    def test_ids_de_outra_empresa_nao_abrem_nem_alteram_inventario_ou_reconciliacao(self):
        self.assertEqual(self.client.get(f"/estoque/inventarios/{self.inventario_b.pk}/").status_code, 404)
        self.assertEqual(
            self.client.post(f"/estoque/inventarios/{self.inventario_b.pk}/itens/novo/").status_code,
            404,
        )
        self.assertEqual(
            self.client.post(f"/estoque/inventarios/{self.inventario_b.pk}/aplicar/").status_code,
            404,
        )
        self.assertEqual(
            self.client.get(f"/estoque/lotes/reconciliacao/{self.estoque_b.pk}/atribuir/").status_code,
            404,
        )
        self.inventario_b.refresh_from_db()
        self.assertEqual(self.inventario_b.status, StatusInventario.ABERTO)

    def test_formularios_rejeitam_filial_de_outra_empresa(self):
        inventario = self.client.post(
            "/estoque/inventarios/novo/",
            {"filial": self.filial_b.pk, "descricao": "Inventario forjado"},
        )
        movimentacao = self.client.post(
            "/estoque/movimentar/",
            {
                "produto": self.produto.pk,
                "filial": self.filial_b.pk,
                "tipo": TipoMovimentacaoEstoque.ENTRADA,
                "quantidade": "2.000",
                "motivo": "Movimento forjado",
            },
        )
        perda = self.client.post(
            "/estoque/perdas/nova/",
            {
                "produto": self.produto.pk,
                "filial": self.filial_b.pk,
                "tipo": "AVARIA",
                "quantidade": "1.000",
                "motivo": "Perda forjada",
            },
        )

        self.assertIn("filial", inventario.context["form"].errors)
        self.assertIn("filial", movimentacao.context["form"].errors)
        self.assertIn("filial", perda.context["form"].errors)
        self.assertFalse(InventarioEstoque.objects.filter(descricao="Inventario forjado").exists())
        self.assertFalse(MovimentacaoEstoque.objects.filter(motivo="Movimento forjado").exists())
        self.assertFalse(PerdaEstoque.objects.filter(motivo="Perda forjada").exists())

    def test_supervisor_de_outra_empresa_nao_autoriza_movimentacao(self):
        resposta = self.client.post(
            "/estoque/movimentar/",
            {
                "produto": self.produto.pk,
                "filial": self.filial_a.pk,
                "tipo": TipoMovimentacaoEstoque.ENTRADA,
                "quantidade": "2.000",
                "motivo": "Autorizacao cruzada",
                "supervisor_usuario": self.usuario_b.username,
                "supervisor_senha": "123",
            },
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "mesma empresa do operador")
        self.assertFalse(MovimentacaoEstoque.objects.filter(motivo="Autorizacao cruzada").exists())

    def test_desmembramentos_receitas_relatorios_e_csv_respeitam_empresa(self):
        desmembramentos = self.client.get("/estoque/desmembramentos/")
        receitas = self.client.get("/estoque/receitas-desmembramento/")
        relatorio = self.client.get("/estoque/desmembramentos/relatorio/")
        csv_lista = self.client.get("/estoque/desmembramentos/exportar.csv").content.decode("utf-8-sig")
        csv_relatorio = self.client.get("/estoque/desmembramentos/relatorio/exportar.csv").content.decode("utf-8-sig")

        self.assertEqual(
            {item.pk for item in desmembramentos.context["desmembramentos"]},
            {self.desmembramento_a.pk},
        )
        self.assertEqual({item.pk for item in receitas.context["receitas"]}, {self.receita_a.pk})
        self.assertEqual(
            {item.desmembramento_id for item in relatorio.context["itens"]},
            {self.desmembramento_a.pk},
        )
        self.assertEqual({filial.pk for filial in relatorio.context["filiais"]}, {self.filial_a.pk})
        self.assertIn("Desmembramento empresa A", csv_lista)
        self.assertNotIn("Desmembramento empresa B", csv_lista)
        self.assertIn(self.filial_a.nome, csv_relatorio)
        self.assertNotIn(self.filial_b.nome, csv_relatorio)

    def test_ids_de_receita_e_desmembramento_externos_retornam_404(self):
        self.assertEqual(
            self.client.get(f"/estoque/receitas-desmembramento/{self.receita_b.pk}.json").status_code,
            404,
        )
        self.assertEqual(
            self.client.get(f"/estoque/receitas-desmembramento/{self.receita_b.pk}/editar/").status_code,
            404,
        )
        self.assertEqual(
            self.client.get(f"/estoque/desmembramentos/{self.desmembramento_b.pk}/").status_code,
            404,
        )
        self.assertEqual(
            self.client.post(f"/estoque/desmembramentos/{self.desmembramento_b.pk}/cancelar/").status_code,
            404,
        )

    def test_formularios_de_receita_e_desmembramento_rejeitam_empresa_externa(self):
        receita = self.client.post(
            "/estoque/receitas-desmembramento/nova/",
            {
                "empresa": self.empresa_b.pk,
                "filial": self.filial_b.pk,
                "produto_origem": self.produto.pk,
                "quantidade_origem": "1.000",
                "produto_destino": self.destino.pk,
                "quantidade_destino": "2.000",
                "tipo": TipoDesmembramentoProduto.SIMPLES,
                "tipo_saida": TipoSaidaDesmembramento.VENDAVEL,
                "is_active": "on",
            },
        )
        desmembramento = self.client.post(
            "/estoque/desmembramentos/novo/",
            {
                "receita": self.receita_b.pk,
                "filial": self.filial_b.pk,
                "produto_origem": self.produto.pk,
                "quantidade_origem": "1.000",
                "tipo": TipoDesmembramentoProduto.SIMPLES,
                "motivo": "Desmembramento forjado",
                "destinos-TOTAL_FORMS": "1",
                "destinos-INITIAL_FORMS": "0",
                "destinos-MIN_NUM_FORMS": "1",
                "destinos-MAX_NUM_FORMS": "1000",
                "destinos-0-produto_destino": self.destino.pk,
                "destinos-0-quantidade_destino": "2.000",
                "destinos-0-tipo_saida_destino": TipoSaidaDesmembramento.VENDAVEL,
            },
        )

        self.assertIn("empresa", receita.context["form"].errors)
        self.assertIn("filial", receita.context["form"].errors)
        self.assertIn("receita", desmembramento.context["form"].errors)
        self.assertIn("filial", desmembramento.context["form"].errors)
        self.assertFalse(DesmembramentoProduto.objects.filter(motivo="Desmembramento forjado").exists())
    def _dados_producao_multiempresa(self):
        composicao_a = ComposicaoProduto.objects.create(
            empresa=self.empresa_a,
            filial=self.filial_a,
            produto_final=self.destino,
            quantidade_final=Decimal("1.000"),
            observacao="Composicao empresa A",
        )
        composicao_b = ComposicaoProduto.objects.create(
            empresa=self.empresa_b,
            filial=self.filial_b,
            produto_final=self.destino,
            quantidade_final=Decimal("1.000"),
            observacao="Composicao empresa B",
        )
        ItemComposicaoProduto.objects.create(
            composicao=composicao_a, produto_componente=self.produto, quantidade=Decimal("1.000")
        )
        ItemComposicaoProduto.objects.create(
            composicao=composicao_b, produto_componente=self.produto, quantidade=Decimal("1.000")
        )
        producao_a = ProducaoComposicaoProduto.objects.create(
            composicao=composicao_a,
            empresa=self.empresa_a,
            filial=self.filial_a,
            produto_final=self.destino,
            quantidade_final=Decimal("1.000"),
            custo_total=Decimal("4.00"),
            usuario=self.usuario_a,
            motivo="Producao empresa A",
        )
        producao_b = ProducaoComposicaoProduto.objects.create(
            composicao=composicao_b,
            empresa=self.empresa_b,
            filial=self.filial_b,
            produto_final=self.destino,
            quantidade_final=Decimal("1.000"),
            custo_total=Decimal("4.00"),
            usuario=self.usuario_b,
            motivo="Producao empresa B",
        )
        ordem_a = OrdemProducaoComposicao.objects.create(
            composicao=composicao_a,
            empresa=self.empresa_a,
            filial=self.filial_a,
            produto_final=self.destino,
            quantidade_planejada=Decimal("2.000"),
            data_programada=timezone.localdate(),
            setor_responsavel="Setor empresa A",
            usuario=self.usuario_a,
            responsavel_operacional=self.usuario_a,
            motivo="Ordem empresa A",
        )
        ordem_b = OrdemProducaoComposicao.objects.create(
            composicao=composicao_b,
            empresa=self.empresa_b,
            filial=self.filial_b,
            produto_final=self.destino,
            quantidade_planejada=Decimal("3.000"),
            data_programada=timezone.localdate(),
            setor_responsavel="Setor empresa B",
            usuario=self.usuario_b,
            responsavel_operacional=self.usuario_b,
            motivo="Ordem empresa B",
        )
        sla_a = ConfiguracaoSLASetorProducao.objects.create(
            empresa=self.empresa_a, filial=self.filial_a, setor="Setor empresa A", meta_minutos=60
        )
        sla_b = ConfiguracaoSLASetorProducao.objects.create(
            empresa=self.empresa_b, filial=self.filial_b, setor="Setor empresa B", meta_minutos=90
        )
        alerta_b = AlertaSLAOrdemProducao.objects.create(
            ordem=ordem_b,
            usuario=self.usuario_a,
            papel="RESPONSAVEL",
            mensagem="Alerta externo empresa B",
        )
        return composicao_a, composicao_b, producao_a, producao_b, ordem_a, ordem_b, sla_a, sla_b, alerta_b

    def test_composicoes_producoes_ordens_sla_e_exportacoes_respeitam_empresa(self):
        composicao_a, _, producao_a, _, ordem_a, _, sla_a, _, _ = self._dados_producao_multiempresa()

        composicoes = self.client.get("/estoque/composicoes/")
        relatorio = self.client.get("/estoque/composicoes/producoes/relatorio/")
        ordens = self.client.get("/estoque/composicoes/ordens/")
        fila = self.client.get("/estoque/composicoes/ordens/fila/")
        slas = self.client.get("/estoque/composicoes/slas-setor/")
        csv_composicoes = self.client.get("/estoque/composicoes/exportar.csv").content.decode("utf-8-sig")
        csv_producoes = self.client.get("/estoque/composicoes/producoes/relatorio/exportar.csv").content.decode("utf-8-sig")
        csv_ordens = self.client.get("/estoque/composicoes/ordens/exportar.csv").content.decode("utf-8-sig")

        self.assertEqual({item.pk for item in composicoes.context["composicoes"]}, {composicao_a.pk})
        self.assertEqual({item.pk for item in relatorio.context["producoes"]}, {producao_a.pk})
        self.assertEqual({item.pk for item in ordens.context["ordens"]}, {ordem_a.pk})
        self.assertContains(fila, "Setor empresa A")
        self.assertNotContains(fila, "Setor empresa B")
        self.assertEqual({item.pk for item in slas.context["configuracoes"]}, {sla_a.pk})
        self.assertIn("Estoque A", csv_composicoes)
        self.assertNotIn("Estoque B", csv_composicoes)
        self.assertIn("Producao empresa A", csv_producoes)
        self.assertNotIn("Producao empresa B", csv_producoes)
        self.assertIn("Ordem empresa A", csv_ordens)
        self.assertNotIn("Ordem empresa B", csv_ordens)

    def test_ids_externos_de_producao_ordem_sla_e_alerta_retornam_404(self):
        _, composicao_b, _, producao_b, _, ordem_b, _, sla_b, alerta_b = self._dados_producao_multiempresa()

        verificacoes = [
            self.client.get(f"/estoque/composicoes/{composicao_b.pk}/"),
            self.client.get(f"/estoque/composicoes/{composicao_b.pk}/editar/"),
            self.client.post(f"/estoque/composicoes/{composicao_b.pk}/produzir/"),
            self.client.post(f"/estoque/composicoes/producoes/{producao_b.pk}/cancelar/"),
            self.client.get(f"/estoque/composicoes/ordens/{ordem_b.pk}/imprimir/"),
            self.client.post(f"/estoque/composicoes/ordens/{ordem_b.pk}/etapa/", {"etapa_operacional": "SEPARACAO"}),
            self.client.post(f"/estoque/composicoes/ordens/{ordem_b.pk}/confirmar/"),
            self.client.post(f"/estoque/composicoes/ordens/{ordem_b.pk}/cancelar/"),
            self.client.get(f"/estoque/composicoes/slas-setor/{sla_b.pk}/editar/"),
            self.client.post(f"/estoque/composicoes/alertas-sla/{alerta_b.pk}/visualizar/"),
        ]

        self.assertTrue(all(resposta.status_code == 404 for resposta in verificacoes))
        ordem_b.refresh_from_db()
        producao_b.refresh_from_db()
        self.assertEqual(ordem_b.status, StatusOrdemProducaoComposicao.PLANEJADA)
        self.assertEqual(producao_b.status, StatusProducaoComposicao.CONFIRMADO)

    def test_formularios_de_producao_rejeitam_empresa_filial_e_responsavel_externos(self):
        _, composicao_b, _, _, _, _, _, _, _ = self._dados_producao_multiempresa()

        ordem = self.client.post(
            "/estoque/composicoes/ordens/nova/",
            {
                "composicao": composicao_b.pk,
                "filial": self.filial_b.pk,
                "quantidade_planejada": "1.000",
                "data_programada": timezone.localdate().isoformat(),
                "prioridade": "NORMAL",
                "etapa_operacional": "AGUARDANDO",
                "responsavel_operacional": self.usuario_b.pk,
                "motivo": "Ordem forjada",
            },
        )
        sla = self.client.post(
            "/estoque/composicoes/slas-setor/nova/",
            {
                "empresa": self.empresa_b.pk,
                "filial": self.filial_b.pk,
                "setor": "SLA forjado",
                "meta_minutos": 30,
                "is_active": "on",
            },
        )
        composicao = self.client.post(
            "/estoque/composicoes/nova/",
            {
                "empresa": self.empresa_b.pk,
                "filial": self.filial_b.pk,
                "produto_final": self.destino.pk,
                "quantidade_final": "1.000",
                "tipo": TipoDesmembramentoProduto.KIT,
                "is_active": "on",
                "componentes-TOTAL_FORMS": "1",
                "componentes-INITIAL_FORMS": "0",
                "componentes-MIN_NUM_FORMS": "1",
                "componentes-MAX_NUM_FORMS": "1000",
                "componentes-0-produto_componente": self.produto.pk,
                "componentes-0-quantidade": "1.000",
            },
        )

        self.assertIn("composicao", ordem.context["form"].errors)
        self.assertIn("filial", ordem.context["form"].errors)
        self.assertIn("responsavel_operacional", ordem.context["form"].errors)
        self.assertIn("empresa", sla.context["form"].errors)
        self.assertIn("filial", sla.context["form"].errors)
        self.assertIn("empresa", composicao.context["form"].errors)
        self.assertIn("filial", composicao.context["form"].errors)
        self.assertFalse(OrdemProducaoComposicao.objects.filter(motivo="Ordem forjada").exists())
        self.assertFalse(ConfiguracaoSLASetorProducao.objects.filter(setor="SLA forjado").exists())
    def test_superadmin_mantem_visao_global(self):
        superadmin = get_user_model().objects.create_superuser("estoque_master", "master@example.com", "123")
        self.client.force_login(superadmin)

        estoque = self.client.get("/estoque/")
        detalhe = self.client.get(f"/estoque/inventarios/{self.inventario_b.pk}/")

        self.assertEqual({item.pk for item in estoque.context["estoques"]}, {self.estoque_a.pk, self.estoque_b.pk})
        self.assertEqual(detalhe.status_code, 200)
