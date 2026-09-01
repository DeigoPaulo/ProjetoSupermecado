from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import PerfilUsuario, TipoPerfil
from apps.auditoria.models import LogAuditoria
from apps.compras.models import CotacaoCompra, StatusCotacaoCompra
from apps.empresas.models import Empresa, Filial
from apps.estoque.models import Estoque
from apps.financeiro.models import ContaFinanceira
from apps.produtos.models import Categoria, Produto


class CotacaoSugestaoReposicaoTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(
            razao_social="Mercado Reposição",
            nome_fantasia="Mercado Reposição",
            cnpj="12345678000190",
        )
        self.filial = Filial.objects.create(empresa=self.empresa, nome="Matriz Reposição")
        self.usuario = get_user_model().objects.create_user("gerente_reposicao", password="senha")
        PerfilUsuario.objects.create(usuario=self.usuario, filial=self.filial, tipo=TipoPerfil.GERENTE)
        categoria = Categoria.objects.create(nome="Mercearia Reposição")
        self.produto = Produto.objects.create(
            codigo_barras="7891000099991",
            nome="Arroz reposição",
            categoria=categoria,
            preco_custo=Decimal("10.00"),
            preco_venda=Decimal("15.00"),
            estoque_minimo=Decimal("10.000"),
        )
        self.estoque = Estoque.objects.create(
            produto=self.produto,
            filial=self.filial,
            quantidade_atual=Decimal("2.000"),
        )
        self.url = reverse("relatorios:criar_cotacao_sugestao_reposicao")
        self.dados = {
            "data_inicio": "2026-08-01",
            "data_fim": "2026-08-31",
            "dias_cobertura": "7",
            "filial": str(self.filial.pk),
            "produto": [str(self.produto.pk)],
        }

    def test_cria_rascunho_idempotente_sem_impacto_operacional(self):
        self.client.force_login(self.usuario)
        saldo_antes = self.estoque.quantidade_atual
        contas_antes = ContaFinanceira.objects.count()

        response = self.client.post(self.url, self.dados)

        self.assertEqual(response.status_code, 302)
        cotacao = CotacaoCompra.objects.get()
        self.assertEqual(cotacao.status, StatusCotacaoCompra.RASCUNHO)
        self.assertEqual(cotacao.filial, self.filial)
        self.assertEqual(cotacao.itens.get().produto, self.produto)
        self.assertEqual(cotacao.itens.get().quantidade, Decimal("8.000"))
        self.estoque.refresh_from_db()
        self.assertEqual(self.estoque.quantidade_atual, saldo_antes)
        self.assertEqual(ContaFinanceira.objects.count(), contas_antes)
        self.assertEqual(
            LogAuditoria.objects.filter(acao="CRIACAO_COTACAO_REPOSICAO", objeto_id=str(cotacao.pk)).count(),
            1,
        )

        repeticao = self.client.post(self.url, self.dados)
        self.assertEqual(repeticao.status_code, 302)
        self.assertEqual(CotacaoCompra.objects.count(), 1)
        self.assertEqual(LogAuditoria.objects.filter(acao="CRIACAO_COTACAO_REPOSICAO").count(), 1)

    def test_recusa_produto_de_outra_empresa(self):
        outra_empresa = Empresa.objects.create(
            razao_social="Mercado Externo",
            nome_fantasia="Mercado Externo",
            cnpj="11222333000144",
        )
        outra_filial = Filial.objects.create(empresa=outra_empresa, nome="Filial externa")
        outro_produto = Produto.objects.create(
            codigo_barras="7891000099992",
            nome="Produto externo",
            categoria=self.produto.categoria,
            preco_custo=Decimal("1.00"),
            preco_venda=Decimal("2.00"),
            estoque_minimo=Decimal("5.000"),
        )
        Estoque.objects.create(produto=outro_produto, filial=outra_filial, quantidade_atual=Decimal("0.000"))
        self.client.force_login(self.usuario)
        dados = {**self.dados, "produto": [str(self.produto.pk), str(outro_produto.pk)]}

        response = self.client.post(self.url, dados, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "fora da filial")
        self.assertFalse(CotacaoCompra.objects.exists())

    def test_compras_visualiza_acao_e_financeiro_apenas_consulta(self):
        self.client.force_login(self.usuario)
        pagina = self.client.get(
            reverse("relatorios:sugestao_reposicao"),
            {"filial": self.filial.pk, "data_inicio": "2026-08-01", "data_fim": "2026-08-31"},
        )
        self.assertEqual(pagina.status_code, 200)
        self.assertContains(pagina, "Criar cotação em rascunho")
        self.assertContains(pagina, f'value="{self.produto.pk}"')

        financeiro = get_user_model().objects.create_user("financeiro_reposicao", password="senha")
        PerfilUsuario.objects.create(usuario=financeiro, filial=self.filial, tipo=TipoPerfil.FINANCEIRO)
        self.client.force_login(financeiro)
        consulta = self.client.get(
            reverse("relatorios:sugestao_reposicao"),
            {"filial": self.filial.pk, "data_inicio": "2026-08-01", "data_fim": "2026-08-31"},
        )
        self.assertEqual(consulta.status_code, 200)
        self.assertNotContains(consulta, "Criar cotação em rascunho")
        bloqueio = self.client.post(self.url, self.dados)
        self.assertEqual(bloqueio.status_code, 403)
        self.assertFalse(CotacaoCompra.objects.exists())
