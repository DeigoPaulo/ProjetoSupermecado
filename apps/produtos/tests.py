from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from PIL import Image

from apps.accounts.models import PerfilUsuario, TipoPerfil
from apps.auditoria.models import LogAuditoria
from apps.configuracoes.models import ConfiguracaoImpressao, ModeloEtiqueta, TipoDocumentoImpressao
from apps.empresas.models import Empresa, Filial
from apps.empresas.services_snapshots import produto_snapshot_payload
from apps.fornecedores.models import Fornecedor

from .forms import CategoriaForm, ProdutoForm, ProdutoFornecedorForm
from .models import (
    Categoria, CodigoBarrasProduto, ConfiguracaoBalancaProduto, InformacaoNutricional, NivelCategoriaProduto, Produto,
    ProdutoFornecedor, ProdutoImagem, SetorBalanca, TipoProduto,
)


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

    def test_importacao_csv_atualiza_campos_fiscais_e_audita(self):
        conteudo = """codigo_barras;nome;categoria;preco_venda;ncm;origem_mercadoria;cst_icms;aliquota_icms;cst_pis;aliquota_pis;cst_cofins;aliquota_cofins;cst_ibs_cbs;classificacao_tributaria_ibs_cbs
7891234567890;Arroz;Mercearia;15,00;10063021;0;40;0;06;;06;;000;000001
"""
        arquivo = SimpleUploadedFile(
            "produtos-fiscais.csv",
            conteudo.encode("utf-8"),
            content_type="text/csv",
        )

        response = self.client.post(
            "/produtos/importar-csv/",
            {"arquivo": arquivo, "atualizar_existentes": "on"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.produto.refresh_from_db()
        self.assertEqual(self.produto.cst_icms, "40")
        self.assertEqual(self.produto.aliquota_icms, Decimal("0"))
        self.assertEqual(self.produto.cst_pis, "06")
        self.assertIsNone(self.produto.aliquota_pis)
        self.assertEqual(self.produto.cst_cofins, "06")
        self.assertEqual(self.produto.cst_ibs_cbs, "000")
        self.assertEqual(self.produto.classificacao_tributaria_ibs_cbs, "000001")
        self.assertTrue(
            LogAuditoria.objects.filter(
                modulo="produtos", acao="IMPORTA_PRODUTOS_CSV"
            ).exists()
        )

    def test_importacao_csv_fiscal_preserva_dados_comerciais(self):
        conteudo = """codigo_barras;codigo_interno;nome;categoria;preco_venda;ncm;cst_icms;_modo_importacao
7891234567890;ALTERADO;Nome alterado;Categoria indevida;999,99;10063022;40;fiscal
"""
        arquivo = SimpleUploadedFile(
            "produtos-fiscais.csv",
            conteudo.encode("utf-8"),
            content_type="text/csv",
        )

        response = self.client.post(
            "/produtos/importar-csv/",
            {"arquivo": arquivo, "atualizar_existentes": "on"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.produto.refresh_from_db()
        self.assertEqual(self.produto.nome, "Arroz")
        self.assertEqual(self.produto.categoria, self.categoria)
        self.assertEqual(self.produto.preco_venda, Decimal("15.00"))
        self.assertNotEqual(self.produto.codigo_interno, "ALTERADO")
        self.assertEqual(self.produto.ncm, "10063022")
        self.assertEqual(self.produto.cst_icms, "40")
        self.assertFalse(Categoria.all_objects.filter(nome="Categoria indevida").exists())
        self.assertContains(response, "1 somente fiscal")

    def test_importacao_csv_fiscal_recusa_criar_produto_inexistente(self):
        conteudo = """codigo_barras;nome;categoria;preco_venda;ncm;_modo_importacao
7890000000999;Produto indevido;Categoria indevida;10,00;10063021;fiscal
"""
        arquivo = SimpleUploadedFile(
            "produto-fiscal-inexistente.csv",
            conteudo.encode("utf-8"),
            content_type="text/csv",
        )

        response = self.client.post(
            "/produtos/importar-csv/",
            {"arquivo": arquivo, "atualizar_existentes": "on"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "planilha fiscal atualiza apenas produtos existentes")
        self.assertFalse(Produto.all_objects.filter(codigo_barras="7890000000999").exists())
        self.assertFalse(Categoria.all_objects.filter(nome="Categoria indevida").exists())

    def test_importacao_csv_rejeita_percentual_fiscal_invalido_sem_alterar_produto(self):
        conteudo = """codigo_barras;nome;categoria;preco_venda;aliquota_icms
7891234567890;Arroz;Mercearia;15,00;120
"""
        arquivo = SimpleUploadedFile(
            "produto-invalido.csv",
            conteudo.encode("utf-8"),
            content_type="text/csv",
        )

        response = self.client.post(
            "/produtos/importar-csv/",
            {"arquivo": arquivo, "atualizar_existentes": "on"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Aliquota ICMS deve estar entre 0 e 100")
        self.produto.refresh_from_db()
        self.assertEqual(self.produto.aliquota_icms, Decimal("18.00"))

    def test_importacao_csv_sem_coluna_opcional_preserva_dados_existentes(self):
        self.produto.descricao = "Descricao preservada"
        self.produto.save(update_fields=["descricao"])
        conteudo = """codigo_barras;nome;categoria;preco_venda
7891234567890;Arroz atualizado;Mercearia;16.00
"""
        arquivo = SimpleUploadedFile(
            "produto-comercial.csv",
            conteudo.encode("utf-8"),
            content_type="text/csv",
        )

        response = self.client.post(
            "/produtos/importar-csv/",
            {"arquivo": arquivo, "atualizar_existentes": "on"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.produto.refresh_from_db()
        self.assertEqual(self.produto.nome, "Arroz atualizado")
        self.assertEqual(self.produto.preco_venda, Decimal("16.00"))
        self.assertEqual(self.produto.descricao, "Descricao preservada")
        self.assertEqual(self.produto.cst_icms, "00")
        self.assertEqual(self.produto.aliquota_icms, Decimal("18.00"))

    def test_codigo_interno_e_gerado_automaticamente_e_pode_ser_sugerido(self):
        self.assertEqual(self.produto.codigo_interno, f"PRD-{self.produto.pk:06d}")

        pagina = self.client.get("/produtos/novo/")
        sugestao = self.client.get("/produtos/proximo-codigo-interno.json")

        self.assertEqual(pagina.status_code, 200)
        self.assertContains(pagina, "data-product-code-generator")
        self.assertContains(pagina, "Deixe vazio para gerar automaticamente ao salvar.")
        self.assertEqual(sugestao.status_code, 200)
        self.assertEqual(sugestao.json()["codigo"], "PRD-000002")

        produto = Produto.objects.create(
            codigo_barras="7890000000999",
            nome="Produto automatico",
            categoria=self.categoria,
            preco_venda=Decimal("3.50"),
        )
        self.assertEqual(produto.codigo_interno, f"PRD-{produto.pk:06d}")

    def test_codigo_interno_manual_e_normalizado_e_preservado(self):
        produto = Produto.objects.create(
            codigo_barras="7890000000998",
            codigo_interno=" ref-abc-9 ",
            nome="Produto manual",
            categoria=self.categoria,
            preco_venda=Decimal("4.50"),
        )

        self.assertEqual(produto.codigo_interno, "REF-ABC-9")

    def test_formulario_bloqueia_codigo_interno_duplicado(self):
        form = ProdutoForm(
            data={
                "codigo_barras": "7890000000997",
                "codigo_interno": self.produto.codigo_interno.lower(),
                "nome": "Produto duplicado",
                "categoria": self.categoria.pk,
                "unidade": "UN",
                "preco_custo": "1.00",
                "preco_venda": "2.00",
                "estoque_minimo": "0",
                "vendido_no_pdv": "on",
                "is_active": "on",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("Este c\u00f3digo interno j\u00e1 est\u00e1 sendo usado", form.errors["codigo_interno"][0])

    def test_form_produto_exibe_secoes_operacionais(self):
        response = self.client.get(f"/produtos/{self.produto.pk}/editar/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Identificação")
        self.assertContains(response, "Preços e estoque")
        self.assertContains(response, "Venda e imagem")
        self.assertContains(response, "Dados fiscais")
        self.assertContains(response, "Obrigat\u00f3rio para NFC-e")
        self.assertContains(response, "select2-field")
        self.assertContains(response, "Imagem para marketplace")
        self.assertContains(response, "Sem imagem cadastrada")
        self.assertContains(response, "Galeria adicional")
        self.assertContains(response, 'name="galeria-TOTAL_FORMS"')
        self.assertContains(response, 'data-ajax-url="/produtos/categorias/busca.json"')
        self.assertContains(response, 'data-ajax-url="/produtos/marcas/busca.json"')

    def test_form_produto_exibe_nutricao_e_similares_como_opcionais(self):
        response = self.client.get(f"/produtos/{self.produto.pk}/editar/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "produtos similares")
        self.assertContains(response, "Opcional")
        self.assertContains(response, 'name="nutricao-TOTAL_FORMS"')
        self.assertContains(response, 'data-ajax-url="/estoque/produtos/busca.json"')

    def test_edicao_salva_nutricao_similares_e_publica_no_snapshot(self):
        similar = Produto.objects.create(
            codigo_barras="7891234567005",
            nome="Arroz integral",
            categoria=self.categoria,
            preco_custo=Decimal("11.00"),
            preco_venda=Decimal("16.50"),
        )
        response = self.client.post(
            f"/produtos/{self.produto.pk}/editar/",
            {
                "codigo_barras": self.produto.codigo_barras,
                "codigo_interno": self.produto.codigo_interno,
                "nome": self.produto.nome,
                "categoria": self.categoria.pk,
                "unidade": "UN",
                "unidade_compra": "UN",
                "fator_conversao_compra": "1.000",
                "preco_custo": "10.00",
                "preco_venda": "15.00",
                "estoque_minimo": "0",
                "vendido_no_pdv": "on",
                "produtos_similares": [similar.pk],
                "ncm": "10063021",
                "origem_mercadoria": "0",
                "cst_icms": "00",
                "aliquota_icms": "18.00",
                "is_active": "on",
                "galeria-TOTAL_FORMS": "0",
                "galeria-INITIAL_FORMS": "0",
                "galeria-MIN_NUM_FORMS": "0",
                "galeria-MAX_NUM_FORMS": "1000",
                "nutricao-TOTAL_FORMS": "1",
                "nutricao-INITIAL_FORMS": "0",
                "nutricao-MIN_NUM_FORMS": "0",
                "nutricao-MAX_NUM_FORMS": "1",
                "nutricao-0-base_calculo": "100G",
                "nutricao-0-porcao_quantidade": "50.00",
                "nutricao-0-porcao_unidade": "g",
                "nutricao-0-medida_caseira": "1/4 de x?cara",
                "nutricao-0-porcoes_por_embalagem": "10.00",
                "nutricao-0-valor_energetico_kcal": "180.00",
                "nutricao-0-carboidratos_g": "39.00",
                "nutricao-0-proteinas_g": "3.50",
                "nutricao-0-sodio_mg": "1.00",
                "nutricao-0-ingredientes": "Arroz branco.",
                "nutricao-0-gluten": "NAO_CONTEM",
            },
        )

        self.assertRedirects(response, "/produtos/")
        nutricao = InformacaoNutricional.objects.get(produto=self.produto)
        self.assertEqual(nutricao.porcao_quantidade, Decimal("50.00"))
        self.assertEqual(nutricao.valor_energetico_kcal, Decimal("180.00"))
        self.assertEqual(nutricao.gluten, "NAO_CONTEM")
        self.assertTrue(self.produto.produtos_similares.filter(pk=similar.pk).exists())
        self.assertTrue(similar.produtos_similares.filter(pk=self.produto.pk).exists())

        from apps.empresas.services_snapshots import produto_snapshot_payload
        payload = produto_snapshot_payload(self.produto)
        self.assertEqual(payload["informacao_nutricional"]["porcao_quantidade"], "50.00")
        self.assertEqual(payload["produtos_similares"][0]["codigo_barras"], similar.codigo_barras)

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

    def test_edicao_salva_unidade_de_compra_e_codigo_adicional(self):
        response = self.client.post(
            f"/produtos/{self.produto.pk}/editar/",
            {
                "codigo_barras": self.produto.codigo_barras,
                "codigo_interno": self.produto.codigo_interno,
                "nome": self.produto.nome,
                "categoria": self.categoria.pk,
                "unidade": "UN",
                "unidade_compra": "CX",
                "fator_conversao_compra": "12.000",
                "peso_liquido": "10.500",
                "peso_bruto": "11.000",
                "preco_custo": "10.00",
                "preco_venda": "15.00",
                "estoque_minimo": "0",
                "vendido_no_pdv": "on",
                "ncm": "10063021",
                "origem_mercadoria": "0",
                "cst_icms": "00",
                "aliquota_icms": "18.00",
                "is_active": "on",
                "galeria-TOTAL_FORMS": "0",
                "galeria-INITIAL_FORMS": "0",
                "galeria-MIN_NUM_FORMS": "0",
                "galeria-MAX_NUM_FORMS": "1000",
                "codigos-TOTAL_FORMS": "1",
                "codigos-INITIAL_FORMS": "0",
                "codigos-MIN_NUM_FORMS": "0",
                "codigos-MAX_NUM_FORMS": "1000",
                "codigos-0-codigo": "17891234567897",
                "codigos-0-tipo": "CAIXA",
                "codigos-0-fator_conversao": "12.000",
                "codigos-0-permite_venda": "on",
                "codigos-0-is_active": "on",
            },
        )

        self.assertRedirects(response, "/produtos/")
        self.produto.refresh_from_db()
        codigo = self.produto.codigos_adicionais.get()
        self.assertEqual(self.produto.unidade_compra, "CX")
        self.assertEqual(self.produto.fator_conversao_compra, Decimal("12.000"))
        self.assertEqual(self.produto.peso_liquido, Decimal("10.500"))
        self.assertEqual(codigo.codigo, "17891234567897")
        self.assertEqual(codigo.fator_conversao, Decimal("12.000"))
        self.assertTrue(codigo.permite_venda)

    def test_formulario_bloqueia_ean_adicional_repetido_em_outro_produto(self):
        CodigoBarrasProduto.objects.create(
            produto=self.produto,
            codigo="17891234567897",
            tipo="CAIXA",
            fator_conversao=Decimal("12.000"),
        )
        response = self.client.post(
            "/produtos/novo/",
            {
                "codigo_barras": "7890000000777",
                "nome": "Produto com EAN repetido",
                "categoria": self.categoria.pk,
                "unidade": "UN",
                "preco_custo": "1.00",
                "preco_venda": "2.00",
                "estoque_minimo": "0",
                "vendido_no_pdv": "on",
                "is_active": "on",
                "galeria-TOTAL_FORMS": "0",
                "galeria-INITIAL_FORMS": "0",
                "galeria-MIN_NUM_FORMS": "0",
                "galeria-MAX_NUM_FORMS": "1000",
                "codigos-TOTAL_FORMS": "1",
                "codigos-INITIAL_FORMS": "0",
                "codigos-MIN_NUM_FORMS": "0",
                "codigos-MAX_NUM_FORMS": "1000",
                "codigos-0-codigo": "17891234567897",
                "codigos-0-tipo": "CAIXA",
                "codigos-0-fator_conversao": "6.000",
                "codigos-0-permite_venda": "on",
                "codigos-0-is_active": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "já existe.")
        self.assertFalse(Produto.objects.filter(codigo_barras="7890000000777").exists())

    def test_lista_e_etiquetas_encontram_produto_por_ean_adicional(self):
        CodigoBarrasProduto.objects.create(
            produto=self.produto,
            codigo="17891234567897",
            tipo="CAIXA",
            fator_conversao=Decimal("12.000"),
        )
        lista = self.client.get("/produtos/", {"q": "17891234567897"})
        etiquetas = self.client.get(
            "/produtos/etiquetas/",
            {"busca": "17891234567897", "modelo": "compacto", "quantidade_copias": "1"},
        )

        self.assertContains(lista, self.produto.nome)
        self.assertContains(etiquetas, self.produto.nome)
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
        self.assertContains(response, 'class="label-barcode-svg"', count=2)
        self.assertContains(response, self.produto.codigo_barras, count=2)
        self.assertContains(response, "SKU SKU-ARROZ-01", count=2)
        self.assertContains(response, "Arroz", count=2)
        self.assertContains(response, "Bipe o código de barras")

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
        self.assertEqual(response.context["payload_etiquetas"]["contrato"], "label_print_v1")
        self.assertEqual(response.context["payload_etiquetas"]["origem"], "produtos_etiquetas")
        self.assertEqual(response.context["payload_etiquetas"]["linguagem"], "ZPL")
        self.assertEqual(response.context["payload_etiquetas"]["modelo"]["largura_mm"], 80.0)
        self.assertEqual(response.context["payload_etiquetas"]["itens"][0]["copias"], 1)
        self.assertIn("preco", response.context["payload_etiquetas"]["itens"][0])

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

    def test_etiqueta_profissional_avisa_quando_nao_tem_impressora_padrao(self):
        empresa = Empresa.objects.create(
            razao_social="Mercado Sem Impressora Ltda",
            nome_fantasia="Mercado Sem Impressora",
            cnpj="11223344000155",
        )
        ConfiguracaoImpressao.objects.create(
            empresa=empresa,
            tipo_documento=TipoDocumentoImpressao.ETIQUETA,
            largura_etiqueta_mm=Decimal("80.00"),
            altura_etiqueta_mm=Decimal("40.00"),
            impressora_padrao="",
            linguagem_impressora="ZPL",
        )

        response = self.client.get(
            "/produtos/etiquetas/",
            {"busca": self.produto.codigo_barras, "modelo": "configurado", "quantidade_copias": "1"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "sem impressora padrão")
        self.assertContains(response, "Imprimir pelo navegador")
        self.assertNotContains(response, "Imprimir direto")
        self.assertFalse(response.context["impressao_nativa_disponivel"])
        self.assertIsNone(response.context["payload_etiquetas"])

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
                "nome": "Produto inválido",
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
        self.assertContains(response, "NCM deve possuir 8 d\u00edgitos.")
        self.assertContains(response, "CEST deve possuir 7 d\u00edgitos.")

    def test_hierarquia_comercial_valida_caminho_e_nivel_imediato(self):
        departamento = Categoria.objects.create(nome="Alimentos", nivel=NivelCategoriaProduto.DEPARTAMENTO)
        secao = Categoria.objects.create(nome="Mercearia seca", nivel=NivelCategoriaProduto.SECAO, parent=departamento)
        grupo = Categoria.objects.create(nome="Massas", nivel=NivelCategoriaProduto.GRUPO, parent=secao)

        self.assertEqual(grupo.caminho_completo, "Alimentos > Mercearia seca > Massas")
        form = CategoriaForm(
            data={"nome": "Espaguete", "nivel": "SUBGRUPO", "parent": grupo.pk, "is_active": "on"}
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().caminho_completo, "Alimentos > Mercearia seca > Massas > Espaguete")

        invalido = CategoriaForm(
            data={"nome": "Atalho inválido", "nivel": "SUBGRUPO", "parent": departamento.pk, "is_active": "on"}
        )
        self.assertFalse(invalido.is_valid())
        self.assertIn("Selecione uma classificação de nível superior.", invalido.errors["parent"])

    def test_produto_exibe_tipo_e_classificacao_comercial_na_mesma_tela(self):
        response = self.client.get("/produtos/novo/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tipo comercial")
        self.assertContains(response, "Classificação comercial")
        self.assertContains(response, "Selecione o nível mais específico disponível.")

    def test_form_categoria_exibe_uso_operacional(self):
        response = self.client.get("/produtos/categorias/nova/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Hierarquia do produto")
        self.assertContains(response, "departamento, seção, grupo e subgrupo")
        self.assertContains(response, "Sem carga manual para os caixas.")

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
        self.assertEqual(categoria_response.json()["results"][0]["text"], "Mercearia")
        self.assertEqual(categoria_response.json()["results"][0]["descricao"], "Grupo")
        self.assertEqual(marca_response.status_code, 200)
        self.assertEqual(marca_response.json()["results"][0]["id"], marca.id)

    def test_margem_e_preco_sugerido_usam_margem_sobre_venda(self):
        self.produto.preco_custo = Decimal("80.00")
        self.produto.preco_venda = Decimal("100.00")
        self.produto.margem_desejada_percentual = Decimal("20.00")

        self.assertEqual(self.produto.margem_atual_percentual, Decimal("20.00"))
        self.assertEqual(self.produto.preco_venda_sugerido, Decimal("100.00"))

    def test_tela_produto_exibe_fornecedores_margem_e_preco_sugerido(self):
        response = self.client.get(f"/produtos/{self.produto.pk}/editar/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Fornecedores do produto")
        self.assertContains(response, 'name="fornecedores-TOTAL_FORMS"')
        self.assertContains(response, "Margem desejada (%)")
        self.assertContains(response, "Preço sugerido", html=False)
        self.assertContains(response, 'data-margin-calculator')

    def test_edicao_salva_fornecedor_vinculado(self):
        empresa = Empresa.objects.create(
            razao_social="Fornecedor Empresa Ltda", nome_fantasia="Fornecedor Empresa", cnpj="10101010000110"
        )
        fornecedor = Fornecedor.objects.create(empresa=empresa, razao_social="Distribuidora Central")
        response = self.client.post(
            f"/produtos/{self.produto.pk}/editar/",
            {
                "codigo_barras": self.produto.codigo_barras,
                "codigo_interno": self.produto.codigo_interno,
                "nome": self.produto.nome,
                "tipo_produto": self.produto.tipo_produto,
                "categoria": self.categoria.pk,
                "unidade": "UN",
                "unidade_compra": "UN",
                "fator_conversao_compra": "1.000",
                "preco_custo": "10.00",
                "margem_desejada_percentual": "25.00",
                "preco_venda": "15.00",
                "estoque_minimo": "0",
                "vendido_no_pdv": "on",
                "ncm": "10063021",
                "origem_mercadoria": "0",
                "cst_icms": "00",
                "aliquota_icms": "18.00",
                "is_active": "on",
                "galeria-TOTAL_FORMS": "0",
                "galeria-INITIAL_FORMS": "0",
                "galeria-MIN_NUM_FORMS": "0",
                "galeria-MAX_NUM_FORMS": "1000",
                "fornecedores-TOTAL_FORMS": "1",
                "fornecedores-INITIAL_FORMS": "0",
                "fornecedores-MIN_NUM_FORMS": "0",
                "fornecedores-MAX_NUM_FORMS": "1000",
                "fornecedores-0-fornecedor": fornecedor.pk,
                "fornecedores-0-codigo_no_fornecedor": "SKU-ARROZ-10",
                "fornecedores-0-ultimo_custo": "9.50",
                "fornecedores-0-principal": "on",
                "fornecedores-0-is_active": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        vinculo = ProdutoFornecedor.objects.get(produto=self.produto, fornecedor=fornecedor)
        self.assertEqual(vinculo.codigo_no_fornecedor, "SKU-ARROZ-10")
        self.assertEqual(vinculo.ultimo_custo, Decimal("9.50"))
        self.assertTrue(vinculo.principal)
        self.produto.refresh_from_db()
        self.assertEqual(self.produto.margem_desejada_percentual, Decimal("25.00"))

    def test_fornecedor_do_formulario_respeita_empresa_do_usuario(self):
        empresa_a = Empresa.objects.create(
            razao_social="Empresa A Ltda", nome_fantasia="Empresa A", cnpj="20202020000120"
        )
        empresa_b = Empresa.objects.create(
            razao_social="Empresa B Ltda", nome_fantasia="Empresa B", cnpj="30303030000130"
        )
        filial_a = Filial.objects.create(empresa=empresa_a, nome="Matriz A", cnpj=empresa_a.cnpj)
        usuario = get_user_model().objects.create_user("comprador_empresa_a", password="123")
        PerfilUsuario.objects.create(usuario=usuario, filial=filial_a, tipo=TipoPerfil.COMPRAS)
        fornecedor_a = Fornecedor.objects.create(empresa=empresa_a, razao_social="Fornecedor A")
        fornecedor_b = Fornecedor.objects.create(empresa=empresa_b, razao_social="Fornecedor B")

        form = ProdutoFornecedorForm(user=usuario)

        self.assertQuerySetEqual(form.fields["fornecedor"].queryset, [fornecedor_a])
        self.assertNotIn(fornecedor_b, form.fields["fornecedor"].queryset)
    def test_configuracao_plu_e_salva_no_produto_e_resolvida_no_pdv(self):
        from apps.pdv.views import _resolver_produto_por_busca

        empresa = Empresa.objects.create(
            razao_social="Mercado PLU Ltda", nome_fantasia="Mercado PLU", cnpj="40404040000140"
        )
        setor = SetorBalanca.objects.create(empresa=empresa, codigo=1, nome="Hortifruti")
        response = self.client.post(
            f"/produtos/{self.produto.pk}/editar/",
            {
                "codigo_barras": self.produto.codigo_barras,
                "codigo_interno": self.produto.codigo_interno,
                "nome": self.produto.nome,
                "tipo_produto": self.produto.tipo_produto,
                "categoria": self.categoria.pk,
                "unidade": "KG",
                "unidade_compra": "KG",
                "fator_conversao_compra": "1.000",
                "produto_pesavel": "on",
                "preco_custo": "10.00",
                "preco_venda": "15.00",
                "estoque_minimo": "0",
                "vendido_no_pdv": "on",
                "ncm": "10063021",
                "origem_mercadoria": "0",
                "cst_icms": "00",
                "aliquota_icms": "18.00",
                "is_active": "on",
                "galeria-TOTAL_FORMS": "0",
                "galeria-INITIAL_FORMS": "0",
                "galeria-MIN_NUM_FORMS": "0",
                "galeria-MAX_NUM_FORMS": "1000",
                "balanca-TOTAL_FORMS": "1",
                "balanca-INITIAL_FORMS": "0",
                "balanca-MIN_NUM_FORMS": "0",
                "balanca-MAX_NUM_FORMS": "1000",
                "balanca-0-setor": setor.pk,
                "balanca-0-plu": "1234",
                "balanca-0-tara_kg": "0.015",
                "balanca-0-validade_dias": "5",
                "balanca-0-is_active": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        configuracao = ConfiguracaoBalancaProduto.objects.get(produto=self.produto, empresa=empresa)
        self.assertEqual(configuracao.setor, setor)
        self.assertEqual(configuracao.plu, 1234)
        self.assertEqual(configuracao.tara_kg, Decimal("0.015"))
        from apps.empresas.services_snapshots import produto_snapshot_payload
        payload = produto_snapshot_payload(self.produto, empresa=empresa)
        self.assertEqual(payload["configuracoes_balanca"][0]["plu"], 1234)
        self.assertEqual(payload["configuracoes_balanca"][0]["setor_nome"], "Hortifruti")
        produto, fator, apresentacao = _resolver_produto_por_busca("1234", somente_venda=True, empresa_id=empresa.pk)
        self.assertEqual(produto, self.produto)
        self.assertEqual(fator, Decimal("1.000"))
        self.assertIsNone(apresentacao)

    def test_setores_de_balanca_respeitam_empresa_do_usuario(self):
        empresa_a = Empresa.objects.create(
            razao_social="Balanca Empresa A Ltda", nome_fantasia="Balanca A", cnpj="50505050000150"
        )
        empresa_b = Empresa.objects.create(
            razao_social="Balanca Empresa B Ltda", nome_fantasia="Balanca B", cnpj="60606060000160"
        )
        filial_a = Filial.objects.create(empresa=empresa_a, nome="Matriz A", cnpj=empresa_a.cnpj)
        usuario = get_user_model().objects.create_user("cadastro_balanca_a", password="123")
        PerfilUsuario.objects.create(usuario=usuario, filial=filial_a, tipo=TipoPerfil.ADMINISTRADOR)
        setor_a = SetorBalanca.objects.create(empresa=empresa_a, codigo=1, nome="Hortifruti")
        setor_b = SetorBalanca.objects.create(empresa=empresa_b, codigo=1, nome="Acougue")
        self.client.force_login(usuario)

        response = self.client.get("/produtos/setores-balanca/busca.json")

        self.assertEqual(response.status_code, 200)
        ids = [item["id"] for item in response.json()["results"]]
        self.assertIn(setor_a.pk, ids)
        self.assertNotIn(setor_b.pk, ids)

    def test_perfil_fiscal_avancado_e_opcional_validado_e_sincronizado(self):
        form = ProdutoForm(
            data={
                "codigo_barras": "7891234567005",
                "nome": "Produto fiscal avançado",
                "categoria": self.categoria.pk,
                "unidade": "UN",
                "preco_custo": "10.00",
                "preco_venda": "15.00",
                "estoque_minimo": "0",
                "ncm": "10063021",
                "origem_mercadoria": "0",
                "cst_icms": "00",
                "aliquota_icms": "18.00",
                "reducao_base_icms": "10.00",
                "aliquota_fcp": "2.00",
                "codigo_beneficio_fiscal": "go123",
                "cst_pis": "01",
                "aliquota_pis": "1.6500",
                "cst_cofins": "01",
                "aliquota_cofins": "7.6000",
                "cst_ipi": "53",
                "codigo_enquadramento_ipi": "999",
                "aliquota_ipi": "0.0000",
                "cst_ibs_cbs": "000",
                "classificacao_tributaria_ibs_cbs": "000001",
                "is_active": "on",
            }
        )

        self.assertTrue(form.is_valid(), form.errors.as_text())
        produto = form.save()
        self.assertEqual(produto.codigo_beneficio_fiscal, "GO123")
        self.assertEqual(produto.aliquota_pis, Decimal("1.6500"))
        payload = produto_snapshot_payload(produto)
        self.assertEqual(payload["cst_cofins"], "01")
        self.assertEqual(payload["aliquota_cofins"], "7.6000")
        self.assertEqual(payload["codigo_enquadramento_ipi"], "999")
        self.assertEqual(payload["classificacao_tributaria_ibs_cbs"], "000001")

    def test_perfil_fiscal_avancado_rejeita_codigos_e_percentuais_invalidos(self):
        form = ProdutoForm(
            data={
                "codigo_barras": "7891234567006",
                "nome": "Produto fiscal inválido",
                "categoria": self.categoria.pk,
                "unidade": "UN",
                "preco_custo": "10.00",
                "preco_venda": "15.00",
                "estoque_minimo": "0",
                "cst_pis": "1",
                "codigo_enquadramento_ipi": "99A",
                "aliquota_fcp": "101.00",
                "cst_ibs_cbs": "00",
                "classificacao_tributaria_ibs_cbs": "123",
                "is_active": "on",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("cst_pis", form.errors)
        self.assertIn("codigo_enquadramento_ipi", form.errors)
        self.assertIn("aliquota_fcp", form.errors)
        self.assertIn("cst_ibs_cbs", form.errors)
        self.assertIn("classificacao_tributaria_ibs_cbs", form.errors)
