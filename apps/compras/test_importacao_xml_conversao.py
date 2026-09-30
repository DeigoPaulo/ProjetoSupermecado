from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.compras.models import EntradaCompra, ItemEntradaCompra, ItemPedidoCompra, PedidoCompra, StatusEntradaCompra, StatusPedidoCompra
from apps.compras.services import cancelar_entrada_compra, finalizar_entrada_compra
from apps.compras.services_xml import importar_xml_entrada
from apps.empresas.models import Empresa, Filial
from apps.estoque.models import Estoque, LoteEstoque
from apps.financeiro.models import ContaFinanceira
from apps.fornecedores.models import Fornecedor
from apps.produtos.models import Categoria, CodigoBarrasProduto, Produto, ProdutoFornecedor


class ImportacaoXMLConversaoUnidadeTests(TestCase):
    CHAVE = "35260912345678000199550010000001921000001927"
    GTIN_UNIDADE = "7894900705119"
    GTIN_UNIDADE_14 = "07894900705119"
    GTIN_CAIXA = "27894900705113"

    def setUp(self):
        self.usuario = get_user_model().objects.create_superuser(
            "importador_conversao", "conversao@example.invalid", "123"
        )
        self.empresa = Empresa.objects.create(
            razao_social="Mercado Sintetico",
            nome_fantasia="Mercado Sintetico",
            cnpj="98.765.432/0001-10",
        )
        self.filial = Filial.objects.create(
            empresa=self.empresa,
            nome="Matriz Sintetica",
            cnpj="98.765.432/0001-10",
        )
        self.fornecedor = Fornecedor.objects.create(
            razao_social="Fornecedor Sintetico",
            nome_fantasia="Fornecedor Sintetico",
            cnpj="12.345.678/0001-99",
        )
        self.categoria = Categoria.all_objects.create(nome="Bebidas Sinteticas")
        self.produto = Produto.objects.create(
            codigo_barras=self.GTIN_UNIDADE,
            codigo_interno="REFRI-ZERO-1L",
            nome="REFRIGERANTE ZERO 1L",
            categoria=self.categoria,
            unidade="UN",
            unidade_compra="CX",
            fator_conversao_compra=Decimal("12.000"),
            preco_custo=Decimal("3.000000"),
            preco_venda=Decimal("8.00"),
        )
        self.codigo_caixa = CodigoBarrasProduto.objects.create(
            produto=self.produto,
            codigo=self.GTIN_CAIXA,
            tipo="CAIXA",
            fator_conversao=Decimal("12.000"),
            permite_venda=False,
        )
        self.client.force_login(self.usuario)

    def _xml(
        self,
        *,
        cprod="REFRI-ZERO-1L",
        cean=None,
        cean_trib=None,
        ucom="CX",
        qcom="3.0000",
        vuncom="52.2700000000",
        vprod="156.81",
        vnf="168.14",
        rastros="",
    ):
        cean = self.GTIN_CAIXA if cean is None else cean
        cean_trib = self.GTIN_UNIDADE if cean_trib is None else cean_trib
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">
  <NFe><infNFe Id="NFe{self.CHAVE}" versao="4.00">
    <ide><nNF>192</nNF><dhEmi>2026-09-30T08:00:00-03:00</dhEmi></ide>
    <emit><CNPJ>12345678000199</CNPJ><xNome>Fornecedor Sintetico</xNome></emit>
    <dest><CNPJ>98765432000110</CNPJ><xNome>Mercado Sintetico</xNome></dest>
    <det nItem="1"><prod>
      <cProd>{cprod}</cProd><cEAN>{cean}</cEAN><xProd>REFRIGERANTE ZERO 1L</xProd>
      <uCom>{ucom}</uCom><qCom>{qcom}</qCom><vUnCom>{vuncom}</vUnCom><vProd>{vprod}</vProd>
      <cEANTrib>{cean_trib}</cEANTrib>{rastros}
    </prod></det>
    <total><ICMSTot><vProd>{vprod}</vProd><vNF>{vnf}</vNF></ICMSTot></total>
  </infNFe></NFe>
  <protNFe><infProt><chNFe>{self.CHAVE}</chNFe><cStat>100</cStat></infProt></protNFe>
