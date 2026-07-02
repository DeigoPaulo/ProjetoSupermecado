from datetime import datetime, timedelta, timezone
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.utils import timezone as django_timezone
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

from apps.auditoria.models import LogAuditoria
from apps.empresas.models import Empresa, Filial
from apps.pdv.models import Caixa
from apps.produtos.models import Categoria, Produto
from apps.vendas.models import FormaPagamento, ItemVenda, PagamentoVenda, StatusVenda, Venda

from .models import (
    AmbienteFiscal,
    ConfiguracaoFiscal,
    DocumentoFiscal,
    NaturezaOperacao,
    SerieFiscal,
    StatusDocumentoFiscal,
    TipoDocumentoFiscal,
)
from .certificados import abrir_certificado_a1, salvar_certificado_a1
from .services import cancelar_documento, preparar_documento_venda


def _certificado_teste(nome="certificado-teste.pfx", senha="123456", dias_validade=365):
    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    assunto = emissor = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "BR"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Mercado Teste"),
            x509.NameAttribute(NameOID.COMMON_NAME, "Mercado Teste A1"),
        ]
    )
    agora = datetime.now(timezone.utc)
    certificado = (
        x509.CertificateBuilder()
        .subject_name(assunto)
        .issuer_name(emissor)
        .public_key(chave.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(agora - timedelta(days=1))
        .not_valid_after(agora + timedelta(days=dias_validade))
        .sign(chave, hashes.SHA256())
    )
    conteudo = pkcs12.serialize_key_and_certificates(
        name=b"mercado-teste",
        key=chave,
        cert=certificado,
        cas=None,
        encryption_algorithm=serialization.BestAvailableEncryption(senha.encode("utf-8")),
    )
    return SimpleUploadedFile(nome, conteudo, content_type="application/x-pkcs12")


class FiscalTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser("admin", "admin@example.com", "123")
        self.client = Client(HTTP_HOST="localhost")
        self.client.force_login(self.user)
        self.empresa = Empresa.objects.create(razao_social="Mercado Teste", nome_fantasia="Mercado", cnpj="44.444.444/0001-44")
        self.filial = Filial.objects.create(
            empresa=self.empresa,
            nome="Matriz",
            cnpj=self.empresa.cnpj,
            municipio="Sao Paulo",
            uf="SP",
            codigo_municipio_ibge="3550308",
        )
        self.caixa = Caixa.objects.create(filial=self.filial, usuario_abertura=self.user, valor_inicial=Decimal("50.00"))
        self.venda = Venda.objects.create(
            filial=self.filial,
            caixa=self.caixa,
            usuario=self.user,
            total_bruto=Decimal("82.70"),
            total_liquido=Decimal("82.70"),
            status=StatusVenda.FINALIZADA,
        )
        self.categoria = Categoria.objects.create(nome="Mercearia")
        self.produto = Produto.objects.create(
            codigo_barras="7891234567001",
            nome="Arroz Branco 5kg",
            categoria=self.categoria,
            preco_custo=Decimal("15.00"),
            preco_venda=Decimal("82.70"),
            ncm="10063021",
            origem_mercadoria="0",
            cst_icms="00",
            aliquota_icms=Decimal("18.00"),
        )
        ItemVenda.objects.create(
            venda=self.venda,
            produto=self.produto,
            quantidade=Decimal("1.000"),
            preco_unitario_venda=Decimal("82.70"),
            total=Decimal("82.70"),
            custo_unitario_no_momento=Decimal("15.00"),
        )
        forma = FormaPagamento.objects.create(nome="Dinheiro", tipo="DINHEIRO", permite_troco=True)
        PagamentoVenda.objects.create(venda=self.venda, forma_pagamento=forma, valor=Decimal("82.70"))
        self.configuracao = ConfiguracaoFiscal.objects.create(
            filial=self.filial,
            ambiente=AmbienteFiscal.HOMOLOGACAO,
            inscricao_estadual="123456789",
            csc_id="1",
            csc_token="token-homologacao",
            regime_tributario="Regime normal",
        )
        salvar_certificado_a1(self.configuracao, _certificado_teste(), "123456")
        SerieFiscal.objects.create(filial=self.filial, tipo_documento=TipoDocumentoFiscal.NFCE, serie=1, proximo_numero=100)
        NaturezaOperacao.objects.create(descricao="Venda ao consumidor", cfop="5102", tipo_documento=TipoDocumentoFiscal.NFCE)

    def test_tela_fiscal_abre_com_parametros(self):
        response = self.client.get("/fiscal/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Fiscal")
        self.assertContains(response, "Vendas aguardando NFC-e")
        self.assertContains(response, f"#{self.venda.id}")
        self.assertContains(response, "Venda ao consumidor")
        self.assertContains(response, "Homologacao")
        self.assertContains(response, "Situacao fiscal")
        self.assertContains(response, "Pronta")
        self.assertContains(response, "Valido ate")
        self.assertContains(response, "Produtos fiscais")

    def test_tela_produtos_fiscais_mostra_pendencias_e_prontos(self):
        Produto.objects.create(
            codigo_barras="7890000000001",
            nome="Produto sem fiscal",
            categoria=self.categoria,
            preco_custo=Decimal("1.00"),
            preco_venda=Decimal("2.00"),
        )

        response = self.client.get("/fiscal/produtos/")
        response_todos = self.client.get("/fiscal/produtos/?filtro=todos")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Produtos fiscais")
        self.assertContains(response, "Produto sem fiscal")
        self.assertContains(response, "NCM com 8 digitos")
        self.assertContains(response, "CST ICMS com 2 digitos")
        self.assertContains(response_todos, "Arroz Branco 5kg")
        self.assertContains(response_todos, "Pronto")

    def test_preparar_documento_venda_numera_e_audita(self):
        documento = preparar_documento_venda(self.venda, self.user)

        self.assertEqual(documento.status, StatusDocumentoFiscal.PRONTO)
        self.assertEqual(documento.numero, 100)
        self.assertEqual(documento.valor_total, Decimal("82.70"))
        self.assertEqual(documento.natureza_operacao.descricao, "Venda ao consumidor")
        self.assertIn("<NFe", documento.xml_conteudo)
        self.assertIn("<cUF>35</cUF>", documento.xml_conteudo)
        self.assertIn("<cMunFG>3550308</cMunFG>", documento.xml_conteudo)
        self.assertIn("<mod>65</mod>", documento.xml_conteudo)
        self.assertIn("<xProd>Arroz Branco 5kg</xProd>", documento.xml_conteudo)
        self.assertIsNotNone(documento.xml_gerado_em)
        self.assertTrue(LogAuditoria.objects.filter(modulo="fiscal", acao="PREPARA_DOCUMENTO").exists())
        self.assertEqual(SerieFiscal.objects.get(filial=self.filial).proximo_numero, 101)

    def test_nao_prepara_documento_duplicado_para_mesma_venda(self):
        preparar_documento_venda(self.venda, self.user)

        with self.assertRaisesMessage(Exception, "ja possui documento fiscal"):
            preparar_documento_venda(self.venda, self.user)

        self.assertEqual(DocumentoFiscal.objects.filter(venda=self.venda).count(), 1)

    def test_bloqueia_nfce_quando_produto_esta_sem_dados_tributarios(self):
        self.produto.ncm = ""
        self.produto.origem_mercadoria = ""
        self.produto.cst_icms = ""
        self.produto.aliquota_icms = None
        self.produto.save(update_fields=["ncm", "origem_mercadoria", "cst_icms", "aliquota_icms"])

        with self.assertRaises(ValidationError) as contexto:
            preparar_documento_venda(self.venda, self.user)

        mensagem = " ".join(contexto.exception.messages)
        self.assertIn("NCM com 8 digitos", mensagem)
        self.assertIn("origem da mercadoria", mensagem)
        self.assertIn("CST ICMS", mensagem)
        self.assertIn("aliquota de ICMS", mensagem)
        self.assertFalse(DocumentoFiscal.objects.exists())
        self.assertEqual(SerieFiscal.objects.get(filial=self.filial).proximo_numero, 100)

        response = self.client.get("/fiscal/")
        self.assertContains(response, "4 pendencias")
        self.assertContains(response, "Corrija as pendencias fiscais antes de preparar")

    def test_cancelar_documento_pronto(self):
        documento = preparar_documento_venda(self.venda, self.user)

        cancelar_documento(documento, self.user, "Venda cancelada antes da transmissao")
        documento.refresh_from_db()

        self.assertEqual(documento.status, StatusDocumentoFiscal.CANCELADO)
        self.assertIn("Venda cancelada", documento.motivo_cancelamento)
        self.assertTrue(LogAuditoria.objects.filter(modulo="fiscal", acao="CANCELA_DOCUMENTO").exists())

    def test_rota_preparar_venda(self):
        response = self.client.post(f"/fiscal/vendas/{self.venda.pk}/preparar/")

        self.assertEqual(response.status_code, 302)
        self.assertTrue(DocumentoFiscal.objects.filter(venda=self.venda, status=StatusDocumentoFiscal.PRONTO).exists())

    def test_detalhe_e_impressao_mostram_espelho_do_documento(self):
        documento = preparar_documento_venda(self.venda, self.user)

        response = self.client.get(f"/fiscal/documentos/{documento.pk}/")
        response_print = self.client.get(f"/fiscal/documentos/{documento.pk}/imprimir/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Espelho de conferencia")
        self.assertContains(response, "Arroz Branco 5kg")
        self.assertContains(response, "Dinheiro")
        self.assertContains(response, "Cliente avulso")
        self.assertContains(response, "Baixar XML")
        self.assertEqual(response_print.status_code, 200)
        self.assertContains(response_print, "window.print")

        response_xml = self.client.get(f"/fiscal/documentos/{documento.pk}/xml/")
        self.assertEqual(response_xml.status_code, 200)
        self.assertEqual(response_xml["Content-Type"], "application/xml; charset=utf-8")
        self.assertIn(b"<NFe", response_xml.content)
        self.assertIn(b"<tPag>01</tPag>", response_xml.content)

    def test_upload_certificado_a1_criptografa_e_le_validade(self):
        nova_filial = Filial.objects.create(
            empresa=self.empresa,
            nome="Loja 2",
            cnpj="55.555.555/0001-55",
            municipio="Sao Paulo",
            uf="SP",
            codigo_municipio_ibge="3550308",
        )
        arquivo = _certificado_teste(nome="loja2.p12", senha="segredo", dias_validade=90)

        response = self.client.post(
            "/fiscal/configuracoes/nova/",
            {
                "filial": nova_filial.pk,
                "ambiente": AmbienteFiscal.HOMOLOGACAO,
                "regime_tributario": "Regime normal",
                "inscricao_estadual": "987654321",
                "csc_id": "2",
                "csc_token": "token",
                "certificado_nome": "",
                "certificado_validade": "",
                "certificado_senha": "segredo",
                "ativo": "on",
                "certificado_arquivo": arquivo,
            },
        )

        self.assertEqual(response.status_code, 302)
        configuracao = ConfiguracaoFiscal.objects.get(filial=nova_filial)
        self.assertTrue(configuracao.certificado_configurado)
        self.assertEqual(configuracao.certificado_nome, "loja2.p12")
        self.assertGreaterEqual(configuracao.certificado_validade, django_timezone.localdate())
        conteudo, senha = abrir_certificado_a1(configuracao)
        self.assertEqual(senha, "segredo")
        self.assertIsInstance(conteudo, bytes)
        self.assertNotIn(b"segredo", bytes(configuracao.certificado_senha_criptografada))

    def test_bloqueia_nfce_sem_certificado_a1(self):
        self.configuracao.certificado_a1_criptografado = None
        self.configuracao.certificado_senha_criptografada = None
        self.configuracao.certificado_validade = None
        self.configuracao.save(
            update_fields=["certificado_a1_criptografado", "certificado_senha_criptografada", "certificado_validade"]
        )

        with self.assertRaises(ValidationError) as contexto:
            preparar_documento_venda(self.venda, self.user)

        self.assertIn("Envie o certificado A1", " ".join(contexto.exception.messages))

    def test_bloqueia_nfce_sem_uf_e_codigo_ibge_da_filial(self):
        self.filial.uf = ""
        self.filial.codigo_municipio_ibge = ""
        self.filial.save(update_fields=["uf", "codigo_municipio_ibge"])

        with self.assertRaises(ValidationError) as contexto:
            preparar_documento_venda(self.venda, self.user)

        mensagem = " ".join(contexto.exception.messages)
        self.assertIn("UF da filial", mensagem)
        self.assertIn("codigo IBGE", mensagem)
