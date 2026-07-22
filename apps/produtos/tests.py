from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from PIL import Image

from apps.configuracoes.models import ConfiguracaoImpressao, ModeloEtiqueta, TipoDocumentoImpressao
from apps.empresas.models import Empresa

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
        self.assertContains(response, 'data-ajax-url="/produtos/categorias/busca.json"')
        self.assertContains(response, 'data-ajax-url="/produtos/marcas/busca.json"')

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

    def test_etiquetas_tem_modelos_e_busca_por_codigo_interno(self):
        self.produto.codigo_interno = "SKU-ARROZ-01"
        self.produto.save(update_fields=["codigo_interno"])

        response = self.client.get(
            "/produtos/etiquetas/",
            {"busca": "SKU-ARROZ-01", "modelo": "compacto", "quantidade_copias": "2"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Compacto gondola 110 x 30 mm")
        self.assertContains(response, "label-sheet-compacto")
        self.assertContains(response, "SKU SKU-ARROZ-01", count=2)
        self.assertContains(response, "Arroz", count=2)
        self.assertContains(response, "Bipe o codigo de barras")

    def test_etiqueta_profissional_aplica_configuracao_da_empresa(self):
        empresa = Empresa.objects.create(
            razao_social="Mercado Modelo Ltda",
            nome_fantasia="Mercado Modelo",
            cnpj="12345678000199",
        )
        ConfiguracaoImpressao.objects.create(
            empresa=empresa,
            tipo_documento=TipoDocumentoImpressao.ETIQUETA,
            largura_etiqueta_mm=Decimal("80.00"),
            altura_etiqueta_mm=Decimal("40.00"),
            gap_horizontal_mm=Decimal("3.00"),
            gap_vertical_mm=Decimal("4.00"),
            colunas_etiqueta=2,
            dpi_impressora=300,
            impressora_padrao="Zebra ZD421",
            linguagem_impressora="ZPL",
        )

        response = self.client.get(
            "/produtos/etiquetas/",
            {"busca": self.produto.codigo_barras, "modelo": "configurado", "quantidade_copias": "1"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Modelo profissional configurado")
        self.assertContains(response, "--label-width: 80.00mm")
        self.assertContains(response, "--label-height: 40.00mm")
        self.assertContains(response, "--label-columns: 2")
        self.assertContains(response, "Zebra ZD421")
        self.assertContains(response, "300 DPI")
        self.assertContains(response, "Imprimir direto")
        self.assertEqual(response.context["payload_etiquetas"]["linguagem"], "ZPL")
        self.assertEqual(response.context["payload_etiquetas"]["modelo"]["largura_mm"], 80.0)
        self.assertEqual(response.context["payload_etiquetas"]["itens"][0]["copias"], 1)

    def test_etiqueta_profissional_oferece_impressao_direta_ppla(self):
        empresa = Empresa.objects.create(
            razao_social="Mercado Argox Ltda",
            nome_fantasia="Mercado Argox",
            cnpj="12345678000198",
        )
        ConfiguracaoImpressao.objects.create(
            empresa=empresa,
            tipo_documento=TipoDocumentoImpressao.ETIQUETA,
            largura_etiqueta_mm=Decimal("80.00"),
            altura_etiqueta_mm=Decimal("40.00"),
            impressora_padrao="Argox OS-214",
            linguagem_impressora="PPLA",
        )

        response = self.client.get(
            "/produtos/etiquetas/",
            {"busca": self.produto.codigo_barras, "modelo": "configurado", "quantidade_copias": "1"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Imprimir direto")
        self.assertEqual(response.context["payload_etiquetas"]["linguagem"], "PPLA")
        self.assertEqual(response.context["payload_etiquetas"]["impressora_padrao"], "Argox OS-214")

    def test_etiqueta_profissional_usa_modelo_nomeado(self):
        empresa = Empresa.objects.create(
            razao_social="Mercado Etiquetas Ltda",
            nome_fantasia="Mercado Etiquetas",
            cnpj="98765432000188",
        )
        config = ConfiguracaoImpressao.objects.create(
            empresa=empresa,
            tipo_documento=TipoDocumentoImpressao.ETIQUETA,
            impressora_padrao="Argox OS-214",
        )
        modelo = ModeloEtiqueta.objects.create(
            configuracao=config,
            nome="Gondola promocional",
            largura_mm=Decimal("90.00"),
            altura_mm=Decimal("45.00"),
            colunas=2,
            orientacao="PAISAGEM",
            padrao=True,
        )

        response = self.client.get(
            "/produtos/etiquetas/",
            {
                "busca": self.produto.codigo_barras,
                "modelo": "configurado",
                "modelo_salvo": modelo.id,
                "quantidade_copias": "1",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "--label-width: 90.00mm")
        self.assertContains(response, "--label-height: 45.00mm")
        self.assertContains(response, "Gondola promocional")
        self.assertContains(response, "Argox OS-214")

    def test_impressao_direta_nao_e_oferecida_sem_linguagem_nativa(self):
        empresa = Empresa.objects.create(
            razao_social="Mercado Driver Ltda",
            nome_fantasia="Mercado Driver",
            cnpj="55443322000100",
        )
        ConfiguracaoImpressao.objects.create(
            empresa=empresa,
            tipo_documento=TipoDocumentoImpressao.ETIQUETA,
            impressora_padrao="Impressora do Windows",
            linguagem_impressora="WINDOWS",
        )

        response = self.client.get(
            "/produtos/etiquetas/",
            {"busca": self.produto.codigo_barras, "modelo": "compacto", "quantidade_copias": "2"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Imprimir direto")
        self.assertContains(response, "Imprimir pelo navegador")
        self.assertIsNone(response.context["payload_etiquetas"])

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

    def test_busca_json_retorna_categoria_e_marca_para_select2(self):
        from .models import Marca

        marca = Marca.objects.create(nome="Marca Teste")

        categoria_response = self.client.get("/produtos/categorias/busca.json", {"q": "Merce"})
        marca_response = self.client.get("/produtos/marcas/busca.json", {"q": "Teste"})

        self.assertEqual(categoria_response.status_code, 200)
        self.assertEqual(categoria_response.json()["results"][0]["id"], self.categoria.id)
        self.assertEqual(marca_response.status_code, 200)
        self.assertEqual(marca_response.json()["results"][0]["id"], marca.id)