</nfeProc>""".encode()

    def test_caso_sanitizado_converte_caixa_finaliza_financeiro_e_cancela(self):
        entrada = importar_xml_entrada(self._xml(), usuario=self.usuario)
        item = entrada.itens.get()

        self.assertEqual(entrada.status, StatusEntradaCompra.RASCUNHO)
        self.assertEqual(item.quantidade, Decimal("36.000"))
        self.assertEqual(item.custo_unitario, Decimal("4.355833"))
        self.assertEqual(item.total, Decimal("156.81"))
        self.assertEqual(entrada.total_produtos, Decimal("156.81"))
        self.assertEqual(entrada.total_documento, Decimal("168.14"))
        self.assertFalse(Estoque.objects.exists())
        self.assertEqual(
            item.origem_xml_snapshot,
            {
                "contrato": "purchase_xml_unit_conversion_v1",
                "nItem": "1",
                "cProd": "REFRI-ZERO-1L",
                "cEAN": self.GTIN_CAIXA,
                "cEANTrib": self.GTIN_UNIDADE,
                "uCom": "CX",
                "qCom": "3.0000",
                "vUnCom": "52.2700000000",
                "vProd": "156.81",
                "unidade_base": "UN",
                "fator_conversao": "12.000",
                "quantidade_base": "36.000",
                "quantidade_base_item": "36.000",
                "custo_unitario_base": "4.355833",
                "fonte_conversao": "CODIGO_BARRAS_ADICIONAL+UNIDADE_COMPRA",
            },
        )

        detalhe = self.client.get(f"/compras/{entrada.pk}/")
        self.assertContains(detalhe, "Origem XML: 3.0000 CX × fator 12.000")
        self.assertContains(detalhe, "Estoque: 36.000 UN")
        self.assertContains(detalhe, "Custo por UN: R$ 4,355833")
        revisao = self.client.get(f"/compras/{entrada.pk}/editar/")
        self.assertContains(revisao, "Origem XML: 3.0000 CX × fator 12.000")
        self.assertContains(revisao, "Estoque: 36.000 UN")

        finalizar_entrada_compra(entrada)
        self.produto.refresh_from_db()
        self.assertEqual(
            Estoque.objects.get(produto=self.produto, filial=self.filial).quantidade_atual,
            Decimal("36.000"),
        )
        self.assertEqual(self.produto.preco_custo, Decimal("4.355833"))
        self.assertEqual(ContaFinanceira.objects.get(entrada_compra=entrada).valor, Decimal("168.14"))

        cancelar_entrada_compra(entrada, usuario=self.usuario, motivo="Teste sintetico")
        self.assertEqual(
            Estoque.objects.get(produto=self.produto, filial=self.filial).quantidade_atual,
            Decimal("0.000"),
        )

    def test_fator_um_preserva_quantidade_e_custo(self):
        self.codigo_caixa.delete()
        self.produto.unidade_compra = "UN"
        self.produto.fator_conversao_compra = Decimal("1.000")
        self.produto.save(update_fields=["unidade_compra", "fator_conversao_compra", "updated_at"])

        entrada = importar_xml_entrada(
            self._xml(
                cean=self.GTIN_UNIDADE,
                cean_trib=self.GTIN_UNIDADE,
                ucom="UN",
                qcom="3",
                vuncom="5",
                vprod="15.00",
                vnf="15.00",
            ),
            usuario=self.usuario,
        )

        item = entrada.itens.get()
        self.assertEqual(item.quantidade, Decimal("3.000"))
        self.assertEqual(item.custo_unitario, Decimal("5.000000"))
        self.assertEqual(item.total, Decimal("15.00"))

    def test_unidade_compra_aplica_fator_sem_codigo_adicional(self):
        self.codigo_caixa.delete()

        item = importar_xml_entrada(
            self._xml(cean=self.GTIN_UNIDADE, cean_trib=self.GTIN_UNIDADE),
            usuario=self.usuario,
        ).itens.get()

        self.assertEqual(item.quantidade, Decimal("36.000"))
        self.assertEqual(item.origem_xml_snapshot["fonte_conversao"], "UNIDADE_COMPRA")

    def test_codigo_adicional_aplica_fator_mesmo_sem_permissao_de_venda(self):
        self.produto.unidade_compra = "UN"
        self.produto.fator_conversao_compra = Decimal("1.000")
        self.produto.save(update_fields=["unidade_compra", "fator_conversao_compra", "updated_at"])

        item = importar_xml_entrada(self._xml(ucom="FD"), usuario=self.usuario).itens.get()

        self.assertEqual(item.quantidade, Decimal("36.000"))
        self.assertEqual(item.origem_xml_snapshot["fonte_conversao"], "CODIGO_BARRAS_ADICIONAL")

    def test_codigo_do_fornecedor_localiza_produto_no_fornecedor_correto(self):
        self.codigo_caixa.delete()
        outro_fornecedor = Fornecedor.objects.create(
            razao_social="Outro fornecedor sintetico",
            cnpj="11.111.111/0001-11",
        )
        outro_produto = Produto.objects.create(
            codigo_barras="7894900011513",
            codigo_interno="OUTRO-ABC",
            nome="Outro produto sintetico",
            categoria=self.categoria,
            preco_venda=Decimal("5.00"),
        )
        ProdutoFornecedor.objects.create(
            produto=outro_produto,
            fornecedor=outro_fornecedor,
            codigo_no_fornecedor="ABC123",
        )
        ProdutoFornecedor.objects.create(
            produto=self.produto,
            fornecedor=self.fornecedor,
            codigo_no_fornecedor="ABC123",
        )

        item = importar_xml_entrada(
            self._xml(cprod="ABC123", cean="SEM GTIN", cean_trib="SEM GTIN"),
            usuario=self.usuario,
        ).itens.get()

        self.assertEqual(item.produto, self.produto)
        self.assertEqual(item.quantidade, Decimal("36.000"))

    def test_conflito_gtin_e_codigo_do_fornecedor_bloqueia_sem_rascunho(self):
        outro = Produto.objects.create(
            codigo_barras="7894900011513",
            codigo_interno="OUTRO",
            nome="Outro produto sintetico",
            categoria=self.categoria,
            preco_venda=Decimal("5.00"),
        )
        ProdutoFornecedor.objects.create(
            produto=outro,
            fornecedor=self.fornecedor,
            codigo_no_fornecedor="ABC123",
        )

        with self.assertRaisesMessage(ValidationError, "Conflito na identificação do produto do item 1"):
            importar_xml_entrada(self._xml(cprod="ABC123"), usuario=self.usuario)

        self.assertFalse(EntradaCompra.objects.exists())
        self.assertFalse(ItemEntradaCompra.objects.exists())

    def test_conflito_entre_cean_e_ceantrib_bloqueia(self):
        outro = Produto.objects.create(
            codigo_barras="7894900011513",
            codigo_interno="OUTRO-GTIN",
            nome="Outro GTIN sintetico",
            categoria=self.categoria,
            preco_venda=Decimal("5.00"),
        )

        with self.assertRaisesMessage(ValidationError, "Conflito na identificação do produto do item 1"):
            importar_xml_entrada(
                self._xml(cean_trib=outro.codigo_barras),
                usuario=self.usuario,
            )

        self.assertFalse(EntradaCompra.objects.exists())

    def test_conflito_entre_fator_do_codigo_e_unidade_compra_bloqueia(self):
        self.codigo_caixa.fator_conversao = Decimal("6.000")
        self.codigo_caixa.save(update_fields=["fator_conversao", "updated_at"])

        with self.assertRaisesMessage(ValidationError, "Conversão de unidade ambígua para o item 1"):
            importar_xml_entrada(self._xml(), usuario=self.usuario)

        self.assertFalse(EntradaCompra.objects.exists())
        self.assertFalse(ItemEntradaCompra.objects.exists())

    def test_unidade_desconhecida_sem_codigo_de_embalagem_bloqueia(self):
        self.codigo_caixa.delete()

        with self.assertRaisesMessage(ValidationError, "Configure a unidade de compra"):
            importar_xml_entrada(
                self._xml(cean=self.GTIN_UNIDADE, cean_trib=self.GTIN_UNIDADE, ucom="FD"),
                usuario=self.usuario,
            )

        self.assertFalse(EntradaCompra.objects.exists())

    def test_fator_invalido_bloqueia(self):
        self.codigo_caixa.delete()
        Produto.objects.filter(pk=self.produto.pk).update(fator_conversao_compra=Decimal("0.000"))

        with self.assertRaisesMessage(ValidationError, "Fator de conversão inválido"):
            importar_xml_entrada(
                self._xml(cean=self.GTIN_UNIDADE, cean_trib=self.GTIN_UNIDADE),
                usuario=self.usuario,
            )

        self.assertFalse(EntradaCompra.objects.exists())

    def test_quantidade_convertida_nao_representavel_bloqueia(self):
        with self.assertRaisesMessage(ValidationError, "Precisão incompatível"):
            importar_xml_entrada(
                self._xml(qcom="0.3333", vuncom="10", vprod="3.33", vnf="3.33"),
                usuario=self.usuario,
            )

        self.assertFalse(EntradaCompra.objects.exists())

    def test_gtin13_e_gtin14_equivalentes_localizam_mesmo_produto(self):
        self.codigo_caixa.delete()
        self.produto.unidade_compra = "UN"
        self.produto.fator_conversao_compra = Decimal("1.000")
        self.produto.save(update_fields=["unidade_compra", "fator_conversao_compra", "updated_at"])

        item = importar_xml_entrada(
            self._xml(
                cean=self.GTIN_UNIDADE_14,
                cean_trib=self.GTIN_UNIDADE_14,
                ucom="UN",
                qcom="1",
                vuncom="5",
                vprod="5.00",
                vnf="5.00",
            ),
            usuario=self.usuario,
        ).itens.get()

        self.assertEqual(item.produto, self.produto)

    def test_codigo_interno_arbitrario_nao_perde_zero_a_esquerda(self):
        self.codigo_caixa.delete()
        self.produto.codigo_interno = "00123"
        self.produto.save(update_fields=["codigo_interno", "updated_at"])

        with self.assertRaisesMessage(ValidationError, "Nenhuma entrada foi criada"):
            importar_xml_entrada(
                self._xml(cprod="123", cean="SEM GTIN", cean_trib="SEM GTIN"),
                usuario=self.usuario,
            )

    def test_pedido_em_unidade_base_casa_com_xml_convertido(self):
        pedido = PedidoCompra.objects.create(
            fornecedor=self.fornecedor,
            filial=self.filial,
            usuario=self.usuario,
            referencia="PED-CX12",
            status=StatusPedidoCompra.ENVIADO,
            total_previsto=Decimal("156.81"),
        )
        ItemPedidoCompra.objects.create(
            pedido=pedido,
            produto=self.produto,
            quantidade=Decimal("36.000"),
            custo_unitario_previsto=Decimal("4.355833"),
            total_previsto=Decimal("156.81"),
        )

        entrada = importar_xml_entrada(self._xml(), usuario=self.usuario)

        pedido.refresh_from_db()
        self.assertEqual(entrada.pedido_origem, pedido)
        self.assertEqual(pedido.status, StatusPedidoCompra.CONVERTIDO)

    def test_lotes_sao_convertidos_e_preservam_somas(self):
        self.produto.exige_lote = True
        self.produto.save(update_fields=["exige_lote", "updated_at"])
        rastros = (
            "<rastro><nLote>LOTE-A</nLote><qLote>2.0000</qLote>"
            "<dFab>2026-09-01</dFab><dVal>2027-09-01</dVal></rastro>"
            "<rastro><nLote>LOTE-B</nLote><qLote>1.0000</qLote>"
            "<dFab>2026-09-01</dFab><dVal>2027-09-01</dVal></rastro>"
        )

        entrada = importar_xml_entrada(self._xml(rastros=rastros), usuario=self.usuario)
        itens = list(entrada.itens.order_by("codigo_lote"))

        self.assertEqual([item.quantidade for item in itens], [Decimal("24.000"), Decimal("12.000")])
        self.assertEqual(sum((item.quantidade for item in itens), Decimal("0.000")), Decimal("36.000"))
        self.assertEqual([item.origem_xml_snapshot["qLote"] for item in itens], ["2.0000", "1.0000"])

        finalizar_entrada_compra(entrada)
        self.assertEqual(
            list(LoteEstoque.objects.order_by("codigo").values_list("quantidade_atual", flat=True)),
            [Decimal("24.000"), Decimal("12.000")],
        )
