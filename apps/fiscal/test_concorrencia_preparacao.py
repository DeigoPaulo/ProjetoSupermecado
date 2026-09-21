from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from unittest import skipUnless

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.test import TestCase, TransactionTestCase

from apps.empresas.models import Empresa, Filial
from apps.marketplace.models import ItemPedidoOnline, PedidoOnline
from apps.pdv.models import Caixa
from apps.produtos.models import Categoria, Produto
from apps.vendas.models import FormaPagamento, ItemVenda, PagamentoVenda, Venda

from .admin import DocumentoFiscalAdmin
from .models import (
    AmbienteFiscal,
    CodigoRegimeTributario,
    ConfiguracaoFiscal,
    DocumentoFiscal,
    NaturezaOperacao,
    SerieFiscal,
    StatusDocumentoFiscal,
    TipoDocumentoFiscal,
)
from .certificados import criptografar
from .services import preparar_documento_pedido_online, preparar_documento_venda
from .test_support_identidades_fiscais import obter_identidade_fiscal_teste


class FiscalOriginFixtureMixin:
    def setUp(self):
        self.usuario = get_user_model().objects.create_superuser(
            "admin_concorrencia_fiscal",
            "concorrencia-fiscal@example.com",
            "senha-teste",
        )
        self.empresa = Empresa.objects.create(
            razao_social="Mercado Concorrencia Ltda",
            nome_fantasia="Mercado Concorrencia",
            cnpj=obter_identidade_fiscal_teste(
                "EMPRESA_MATRIZ",
                finalidade="TESTE_INTEGRACAO_LOCAL",
            ),
        )
        self.filial = Filial.objects.create(
            empresa=self.empresa,
            nome="Matriz",
            cnpj=self.empresa.cnpj,
            municipio="Goiania",
            uf="GO",
            codigo_municipio_ibge="5208707",
        )
        self.categoria = Categoria.objects.create(nome="Mercearia concorrencia")
        self.produto = Produto.objects.create(
            codigo_barras="7891234567895",
            nome="Produto fiscal concorrente",
            categoria=self.categoria,
            preco_custo=Decimal("10.00"),
            preco_venda=Decimal("30.00"),
            ncm="10063021",
            origem_mercadoria="0",
            cst_icms="00",
            aliquota_icms=Decimal("18.00"),
            cst_pis="01",
            aliquota_pis=Decimal("1.6500"),
            cst_cofins="01",
            aliquota_cofins=Decimal("7.6000"),
        )
        self.caixa = Caixa.objects.create(
            filial=self.filial,
            usuario_abertura=self.usuario,
            valor_inicial=Decimal("50.00"),
        )
        self.venda = Venda.objects.create(
            filial=self.filial,
            caixa=self.caixa,
            usuario=self.usuario,
            total_bruto=Decimal("30.00"),
            total_liquido=Decimal("30.00"),
            status="FINALIZADA",
        )
        ItemVenda.objects.create(
            venda=self.venda,
            produto=self.produto,
            quantidade=Decimal("1.000"),
            preco_unitario_venda=Decimal("30.00"),
            total=Decimal("30.00"),
            custo_unitario_no_momento=Decimal("10.00"),
        )
        forma = FormaPagamento.objects.filter(tipo="DINHEIRO").order_by("pk").first()
        if not forma:
            forma = FormaPagamento.objects.create(
                pk=900001,
                nome="Dinheiro concorrencia",
                tipo="DINHEIRO",
                permite_troco=True,
            )
        PagamentoVenda.objects.create(
            venda=self.venda,
            forma_pagamento=forma,
            valor=Decimal("30.00"),
        )
        self.pedido = PedidoOnline.objects.create(
            filial=self.filial,
            nome_cliente="Cliente Online",
            documento_cliente_tipo="CNPJ",
            documento_cliente=obter_identidade_fiscal_teste(
                "CLIENTE_PJ",
                finalidade="TESTE_INTEGRACAO_LOCAL",
            ),
            destinatario_indicador_ie="9",
            destinatario_logradouro="Rua Fiscal",
            destinatario_numero="100",
            destinatario_bairro="Centro",
            destinatario_codigo_municipio_ibge="5208707",
            destinatario_municipio="Goiania",
            destinatario_uf="GO",
            destinatario_cep="74000000",
            status_pagamento="PAGO",
            forma_pagamento="GATEWAY",
            valor_pago=Decimal("30.00"),
            usuario=self.usuario,
        )
        ItemPedidoOnline.objects.create(
            pedido=self.pedido,
            produto=self.produto,
            quantidade=Decimal("1.000"),
            preco_unitario=Decimal("30.00"),
        )
        self.pedido.recalcular()
        self.pedido.valor_pago = self.pedido.total
        self.pedido.save(update_fields=["valor_pago"])

        ConfiguracaoFiscal.objects.create(
            filial=self.filial,
            ambiente=AmbienteFiscal.HOMOLOGACAO,
            inscricao_estadual="123456789",
            regime_tributario="Regime normal",
            crt=CodigoRegimeTributario.REGIME_NORMAL,
            csc_id="1",
            csc_token_criptografado=criptografar("token-homologacao"),
            url_qrcode_nfce=(
                "https://nfewebhomolog.sefaz.go.gov.br/nfeweb/sites/nfce/danfeNFCe"
            ),
            url_consulta_nfce=(
                "https://nfewebhomolog.sefaz.go.gov.br/nfeweb/sites/nfce/danfeNFCe"
            ),
            certificado_a1_criptografado=b"certificado-teste",
            certificado_senha_criptografada=b"senha-teste",
        )
        SerieFiscal.objects.create(
            filial=self.filial,
            tipo_documento=TipoDocumentoFiscal.NFCE,
            serie=1,
            proximo_numero=100,
        )
        SerieFiscal.objects.create(
            filial=self.filial,
            tipo_documento=TipoDocumentoFiscal.NFE,
            serie=55,
            proximo_numero=200,
        )
        NaturezaOperacao.objects.create(
            empresa=self.empresa,
            descricao="Venda ao consumidor",
            cfop="5102",
            tipo_documento=TipoDocumentoFiscal.NFCE,
        )
        NaturezaOperacao.objects.create(
            empresa=self.empresa,
            descricao="Venda online",
            cfop="5102",
            tipo_documento=TipoDocumentoFiscal.NFE,
        )


