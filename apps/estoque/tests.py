from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase

from apps.auditoria.models import LogAuditoria
from apps.empresas.models import Empresa, Filial
from apps.estoque.models import (
    ComposicaoProduto,
    DesmembramentoProduto,
    Estoque,
    ItemComposicaoProduto,
    MovimentacaoEstoque,
    PerdaEstoque,
    ProducaoComposicaoProduto,
    ReceitaDesmembramento,
    StatusDesmembramentoProduto,
    StatusProducaoComposicao,
    TipoDesmembramentoProduto,
    TipoMovimentacaoEstoque,
    TipoSaidaDesmembramento,
)
from apps.estoque.services import (
    cancelar_desmembramento_produto,
    cancelar_producao_composicao,
    confirmar_desmembramento_multidestino,
    confirmar_desmembramento_simples,
    confirmar_producao_composicao,
    simular_desmembramento_simples,
)
from apps.produtos.models import Categoria, Produto


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
            nome="Corte baixo relatorio",
            categoria=self.categoria,
            preco_custo="0.00",
            preco_venda="19.00",
        )
        destino_ok = Produto.objects.create(
            codigo_barras="7893333333324",
            nome="Corte ok relatorio",
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
            motivo="Relatorio abaixo",
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
            motivo="Relatorio ok",
            tipo="ACOUGUE",
        )

        pagina = self.client.get("/estoque/desmembramentos/relatorio/", {"alerta": "abaixo"})
        csv_response = self.client.get("/estoque/desmembramentos/relatorio/exportar.csv", {"alerta": "abaixo"})

        self.assertEqual(pagina.status_code, 200)
        self.assertContains(pagina, "Relatorio de rendimento")
        self.assertContains(pagina, "rendimento-chart-data")
        self.assertContains(pagina, "rendimento-destinos-chart")
        self.assertContains(pagina, "rendimento-custos-chart")
        self.assertContains(pagina, "rendimento-alertas-chart")
        self.assertContains(pagina, "Corte baixo relatorio")
        self.assertContains(pagina, "Abaixo do esperado")
        self.assertNotContains(pagina, "Corte ok relatorio")
        self.assertEqual(csv_response.status_code, 200)
        conteudo = csv_response.content.decode("utf-8-sig")
        self.assertIn("Diferenca %", conteudo)
        self.assertIn("Corte baixo relatorio", conteudo)
        self.assertIn("Abaixo do esperado", conteudo)
        self.assertNotIn("Corte ok relatorio", conteudo)

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
        Estoque.objects.create(produto=componente, filial=self.filial, quantidade_atual=Decimal("1.000"))

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
        self.assertContains(lista, "Composicoes")
        self.assertContains(form, "Nova composicao")
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
        self.assertContains(response, "Visao operacional")
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
                motivo="Tentativa invalida",
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
        self.assertEqual(DesmembramentoProduto.objects.count(), 0)
        self.assertEqual(MovimentacaoEstoque.objects.count(), 0)

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
        self.assertContains(lista, "Relatorio de rendimento")
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
        self.assertContains(response, "Previa da operacao")
        self.assertContains(response, "Estoque suficiente para confirmar")
        self.assertEqual(DesmembramentoProduto.objects.count(), 0)
        self.assertEqual(MovimentacaoEstoque.objects.count(), 0)

    def test_post_simular_desmembramento_com_multiplos_destinos(self):
        destino_a = Produto.objects.create(
            codigo_barras="7896767676701",
            nome="Corte simulado A",
            categoria=self.categoria,
            preco_custo="0.00",
            preco_venda="12.00",
        )
        destino_b = Produto.objects.create(
            codigo_barras="7896767676702",
            nome="Apara simulada",
            categoria=self.categoria,
            preco_custo="0.00",
            preco_venda="4.00",
        )
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
                "observacao": "Pacote padrao com trinta unidades",
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
        self.assertContains(response, "1,000 -> 30,000")
        self.assertContains(response, f"/estoque/desmembramentos/novo/?receita={receita.id}")

    def test_tela_receita_desmembramento_usa_busca_remota_de_produtos(self):
        response = self.client.get("/estoque/receitas-desmembramento/nova/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Conversao padrao")
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
