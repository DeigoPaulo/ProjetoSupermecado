from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.core_gtin import gtin_fiscal
from apps.pdv.views import _resolver_produto_por_busca

from .forms import ProdutoForm
from .models import Categoria, CodigoBarrasProduto, Produto


class ProdutoEanOpcionalTests(TestCase):
    def setUp(self):
        self.categoria = Categoria.objects.create(nome="Teste de EAN")
        self.user = get_user_model().objects.create_superuser("ean-admin", "ean@example.com", "teste")
        self.client.force_login(self.user)

    def dados(self, **overrides):
        data = {
            "codigo_barras": "",
            "codigo_interno": "",
            "nome": "Produto de teste",
            "categoria": self.categoria.pk,
            "unidade": "UN",
            "preco_custo": "1.00",
            "preco_venda": "2.00",
            "estoque_minimo": "0",
            "is_active": "on",
            "vendido_no_pdv": "on",
            "galeria-TOTAL_FORMS": "0",
            "galeria-INITIAL_FORMS": "0",
            "galeria-MIN_NUM_FORMS": "0",
            "galeria-MAX_NUM_FORMS": "1000",
        }
        data.update(overrides)
        return data

    def produto(self, *, ean="", nome="Produto", codigo_interno=""):
        return Produto.objects.create(
            codigo_barras=ean,
            codigo_interno=codigo_interno,
            nome=nome,
            categoria=self.categoria,
            preco_custo=Decimal("1.00"),
            preco_venda=Decimal("2.00"),
        )

    def test_formulario_aceita_ean_vazio_sem_required_html(self):
        form = ProdutoForm(data=self.dados())
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["codigo_barras"], "")
        self.assertFalse(form.fields["codigo_barras"].required)
        self.assertNotIn("required", str(form["codigo_barras"]))

    def test_campos_obrigatorios_continuam_obrigatorios(self):
        form = ProdutoForm(data=self.dados(nome="", preco_venda=""))
        self.assertFalse(form.is_valid())
        self.assertIn("nome", form.errors)
        self.assertIn("preco_venda", form.errors)
        self.assertNotIn("codigo_barras", form.errors)
        self.assertTrue(form.fields["categoria"].required)
        self.assertFalse(form.fields["marca"].required)

    def test_aceita_gtin_valido_e_rejeita_formatos_invalidos(self):
        for codigo in ("96385074", "012345678905", "7894900704099", "10012345000017"):
            with self.subTest(codigo=codigo):
                form = ProdutoForm(data=self.dados(codigo_barras=codigo))
                self.assertTrue(form.is_valid(), form.errors)
        for codigo in ("10070247", "123456789", "7894900704098", "ABC4900704099"):
            with self.subTest(invalido=codigo):
                form = ProdutoForm(data=self.dados(codigo_barras=codigo))
                self.assertFalse(form.is_valid())
                self.assertIn("EAN/GTIN inválido", str(form.errors["codigo_barras"]))

    def test_duplicidade_principal_e_adicional_mostra_erro_especifico(self):
        primeiro = self.produto(ean="7894900704099")
        form = ProdutoForm(data=self.dados(codigo_barras="7894900704099"))
        self.assertFalse(form.is_valid())
        self.assertIn("Este EAN/GTIN já está cadastrado em outro produto.", form.errors["codigo_barras"])
        CodigoBarrasProduto.objects.create(produto=primeiro, codigo="96385074")
        adicional = ProdutoForm(data=self.dados(codigo_barras="96385074"))
        self.assertFalse(adicional.is_valid())
        self.assertIn("Este EAN/GTIN já está cadastrado em outro produto.", adicional.errors["codigo_barras"])

    def test_dois_produtos_sem_ean_e_unicidade_de_ean_real(self):
        self.produto(nome="Primeiro")
        self.produto(nome="Segundo")
        self.assertEqual(Produto.objects.filter(codigo_barras="").count(), 2)
        self.produto(ean="7894900704099", nome="Com EAN")
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.produto(ean="7894900704099", nome="EAN duplicado")

    def test_novo_produto_exibe_rotulos_modal_e_campos_visiveis(self):
        response = self.client.get("/produtos/novo/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "EAN/GTIN principal")
        self.assertContains(response, "(opcional)")
        self.assertContains(response, "Voltar e informar EAN")
        self.assertContains(response, "Cadastrar sem EAN")
        self.assertContains(response, "Este campo é obrigatório.")
        self.assertNotIn("required", str(response.context["form"]["codigo_barras"]))

    def test_post_sem_ean_exige_confirmacao_no_servidor(self):
        response = self.client.post("/produtos/novo/", self.dados())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Produto.objects.count(), 0)
        self.assertContains(response, "Confirme o cadastro sem EAN/GTIN antes de salvar.")
        self.assertContains(response, 'data-form-error-summary')

    def test_post_confirmado_salva_sem_ean_e_gera_codigo_interno(self):
        response = self.client.post("/produtos/novo/", self.dados(confirmar_sem_ean="1"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/produtos/")
        produto = Produto.objects.get()
        self.assertEqual(produto.codigo_barras, "")
        self.assertTrue(produto.codigo_interno)

    def test_codigo_interno_informado_nao_substitui_ean(self):
        response = self.client.post(
            "/produtos/novo/", self.dados(codigo_interno="10070246", confirmar_sem_ean="1")
        )
        self.assertEqual(response.status_code, 302)
        produto = Produto.objects.get()
        self.assertEqual(produto.codigo_interno, "10070246")
        self.assertEqual(produto.codigo_barras, "")

    def test_ean_valido_salva_sem_confirmacao(self):
        response = self.client.post("/produtos/novo/", self.dados(codigo_barras="7894900704099"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/produtos/")
        self.assertEqual(Produto.objects.get().codigo_barras, "7894900704099")

    def test_post_ean_duplicado_mostra_erro_no_campo(self):
        self.produto(ean="7894900704099")
        response = self.client.post("/produtos/novo/", self.dados(codigo_barras="7894900704099"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Produto.objects.count(), 1)
        self.assertContains(response, "Este EAN/GTIN já está cadastrado em outro produto.")
        self.assertContains(response, 'data-form-error-summary')

    def test_ean_invalido_e_campos_vazios_exibem_todos_os_erros(self):
        response = self.client.post(
            "/produtos/novo/", self.dados(codigo_barras="10070247", nome="", preco_venda="")
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Produto.objects.count(), 0)
        self.assertContains(response, "EAN/GTIN inválido")
        self.assertIn("nome", response.context["form"].errors)
        self.assertIn("preco_venda", response.context["form"].errors)
        self.assertContains(response, 'data-form-error-summary')

    def test_busca_pdv_por_ean_codigo_interno_e_nome(self):
        sem_ean = self.produto(nome="Sem código de barras", codigo_interno="SEM-EAN-01")
        com_ean = self.produto(ean="7894900704099", nome="Com código")
        for termo in ("SEM-EAN-01", "Sem código"):
            encontrado, _, _ = _resolver_produto_por_busca(termo)
            self.assertEqual(encontrado, sem_ean)
        encontrado, _, _ = _resolver_produto_por_busca("7894900704099")
        self.assertEqual(encontrado, com_ean)

    def test_saida_fiscal_sem_gtin_e_com_gtin(self):
        sem_ean = self.produto(codigo_interno="SEM-EAN-01")
        com_ean = self.produto(ean="7894900704099")
        self.assertEqual(gtin_fiscal(sem_ean.codigo_barras), "SEM GTIN")
        self.assertEqual(gtin_fiscal(com_ean.codigo_barras), "7894900704099")