class DocumentoFiscalOriginConstraintTests(FiscalOriginFixtureMixin, TestCase):
    def _criar_documento(self, *, numero, venda=None, pedido=None, status=StatusDocumentoFiscal.PRONTO):
        return DocumentoFiscal.objects.create(
            filial=self.filial,
            venda=venda,
            pedido_online=pedido,
            tipo_documento=TipoDocumentoFiscal.NFCE if venda else TipoDocumentoFiscal.NFE,
            ambiente=AmbienteFiscal.HOMOLOGACAO,
            serie=1 if venda else 55,
            numero=numero,
            status=status,
            valor_total=Decimal("30.00"),
            usuario=self.usuario,
        )

    def test_banco_impede_dois_documentos_ativos_para_mesma_venda(self):
        primeiro = self._criar_documento(numero=1, venda=self.venda)

        with self.assertRaises(IntegrityError), transaction.atomic():
            self._criar_documento(
                numero=2,
                venda=self.venda,
                status=StatusDocumentoFiscal.REJEITADO,
            )

        primeiro.status = StatusDocumentoFiscal.CANCELADO
        primeiro.save(update_fields=["status"])
        novo = self._criar_documento(numero=3, venda=self.venda)
        self.assertEqual(novo.status, StatusDocumentoFiscal.PRONTO)

    def test_banco_impede_dois_documentos_ativos_para_mesmo_pedido(self):
        primeiro = self._criar_documento(numero=1, pedido=self.pedido)

        with self.assertRaises(IntegrityError), transaction.atomic():
            self._criar_documento(
                numero=2,
                pedido=self.pedido,
                status=StatusDocumentoFiscal.DENEGADO,
            )

        primeiro.status = StatusDocumentoFiscal.CANCELADO
        primeiro.save(update_fields=["status"])
        novo = self._criar_documento(numero=3, pedido=self.pedido)
        self.assertEqual(novo.status, StatusDocumentoFiscal.PRONTO)

    def test_banco_impede_venda_e_pedido_simultaneos(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._criar_documento(
                numero=4,
                venda=self.venda,
                pedido=self.pedido,
            )

    def test_banco_impede_documento_sem_origem(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._criar_documento(numero=5)

    def test_dominio_exige_exatamente_uma_origem(self):
        sem_origem = DocumentoFiscal(
            filial=self.filial,
            tipo_documento=TipoDocumentoFiscal.NFCE,
            ambiente=AmbienteFiscal.HOMOLOGACAO,
            serie=1,
            numero=6,
            status=StatusDocumentoFiscal.PRONTO,
            valor_total=Decimal("30.00"),
            usuario=self.usuario,
        )
        with self.assertRaisesMessage(ValidationError, "exatamente uma origem"):
            sem_origem.full_clean()

        duas_origens = DocumentoFiscal(
            filial=self.filial,
            venda=self.venda,
            pedido_online=self.pedido,
            tipo_documento=TipoDocumentoFiscal.NFCE,
            ambiente=AmbienteFiscal.HOMOLOGACAO,
            serie=1,
            numero=7,
            status=StatusDocumentoFiscal.PRONTO,
            valor_total=Decimal("30.00"),
            usuario=self.usuario,
        )
        with self.assertRaisesMessage(ValidationError, "exatamente uma origem"):
            duas_origens.full_clean()

    def test_dominio_rejeita_origem_de_outra_filial(self):
        outra_empresa = Empresa.objects.create(
            razao_social="Outra empresa fiscal LTDA",
            nome_fantasia="Outra empresa fiscal",
            cnpj="45.678.901/0001-23",
        )
        outra_filial = Filial.objects.create(
            empresa=outra_empresa,
            nome="Outra filial fiscal",
            cnpj=outra_empresa.cnpj,
        )
        documento = DocumentoFiscal(
            filial=outra_filial,
            venda=self.venda,
            tipo_documento=TipoDocumentoFiscal.NFCE,
            ambiente=AmbienteFiscal.HOMOLOGACAO,
            serie=1,
            numero=8,
            status=StatusDocumentoFiscal.PRONTO,
            valor_total=Decimal("30.00"),
            usuario=self.usuario,
        )

        with self.assertRaisesMessage(ValidationError, "mesma filial"):
            documento.full_clean()

    def test_admin_documento_fiscal_e_somente_leitura(self):
        admin_documento = DocumentoFiscalAdmin(DocumentoFiscal, AdminSite())

        self.assertFalse(admin_documento.has_add_permission(None))
        self.assertFalse(admin_documento.has_delete_permission(None))
        self.assertEqual(
            set(admin_documento.get_readonly_fields(None)),
            {campo.name for campo in DocumentoFiscal._meta.fields},
        )

    def test_fixture_prepara_documentos_pelos_dois_servicos(self):
        documento_venda = preparar_documento_venda(self.venda, self.usuario)
        documento_pedido = preparar_documento_pedido_online(self.pedido, self.usuario)

        self.assertEqual(documento_venda.venda, self.venda)
        self.assertEqual(documento_pedido.pedido_online, self.pedido)


@skipUnless(connection.vendor == "postgresql", "Concorrencia real exige PostgreSQL.")
class DocumentoFiscalOriginConcurrencyTests(FiscalOriginFixtureMixin, TransactionTestCase):
    reset_sequences = True

    def _executar_em_paralelo(self, model, objeto_id, preparar):
        barreira = Barrier(2)

        def executar():
            close_old_connections()
            try:
                objeto = model.objects.get(pk=objeto_id)
                usuario = get_user_model().objects.get(pk=self.usuario.pk)
                barreira.wait(timeout=10)
                documento = preparar(objeto, usuario)
                return "criado", documento.pk
            except ValidationError as exc:
                return "bloqueado", " ".join(exc.messages)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            resultados = list(executor.map(lambda _: executar(), range(2)))
        return resultados

    def test_duas_requisicoes_criam_apenas_um_documento_para_venda(self):
        resultados = self._executar_em_paralelo(
            Venda,
            self.venda.pk,
            preparar_documento_venda,
        )

        self.assertEqual(
            [item[0] for item in resultados].count("criado"),
            1,
            resultados,
        )
        self.assertEqual(
            [item[0] for item in resultados].count("bloqueado"),
            1,
            resultados,
        )
        mensagem_bloqueio = next(item[1] for item in resultados if item[0] == "bloqueado")
        self.assertIn("ja possui documento fiscal em andamento", mensagem_bloqueio)
        self.assertEqual(DocumentoFiscal.objects.filter(venda=self.venda).count(), 1)
        self.assertEqual(
            SerieFiscal.objects.get(tipo_documento=TipoDocumentoFiscal.NFCE).proximo_numero,
            101,
        )

    def test_duas_requisicoes_criam_apenas_um_documento_para_pedido(self):
        resultados = self._executar_em_paralelo(
            PedidoOnline,
            self.pedido.pk,
            preparar_documento_pedido_online,
        )

        self.assertEqual(
            [item[0] for item in resultados].count("criado"),
            1,
            resultados,
        )
        self.assertEqual(
            [item[0] for item in resultados].count("bloqueado"),
            1,
            resultados,
        )
        mensagem_bloqueio = next(item[1] for item in resultados if item[0] == "bloqueado")
        self.assertIn("ja possui documento fiscal em andamento", mensagem_bloqueio)
        self.assertEqual(DocumentoFiscal.objects.filter(pedido_online=self.pedido).count(), 1)
        self.assertEqual(
            SerieFiscal.objects.get(tipo_documento=TipoDocumentoFiscal.NFE).proximo_numero,
            201,
        )
