from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.accounts.models import PerfilUsuario, TipoPerfil
from apps.empresas.models import Empresa, Filial
from apps.estoque.models import Estoque, MovimentacaoEstoque, TipoMovimentacaoEstoque
from apps.pdv.models import Caixa, Sangria, StatusCaixa, Suprimento
from apps.produtos.models import Categoria, Produto
from apps.vendas.models import (
    DevolucaoVenda,
    EstornoParcialPagamento,
    FormaPagamento,
    PagamentoVenda,
    StatusEstornoParcial,
    StatusVenda,
    Venda,
)


class DashboardTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.empresa = Empresa.objects.create(razao_social="Mercado Teste", nome_fantasia="Mercado Teste", cnpj="12345678000190")
        self.filial = Filial.objects.create(empresa=self.empresa, nome="Matriz")
        self.usuario = User.objects.create_user(username="gerente", password="senha")
        PerfilUsuario.objects.create(usuario=self.usuario, filial=self.filial, tipo=TipoPerfil.GERENTE)

    def test_dashboard_renderiza_graficos_gerenciais(self):
        categoria = Categoria.objects.create(nome="Mercearia")
        Produto.objects.create(codigo_barras="789100000001", nome="Arroz", categoria=categoria, preco_custo=Decimal("10"), preco_venda=Decimal("15"))
        caixa = Caixa.objects.create(filial=self.filial, usuario_abertura=self.usuario, valor_inicial=Decimal("100"))
        forma = FormaPagamento.objects.create(nome="Pix", tipo="PIX")
        venda = Venda.objects.create(
            filial=self.filial,
            caixa=caixa,
            usuario=self.usuario,
            total_bruto=Decimal("15"),
            total_liquido=Decimal("15"),
            status=StatusVenda.FINALIZADA,
        )
        PagamentoVenda.objects.create(venda=venda, forma_pagamento=forma, valor=Decimal("15"))
        self.client.force_login(self.usuario)

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "dashboard-chart-data")
        self.assertContains(response, "dashboard-payments-chart")
        self.assertContains(response, "dashboard-categories-chart")
        self.assertContains(response, "dashboard-boxes-chart")

    def test_dashboard_isola_empresa_e_permite_filtro_de_filial(self):
        User = get_user_model()
        filial_centro = Filial.objects.create(empresa=self.empresa, nome="Filial Centro")
        empresa_externa = Empresa.objects.create(
            razao_social="Rede Externa Ltda",
            nome_fantasia="Rede Externa",
            cnpj="11222333000144",
        )
        filial_externa = Filial.objects.create(empresa=empresa_externa, nome="Matriz Externa")
        operador_centro = User.objects.create_user("operador_dashboard_centro", password="senha")
        operador_externo = User.objects.create_user("operador_dashboard_externo", password="senha")
        categoria = Categoria.objects.create(nome="Dashboard categoria")
        produto_matriz = Produto.objects.create(
            codigo_barras="789200000001", nome="Produto Matriz", categoria=categoria,
            preco_custo=Decimal("5"), preco_venda=Decimal("10"),
        )
        produto_centro = Produto.objects.create(
            codigo_barras="789200000002", nome="Produto Centro", categoria=categoria,
            preco_custo=Decimal("10"), preco_venda=Decimal("30"),
        )
        produto_externo = Produto.objects.create(
            codigo_barras="789200000003", nome="Produto Externo", categoria=categoria,
            preco_custo=Decimal("100"), preco_venda=Decimal("900"),
        )
        Estoque.objects.create(produto=produto_matriz, filial=self.filial, quantidade_atual=Decimal("10"))
        Estoque.objects.create(produto=produto_centro, filial=filial_centro, quantidade_atual=Decimal("20"))
        Estoque.objects.create(produto=produto_externo, filial=filial_externa, quantidade_atual=Decimal("30"))
        caixa_matriz = Caixa.objects.create(
            filial=self.filial, usuario_abertura=self.usuario, valor_inicial=Decimal("100")
        )
        caixa_centro = Caixa.objects.create(
            filial=filial_centro, usuario_abertura=operador_centro, valor_inicial=Decimal("200")
        )
        caixa_externo = Caixa.objects.create(
            filial=filial_externa, usuario_abertura=operador_externo, valor_inicial=Decimal("900")
        )
        forma = FormaPagamento.objects.create(nome="Pix Dashboard", tipo="PIX")
        for filial, caixa, usuario, valor in [
            (self.filial, caixa_matriz, self.usuario, Decimal("10")),
            (filial_centro, caixa_centro, operador_centro, Decimal("30")),
            (filial_externa, caixa_externo, operador_externo, Decimal("900")),
        ]:
            venda = Venda.objects.create(
                filial=filial, caixa=caixa, usuario=usuario,
                total_bruto=valor, total_liquido=valor, status=StatusVenda.FINALIZADA,
            )
            PagamentoVenda.objects.create(venda=venda, forma_pagamento=forma, valor=valor)
        self.client.force_login(self.usuario)

        gerente = self.client.get("/")
        self.assertEqual(gerente.context["faturamento"], Decimal("10"))
        self.assertEqual(gerente.context["total_produtos"], 1)
        self.assertNotContains(gerente, "operador_dashboard_centro")
        self.assertNotContains(gerente, "operador_dashboard_externo")

        perfil = self.usuario.perfil_supermercado
        perfil.tipo = TipoPerfil.ADMINISTRADOR
        perfil.save(update_fields=["tipo"])
        consolidado = self.client.get("/")
        centro = self.client.get(f"/?filial={filial_centro.pk}")
        externa = self.client.get(f"/?filial={filial_externa.pk}")

        self.assertEqual(consolidado.context["faturamento"], Decimal("40"))
        self.assertEqual(consolidado.context["total_produtos"], 2)
        self.assertContains(consolidado, "operador_dashboard_centro")
        self.assertNotContains(consolidado, "operador_dashboard_externo")
        self.assertEqual(centro.context["faturamento"], Decimal("30"))
        self.assertEqual(centro.context["total_produtos"], 1)
        self.assertEqual(externa.status_code, 403)

    def test_relatorio_caixas_filtra_e_resume_por_operador(self):
        User = get_user_model()
        operador_a = User.objects.create_user(username="caixa_maria", password="senha")
        operador_b = User.objects.create_user(username="caixa_joao", password="senha")
        caixa_a = Caixa.objects.create(
            filial=self.filial,
            usuario_abertura=operador_a,
            valor_inicial=Decimal("100"),
            valor_final=Decimal("180"),
            valor_conferido=Decimal("180"),
            status=StatusCaixa.CONFERIDO,
        )
        Caixa.objects.create(filial=self.filial, usuario_abertura=operador_b, valor_inicial=Decimal("50"))
        venda = Venda.objects.create(
            filial=self.filial,
            caixa=caixa_a,
            usuario=operador_a,
            total_bruto=Decimal("80"),
            total_liquido=Decimal("80"),
            status=StatusVenda.FINALIZADA,
        )
        forma = FormaPagamento.objects.create(nome="Dinheiro", tipo="DINHEIRO")
        pagamento = PagamentoVenda.objects.create(
            venda=venda, forma_pagamento=forma, valor=Decimal("80")
        )
        devolucao = DevolucaoVenda.objects.create(
            venda=venda,
            usuario=operador_a,
            motivo="Devolucao parcial",
            valor_total=Decimal("5"),
        )
        EstornoParcialPagamento.objects.create(
            pagamento=pagamento,
            devolucao=devolucao,
            valor=Decimal("5"),
            status=StatusEstornoParcial.CONFIRMADO,
            motivo="Produto devolvido",
        )
        Sangria.objects.create(caixa=caixa_a, usuario=operador_a, valor=Decimal("20"), motivo="Retirada parcial")
        Suprimento.objects.create(caixa=caixa_a, usuario=operador_a, valor=Decimal("15"), motivo="Troco inicial extra")
        self.client.force_login(self.usuario)

        url = f"/caixas/?operador={operador_a.pk}"
        response = self.client.get(url)
        csv_response = self.client.get(f"/caixas/exportar.csv?operador={operador_a.pk}")
        imprimir = self.client.get(f"/caixas/imprimir/?operador={operador_a.pk}")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Resumo por operador/funcionario")
        self.assertContains(response, "caixa_maria")
        self.assertContains(response, "R$ 80,00")
        self.assertContains(response, "R$ 100,00")
        self.assertContains(response, "Diferença conferida")
        self.assertContains(response, "R$ 0,00")
        self.assertNotContains(response, "R$ 50,00")
        self.assertContains(csv_response, "Filtro operador;caixa_maria")
        self.assertContains(csv_response, "Resumo por operador")
        self.assertContains(csv_response, "Total vendas;Sangrias;Suprimentos;Saldo operacional")
        self.assertContains(csv_response, "80,00;20,00;15,00;75,00")
        self.assertContains(imprimir, "Operador: caixa_maria")
        self.assertContains(imprimir, "Saldo operacional")
        self.assertContains(imprimir, "R$ 75,00")
        self.assertContains(response, "Entradas líquidas por forma de pagamento")
        self.assertEqual(response.context["total_entradas_pagamentos"], Decimal("75.00"))
        self.assertContains(csv_response, "Entradas liquidas por forma de pagamento")
        self.assertContains(csv_response, "Dinheiro;80,00;5,00;75,00")
        self.assertContains(imprimir, "Entradas líquidas por forma de pagamento")

    def test_relatorio_caixas_isola_empresa_e_filial_do_usuario(self):
        User = get_user_model()
        filial_mesma_empresa = Filial.objects.create(empresa=self.empresa, nome="Filial Centro")
        outra_empresa = Empresa.objects.create(
            razao_social="Mercado Externo Ltda",
            nome_fantasia="Mercado Externo",
            cnpj="98765432000199",
        )
        filial_externa = Filial.objects.create(empresa=outra_empresa, nome="Matriz Externa")
        operador_filial = User.objects.create_user(username="operador_filial_centro", password="senha")
        operador_externo = User.objects.create_user(username="operador_empresa_externa", password="senha")
        Caixa.objects.create(
            filial=filial_mesma_empresa,
            usuario_abertura=operador_filial,
            valor_inicial=Decimal("200"),
        )
        Caixa.objects.create(
            filial=filial_externa,
            usuario_abertura=operador_externo,
            valor_inicial=Decimal("900"),
        )
        self.client.force_login(self.usuario)

        gerente = self.client.get("/caixas/")
        tentativa_externa = self.client.get(f"/caixas/?operador={operador_externo.pk}")
        csv_externo = self.client.get(f"/caixas/exportar.csv?operador={operador_externo.pk}")
        pdf_externo = self.client.get(f"/caixas/imprimir/?operador={operador_externo.pk}")

        self.assertEqual(gerente.status_code, 200)
        self.assertNotContains(gerente, "operador_filial_centro")
        self.assertNotContains(gerente, "operador_empresa_externa")
        self.assertEqual(tentativa_externa.status_code, 403)
        self.assertEqual(csv_externo.status_code, 403)
        self.assertEqual(pdf_externo.status_code, 403)

        perfil = self.usuario.perfil_supermercado
        perfil.tipo = TipoPerfil.ADMINISTRADOR
        perfil.save(update_fields=["tipo"])
        administrador = self.client.get("/caixas/")

        self.assertContains(administrador, "operador_filial_centro")
        self.assertNotContains(administrador, "operador_empresa_externa")

        apenas_filial = self.client.get(f"/caixas/?filial={filial_mesma_empresa.pk}")
        apenas_matriz = self.client.get(f"/caixas/?filial={self.filial.pk}")
        csv_filial = self.client.get(f"/caixas/exportar.csv?filial={filial_mesma_empresa.pk}")
        pdf_filial = self.client.get(f"/caixas/imprimir/?filial={filial_mesma_empresa.pk}")
        filial_externa_tela = self.client.get(f"/caixas/?filial={filial_externa.pk}")
        filial_externa_csv = self.client.get(f"/caixas/exportar.csv?filial={filial_externa.pk}")
        filial_externa_pdf = self.client.get(f"/caixas/imprimir/?filial={filial_externa.pk}")

        self.assertContains(apenas_filial, "operador_filial_centro")
        self.assertNotContains(apenas_matriz, "operador_filial_centro")
        self.assertContains(csv_filial, "Filtro filial;Mercado Teste - Filial Centro")
        self.assertContains(pdf_filial, "Filial: Mercado Teste - Filial Centro")
        self.assertEqual(filial_externa_tela.status_code, 403)
        self.assertEqual(filial_externa_csv.status_code, 403)
        self.assertEqual(filial_externa_pdf.status_code, 403)

    def test_relatorio_vendas_isola_empresa_e_filtra_filial_em_todas_as_saidas(self):
        User = get_user_model()
        filial_centro = Filial.objects.create(empresa=self.empresa, nome="Filial Centro Vendas")
        empresa_externa = Empresa.objects.create(
            razao_social="Rede Vendas Externa Ltda",
            nome_fantasia="Rede Vendas Externa",
            cnpj="44555666000177",
        )
        filial_externa = Filial.objects.create(empresa=empresa_externa, nome="Matriz Externa Vendas")
        operador_centro = User.objects.create_user("operador_venda_centro", password="senha")
        operador_externo = User.objects.create_user("operador_venda_externo", password="senha")
        caixa_matriz = Caixa.objects.create(
            filial=self.filial, usuario_abertura=self.usuario, valor_inicial=Decimal("100")
        )
        caixa_centro = Caixa.objects.create(
            filial=filial_centro, usuario_abertura=operador_centro, valor_inicial=Decimal("100")
        )
        caixa_externo = Caixa.objects.create(
            filial=filial_externa, usuario_abertura=operador_externo, valor_inicial=Decimal("100")
        )
        for filial, caixa, usuario, valor in [
            (self.filial, caixa_matriz, self.usuario, Decimal("10")),
            (filial_centro, caixa_centro, operador_centro, Decimal("30")),
            (filial_externa, caixa_externo, operador_externo, Decimal("900")),
        ]:
            Venda.objects.create(
                filial=filial,
                caixa=caixa,
                usuario=usuario,
                total_bruto=valor,
                total_liquido=valor,
                status=StatusVenda.FINALIZADA,
            )
        self.client.force_login(self.usuario)

        gerente = self.client.get("/vendas/")
        gerente_csv = self.client.get("/vendas/exportar.csv")
        gerente_pdf = self.client.get("/vendas/imprimir/")

        self.assertEqual(gerente.status_code, 200)
        self.assertEqual(gerente.context["total_vendas"], 1)
        self.assertEqual(gerente.context["faturamento"], Decimal("10"))
        self.assertNotContains(gerente, "operador_venda_centro")
        self.assertNotContains(gerente, "operador_venda_externo")
        self.assertNotContains(gerente_csv, "operador_venda_centro")
        self.assertNotContains(gerente_pdf, "operador_venda_externo")

        perfil = self.usuario.perfil_supermercado
        perfil.tipo = TipoPerfil.ADMINISTRADOR
        perfil.save(update_fields=["tipo"])
        consolidado = self.client.get("/vendas/")
        centro = self.client.get(f"/vendas/?filial={filial_centro.pk}")
        centro_csv = self.client.get(f"/vendas/exportar.csv?filial={filial_centro.pk}")
        centro_pdf = self.client.get(f"/vendas/imprimir/?filial={filial_centro.pk}")

        self.assertEqual(consolidado.context["total_vendas"], 2)
        self.assertEqual(consolidado.context["faturamento"], Decimal("40"))
        self.assertContains(consolidado, "operador_venda_centro")
        self.assertNotContains(consolidado, "operador_venda_externo")
        self.assertEqual(centro.context["total_vendas"], 1)
        self.assertEqual(centro.context["faturamento"], Decimal("30"))
        self.assertContains(centro_csv, "Filtro filial;Mercado Teste - Filial Centro Vendas")
        self.assertContains(centro_pdf, "Filial: Mercado Teste - Filial Centro Vendas")

        for url in [
            f"/vendas/?filial={filial_externa.pk}",
            f"/vendas/exportar.csv?filial={filial_externa.pk}",
            f"/vendas/imprimir/?filial={filial_externa.pk}",
        ]:
            self.assertEqual(self.client.get(url).status_code, 403)
    def test_relatorios_restantes_bloqueiam_filial_de_outra_empresa(self):
        empresa_externa = Empresa.objects.create(
            razao_social="Empresa Externa Relatorios Ltda",
            nome_fantasia="Empresa Externa Relatorios",
            cnpj="77888999000100",
        )
        filial_externa = Filial.objects.create(empresa=empresa_externa, nome="Filial Externa Relatorios")
        filial_centro = Filial.objects.create(empresa=self.empresa, nome="Filial Centro Relatorios")
        rotas = [
            "/curva-abc/",
            "/curva-abc/exportar.csv",
            "/curva-abc/imprimir/",
            "/estoque-baixo/",
            "/estoque-baixo/exportar.csv",
            "/estoque-baixo/imprimir/",
            "/sugestao-reposicao/",
            "/sugestao-reposicao/exportar.csv",
            "/sugestao-reposicao/imprimir/",
            "/movimentacoes-estoque/",
            "/movimentacoes-estoque/exportar.csv",
            "/movimentacoes-estoque/imprimir/",
            "/perdas/",
            "/perdas/exportar.csv",
            "/perdas/imprimir/",
            "/devolucoes/",
            "/devolucoes/exportar.csv",
            "/devolucoes/imprimir/",
            "/relatorios/compras/",
            "/relatorios/compras/exportar.csv",
            "/relatorios/compras/imprimir/",
        ]
        self.client.force_login(self.usuario)

        for rota in rotas:
            with self.subTest(rota=rota, perfil="gerente"):
                self.assertEqual(self.client.get(rota).status_code, 200)
            separador = "&" if "?" in rota else "?"
            with self.subTest(rota=rota, perfil="filial_externa"):
                resposta = self.client.get(f"{rota}{separador}filial={filial_externa.pk}")
                self.assertEqual(resposta.status_code, 403)

        perfil = self.usuario.perfil_supermercado
        perfil.tipo = TipoPerfil.ADMINISTRADOR
        perfil.save(update_fields=["tipo"])
        rotas_web = [
            "/curva-abc/",
            "/estoque-baixo/",
            "/sugestao-reposicao/",
            "/movimentacoes-estoque/",
            "/perdas/",
            "/devolucoes/",
            "/relatorios/compras/",
        ]
        for rota in rotas_web:
            with self.subTest(rota=rota, perfil="administrador"):
                resposta = self.client.get(f"{rota}?filial={filial_centro.pk}")
                self.assertEqual(resposta.status_code, 200)
                self.assertEqual(resposta.context["filial_id"], str(filial_centro.pk))

    def test_relatorio_movimentacoes_formata_quantidades_no_padrao_brasileiro(self):
        categoria = Categoria.objects.create(nome="Hortifruti")
        produto = Produto.objects.create(
            codigo_barras="789100000002",
            nome="Maca",
            categoria=categoria,
            preco_custo=Decimal("2.00"),
            preco_venda=Decimal("5.00"),
        )
        MovimentacaoEstoque.objects.create(
            produto=produto,
            filial=self.filial,
            tipo=TipoMovimentacaoEstoque.ENTRADA,
            quantidade=Decimal("20.000"),
            usuario=self.usuario,
        )
        MovimentacaoEstoque.objects.create(
            produto=produto,
            filial=self.filial,
            tipo=TipoMovimentacaoEstoque.VENDA,
            quantidade=Decimal("1.250"),
            usuario=self.usuario,
        )
        self.client.force_login(self.usuario)

        response = self.client.get("/movimentacoes-estoque/")

        self.assertContains(response, "<strong>20</strong>", html=True)
        self.assertContains(response, "<strong>1,250</strong>", html=True)
        self.assertNotContains(response, "20,000")
