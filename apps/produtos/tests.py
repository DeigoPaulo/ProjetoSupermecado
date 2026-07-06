from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from PIL import Image

from .models import Categoria, Produto, ProdutoImagem


GIF_1X1 = (
    b"GIF87a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04"
    b"\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)


def png_1x1():
    arquivo = BytesIO()
    Image.new("RGB", (1, 1), color="white").save(arquivo, format="PNG")
    return arquivo.getvalue()


class ProdutoViewsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser("admin", "admin@example.com", "123")
        self.client = Client(HTTP_HOST="localhost")
        self.client.force_login(self.user)
        self.categoria = Categoria.objects.create(nome="Mercearia")
        self.produto = Produto.objects.create(
            codigo_barras="7891234567890",
            nome="Arroz",
            categoria=self.categoria,
            preco_custo=Decimal("10.00"),
            preco_venda=Decimal("15.00"),
            ncm="10063021",
            origem_mercadoria="0",
            cst_icms="00",
            aliquota_icms=Decimal("18.00"),
        )

    def test_form_produto_exibe_secoes_operacionais(self):
        response = self.client.get(f"/produtos/{self.produto.pk}/editar/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Identificacao")
        self.assertContains(response, "Precos e estoque")
        self.assertContains(response, "Venda e imagem")
        self.assertContains(response, "Dados fiscais")
        self.assertContains(response, "Obrigatorio para NFC-e")
        self.assertContains(response, "select2-field")
        self.assertContains(response, "Imagem para marketplace")
        self.assertContains(response, "Sem imagem cadastrada")
        self.assertContains(response, "Galeria adicional")
        self.assertContains(response, 'name="galeria-TOTAL_FORMS"')

    def test_edicao_salva_dados_da_galeria(self):
        imagem = SimpleUploadedFile(
            "frente.png",
            png_1x1(),
            content_type="image/png",
        )
        response = self.client.post(
            f"/produtos/{self.produto.pk}/editar/",
            {
                "codigo_barras": self.produto.codigo_barras,
                "nome": self.produto.nome,
                "categoria": self.categoria.pk,
                "unidade": "UN",
                "preco_custo": "10.00",
                "preco_venda": "15.00",
                "estoque_minimo": "0",
                "vendido_no_pdv": "on",
                "ncm": "10063021",
                "origem_mercadoria": "0",
                "cst_icms": "00",
                "aliquota_icms": "18.00",
                "is_active": "on",
                "galeria-TOTAL_FORMS": "3",
                "galeria-INITIAL_FORMS": "0",
                "galeria-MIN_NUM_FORMS": "0",
                "galeria-MAX_NUM_FORMS": "1000",
                "galeria-0-imagem": imagem,
                "galeria-0-legenda": "Frente da embalagem",
                "galeria-0-ordem": "2",
                "galeria-1-legenda": "",
                "galeria-1-ordem": "0",
                "galeria-2-legenda": "",
                "galeria-2-ordem": "0",
            },
        )

        self.assertRedirects(response, "/produtos/")
        foto = ProdutoImagem.objects.get(produto=self.produto)
        self.assertEqual(foto.legenda, "Frente da embalagem")
        self.assertEqual(foto.ordem, 2)

    def test_produto_e_galeria_aceitam_png_e_bloqueiam_gif(self):
        imagem_png = SimpleUploadedFile("produto.png", png_1x1(), content_type="image/png")
        resposta_png = self.client.post(
            "/produtos/novo/",
            {
                "codigo_barras": "7890000000100",
                "nome": "Produto com imagem",
                "categoria": self.categoria.pk,
                "unidade": "UN",
                "preco_custo": "1.00",
                "preco_venda": "2.00",
                "estoque_minimo": "0",
                "vendido_no_pdv": "on",
                "ncm": "10063021",
                "origem_mercadoria": "0",
                "cst_icms": "00",
                "aliquota_icms": "18.00",
                "is_active": "on",
                "galeria-TOTAL_FORMS": "3",
                "galeria-INITIAL_FORMS": "0",
                "galeria-MIN_NUM_FORMS": "0",
                "galeria-MAX_NUM_FORMS": "1000",
                "galeria-0-legenda": "",
                "galeria-0-ordem": "0",
                "galeria-1-legenda": "",
                "galeria-1-ordem": "0",
                "galeria-2-legenda": "",
                "galeria-2-ordem": "0",
                "imagem": imagem_png,
            },
        )

        self.assertRedirects(resposta_png, "/produtos/")
        self.assertTrue(Produto.objects.filter(codigo_barras="7890000000100", imagem__endswith=".png").exists())

        imagem_gif = SimpleUploadedFile("produto.gif", GIF_1X1, content_type="image/gif")
        resposta_gif = self.client.post(
            "/produtos/novo/",
            {
                "codigo_barras": "7890000000101",
                "nome": "Produto gif",
                "categoria": self.categoria.pk,
                "unidade": "UN",
                "preco_custo": "1.00",
                "preco_venda": "2.00",
                "estoque_minimo": "0",
                "vendido_no_pdv": "on",
                "ncm": "10063021",
                "origem_mercadoria": "0",
                "cst_icms": "00",
                "aliquota_icms": "18.00",
                "is_active": "on",
                "galeria-TOTAL_FORMS": "3",
                "galeria-INITIAL_FORMS": "0",
                "galeria-MIN_NUM_FORMS": "0",
                "galeria-MAX_NUM_FORMS": "1000",
                "galeria-0-legenda": "",
                "galeria-0-ordem": "0",
                "galeria-1-legenda": "",
                "galeria-1-ordem": "0",
                "galeria-2-legenda": "",
                "galeria-2-ordem": "0",
                "imagem": imagem_gif,
            },
        )

        self.assertEqual(resposta_gif.status_code, 200)
        self.assertContains(resposta_gif, "Envie uma imagem PNG, JPG ou JPEG.")
        self.assertFalse(Produto.objects.filter(codigo_barras="7890000000101").exists())

    def test_lista_produtos_renderiza_imagem_com_url_absoluta_de_media(self):
        self.produto.imagem.save("produto-lista.png", SimpleUploadedFile("produto-lista.png", png_1x1(), content_type="image/png"))

        response = self.client.get("/produtos/")

        self.assertContains(response, 'src="/media/produtos/')

    def test_lista_produtos_exibe_status_visual_de_marketplace(self):
        self.produto.vendido_no_marketplace = True
        self.produto.save(update_fields=["vendido_no_marketplace"])

        response = self.client.get("/produtos/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Marketplace")
        self.assertContains(response, "Sem imagem")
        self.assertContains(response, "product-thumb")

    def test_valida_ncm_e_cest(self):
        response = self.client.post(
            "/produtos/novo/",
            {
                "codigo_barras": "7890000000001",
                "nome": "Produto invalido",
                "categoria": self.categoria.pk,
                "unidade": "UN",
                "preco_custo": "1.00",
                "preco_venda": "2.00",
                "estoque_minimo": "0",
                "vendido_no_pdv": "on",
                "ncm": "123",
                "cest": "456",
                "aliquota_icms": "18.00",
                "is_active": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "NCM deve possuir 8 digitos.")
        self.assertContains(response, "CEST deve possuir 7 digitos.")

    def test_form_categoria_exibe_uso_operacional(self):
        response = self.client.get("/produtos/categorias/nova/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Categoria de produto")
        self.assertContains(response, "relatorios, reposicao, etiquetas e marketplace")

    def test_form_marca_exibe_uso_operacional(self):
        response = self.client.get("/produtos/marcas/nova/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Marca comercial")
        self.assertContains(response, "analise de vendas, etiquetas")
