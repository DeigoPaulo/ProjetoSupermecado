import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from apps.accounts.models import PerfilUsuario, TipoPerfil
from apps.auditoria.models import LogAuditoria
from apps.compras.models import EntradaCompra, ItemEntradaCompra
from apps.compras.services_xml_assistido import analisar_xml_entrada, aplicar_resolucoes_e_importar_xml
from apps.empresas.models import Empresa, Filial
from apps.estoque.models import Estoque
from apps.financeiro.models import ContaFinanceira
from apps.fornecedores.models import Fornecedor
from apps.produtos.models import Categoria, CodigoBarrasProduto, Produto, ProdutoFornecedor


class ImportacaoXMLAssistidaTests(TestCase):
    CHAVE = "35260912345678000199550010000001931000001932"
    GTIN_UNIDADE = "7894900705119"
    GTIN_CAIXA = "27894900705113"

    def setUp(self):
        self.usuario = get_user_model().objects.create_superuser(
            "assistente_xml", "assistente@example.invalid", "123"
        )
        self.empresa = Empresa.objects.create(
            razao_social="Mercado Assistido Sintetico",
            nome_fantasia="Mercado Assistido",
            cnpj="98.765.432/0001-10",
        )
        self.filial = Filial.objects.create(
            empresa=self.empresa,
            nome="Matriz Assistida",
            cnpj="98.765.432/0001-10",
        )
        self.fornecedor = Fornecedor.objects.create(
            empresa=self.empresa,
            razao_social="Fornecedor Assistido Sintetico",
            nome_fantasia="Fornecedor Assistido",
            cnpj="12.345.678/0001-99",
        )
        self.categoria = Categoria.all_objects.create(nome="Categoria Assistida")
        self.produto = Produto.objects.create(
            codigo_barras=self.GTIN_UNIDADE,
            codigo_interno="ASSISTIDO-1",
            nome="REFRIGERANTE ZERO 1L",
            categoria=self.categoria,
            unidade="UN",
            unidade_compra="UN",
            fator_conversao_compra=Decimal("1.000"),
            preco_custo=Decimal("3.000000"),
            preco_venda=Decimal("8.00"),
        )
        self.client.force_login(self.usuario)

    def _xml(
        self,
        *,
        chave=None,
        numero="193",
        cprod="ASSISTIDO-1",
        cean=None,
        cean_trib=None,
        descricao="REFRIGERANTE ZERO 1L CX12",
        ucom="CX",
        qcom="3.0000",
        vuncom="52.2700000000",
        vprod="156.81",
        item_extra="",
    ):
        chave = chave or self.CHAVE
        cean = self.GTIN_CAIXA if cean is None else cean
        cean_trib = self.GTIN_UNIDADE if cean_trib is None else cean_trib
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">
  <NFe><infNFe Id="NFe{chave}" versao="4.00">
    <ide><nNF>{numero}</nNF><dhEmi>2026-09-30T08:00:00-03:00</dhEmi></ide>
    <emit><CNPJ>12345678000199</CNPJ><xNome>Fornecedor Assistido</xNome></emit>
    <dest><CNPJ>98765432000110</CNPJ><xNome>Mercado Assistido</xNome></dest>
    <det nItem="1"><prod><cProd>{cprod}</cProd><cEAN>{cean}</cEAN><xProd>{descricao}</xProd>
      <NCM>22021000</NCM><CEST>0301100</CEST><uCom>{ucom}</uCom><qCom>{qcom}</qCom>
      <vUnCom>{vuncom}</vUnCom><vProd>{vprod}</vProd><cEANTrib>{cean_trib}</cEANTrib>
    </prod><imposto><ICMS><ICMS10><CST>10</CST></ICMS10></ICMS></imposto></det>
    {item_extra}
    <total><ICMSTot><vProd>{vprod}</vProd><vNF>{vprod}</vNF></ICMSTot></total>
  </infNFe></NFe><protNFe><infProt><chNFe>{chave}</chNFe><cStat>100</cStat></infProt></protNFe>
</nfeProc>""".encode()

    def _decisao_configurar(self, **extra):
        decisao = {
            "numero": "1",
            "acao": "configurar",
            "unidade_base": "UN",
            "unidade_compra": "CX",
            "fator": "12",
            "definir_como_padrao": True,
        }
        decisao.update(extra)
        return decisao

    def test_analise_pendente_nao_grava_nem_movimenta(self):
        analise = analisar_xml_entrada(self._xml(), usuario=self.usuario)

        self.assertEqual(analise["itens"][0]["status"], "CONVERSAO_NAO_CONFIGURADA")
        self.assertEqual(analise["itens"][0]["ncm_fornecedor"], "22021000")
        self.assertEqual(Produto.objects.count(), 1)
        self.assertFalse(CodigoBarrasProduto.objects.exists())
        self.assertFalse(EntradaCompra.objects.exists())
        self.assertFalse(Estoque.objects.exists())
        self.assertFalse(ContaFinanceira.objects.exists())

    def test_confirma_caixa_e_segunda_nfe_reutiliza_aprendizado(self):
        xml = self._xml()
        analise = analisar_xml_entrada(xml, usuario=self.usuario)
        entrada = aplicar_resolucoes_e_importar_xml(
            xml,
            hash_analisado=analise["hash_sha256"],
            decisoes=[self._decisao_configurar()],
            usuario=self.usuario,
        )
        item = entrada.itens.get()
        self.assertEqual(item.quantidade, Decimal("36.000"))
        self.assertEqual(item.custo_unitario, Decimal("4.355833"))
        self.assertEqual(item.origem_xml_snapshot["fator_conversao"], "12.000")
        codigo = CodigoBarrasProduto.objects.get(codigo=self.GTIN_CAIXA)
        self.assertEqual(codigo.fator_conversao, Decimal("12.000"))
        self.assertFalse(Estoque.objects.exists())
        self.assertFalse(ContaFinanceira.objects.exists())

        segunda_chave = "35260912345678000199550010000001941000001948"
        segunda = self._xml(
            chave=segunda_chave,
            numero="194",
            qcom="5.0000",
            vuncom="52.2700000000",
            vprod="261.35",
        )
        nova_analise = analisar_xml_entrada(segunda, usuario=self.usuario)
        self.assertEqual(nova_analise["itens"][0]["status"], "RESOLVIDO")
        nova_entrada = aplicar_resolucoes_e_importar_xml(
            segunda,
            hash_analisado=nova_analise["hash_sha256"],
            decisoes=[],
            usuario=self.usuario,
        )
        self.assertEqual(nova_entrada.itens.get().quantidade, Decimal("60.000"))

    def test_descricao_cx12_nao_infere_fator(self):
        analise = analisar_xml_entrada(self._xml(descricao="PRODUTO PROMOCIONAL CX12"), usuario=self.usuario)
        self.assertEqual(analise["itens"][0]["status"], "CONVERSAO_NAO_CONFIGURADA")
        self.produto.refresh_from_db()
        self.assertEqual(self.produto.fator_conversao_compra, Decimal("1.000"))

    def test_hash_diferente_bloqueia_sem_gravacao(self):
        xml = self._xml()
        with self.assertRaisesMessage(ValidationError, "arquivo XML mudou"):
            aplicar_resolucoes_e_importar_xml(
                xml,
                hash_analisado="0" * 64,
                decisoes=[self._decisao_configurar()],
                usuario=self.usuario,
            )
        self.assertFalse(EntradaCompra.objects.exists())
        self.assertFalse(CodigoBarrasProduto.objects.exists())

    def test_usuario_compras_analisa_mas_nao_altera_cadastro(self):
        usuario = get_user_model().objects.create_user("comprador", password="123")
        PerfilUsuario.objects.create(usuario=usuario, filial=self.filial, tipo=TipoPerfil.COMPRAS)
        xml = self._xml()
        analise = analisar_xml_entrada(xml, usuario=usuario)
        self.assertFalse(analise["pode_configurar"])
        with self.assertRaises(PermissionDenied):
            aplicar_resolucoes_e_importar_xml(
                xml,
                hash_analisado=analise["hash_sha256"],
                decisoes=[self._decisao_configurar()],
                usuario=usuario,
            )
        self.assertFalse(CodigoBarrasProduto.objects.exists())

    def test_produto_desconhecido_pode_ser_vinculado_ao_fornecedor(self):
        xml = self._xml(cprod="ABC123", cean="SEM GTIN", cean_trib="SEM GTIN")
        analise = analisar_xml_entrada(xml, usuario=self.usuario)
        self.assertEqual(analise["itens"][0]["status"], "PRODUTO_NAO_ENCONTRADO")
        decisao = self._decisao_configurar(acao="vincular", produto_id=self.produto.pk)
        entrada = aplicar_resolucoes_e_importar_xml(
            xml,
            hash_analisado=analise["hash_sha256"],
            decisoes=[decisao],
            usuario=self.usuario,
        )
        self.assertEqual(entrada.itens.get().produto, self.produto)
        self.assertTrue(
            ProdutoFornecedor.objects.filter(
                produto=self.produto,
                fornecedor=self.fornecedor,
                codigo_no_fornecedor="ABC123",
            ).exists()
        )

    def test_produto_novo_usa_formulario_e_nao_copia_tributacao(self):
        xml = self._xml(cprod="NOVO-ABC", cean=self.GTIN_CAIXA, cean_trib="SEM GTIN")
        analise = analisar_xml_entrada(xml, usuario=self.usuario)
        decisao = {
            "numero": "1",
            "acao": "cadastrar",
            "nome": "Produto novo assistido",
            "categoria_id": self.categoria.pk,
            "unidade_base": "UN",
            "unidade_compra": "CX",
            "fator": "12",
            "preco_venda": "9.90",
            "codigo_principal": "7894900011513",
        }
        entrada = aplicar_resolucoes_e_importar_xml(
            xml,
            hash_analisado=analise["hash_sha256"],
            decisoes=[decisao],
            usuario=self.usuario,
        )
        novo = entrada.itens.get().produto
        self.assertEqual(novo.nome, "Produto novo assistido")
        self.assertEqual(novo.unidade_compra, "CX")
        self.assertEqual(novo.fator_conversao_compra, Decimal("12.000"))
        self.assertEqual(novo.ncm, "")
        self.assertEqual(novo.cest, "")
        self.assertEqual(novo.cst_icms, "")
        self.assertEqual(novo.cst_pis, "")
        self.assertTrue(CodigoBarrasProduto.objects.filter(produto=novo, codigo=self.GTIN_CAIXA).exists())
        self.assertTrue(ProdutoFornecedor.objects.filter(produto=novo, fornecedor=self.fornecedor).exists())
        self.assertTrue(LogAuditoria.objects.filter(acao="CADASTRO_PRODUTO_ASSISTIDO_XML").exists())

    def test_falha_em_item_posterior_reverte_aprendizado_do_primeiro(self):
        segundo = """<det nItem="2"><prod><cProd>DESCONHECIDO</cProd><cEAN>SEM GTIN</cEAN>
          <xProd>ITEM DESCONHECIDO</xProd><uCom>ZZ</uCom><qCom>1</qCom><vUnCom>1</vUnCom>
          <vProd>1.00</vProd><cEANTrib>SEM GTIN</cEANTrib></prod></det>"""
        xml = self._xml(item_extra=segundo)
        analise = analisar_xml_entrada(xml, usuario=self.usuario)
        with self.assertRaises(ValidationError):
            aplicar_resolucoes_e_importar_xml(
                xml,
                hash_analisado=analise["hash_sha256"],
                decisoes=[self._decisao_configurar()],
                usuario=self.usuario,
            )
        self.assertFalse(CodigoBarrasProduto.objects.exists())
        self.assertFalse(ProdutoFornecedor.objects.exists())
        self.assertFalse(EntradaCompra.objects.exists())
        self.assertFalse(ItemEntradaCompra.objects.exists())

    def test_alteracao_futura_preserva_snapshot_anterior(self):
        xml = self._xml()
        analise = analisar_xml_entrada(xml, usuario=self.usuario)
        primeira = aplicar_resolucoes_e_importar_xml(
            xml,
            hash_analisado=analise["hash_sha256"],
            decisoes=[self._decisao_configurar()],
            usuario=self.usuario,
        )
        primeiro_item = primeira.itens.get()
        codigo = CodigoBarrasProduto.objects.get(codigo=self.GTIN_CAIXA)
        self.produto.refresh_from_db()
        self.produto.fator_conversao_compra = Decimal("15.000")
        self.produto.save(update_fields=["fator_conversao_compra", "updated_at"])
        codigo.fator_conversao = Decimal("15.000")
        codigo.save(update_fields=["fator_conversao", "updated_at"])

        segunda = self._xml(
            chave="35260912345678000199550010000001951000001953",
            numero="195",
            qcom="2.0000",
            vuncom="52.2700000000",
            vprod="104.54",
        )
        segunda_analise = analisar_xml_entrada(segunda, usuario=self.usuario)
        segunda_entrada = aplicar_resolucoes_e_importar_xml(
            segunda,
            hash_analisado=segunda_analise["hash_sha256"],
            decisoes=[],
            usuario=self.usuario,
        )

        primeiro_item.refresh_from_db()
        self.assertEqual(primeiro_item.quantidade, Decimal("36.000"))
        self.assertEqual(primeiro_item.origem_xml_snapshot["fator_conversao"], "12.000")
        self.assertEqual(segunda_entrada.itens.get().quantidade, Decimal("30.000"))
        self.assertEqual(
            segunda_entrada.itens.get().origem_xml_snapshot["fator_conversao"],
            "15.000",
        )

    def test_embalagem_adicional_nao_substitui_padrao(self):
        self.produto.unidade_compra = "CX"
        self.produto.fator_conversao_compra = Decimal("12.000")
        self.produto.save(update_fields=["unidade_compra", "fator_conversao_compra", "updated_at"])
        codigo_fardo = "37894900705110"
        xml = self._xml(
            chave="35260912345678000199550010000001961000001969",
            numero="196",
            cean=codigo_fardo,
            ucom="FD",
            qcom="1.0000",
            vuncom="90.00",
            vprod="90.00",
        )
        analise = analisar_xml_entrada(xml, usuario=self.usuario)
        self.assertEqual(analise["itens"][0]["status"], "CONVERSAO_NAO_CONFIGURADA")
        decisao = self._decisao_configurar(
            unidade_compra="FD",
            fator="24",
            definir_como_padrao=False,
        )
        entrada = aplicar_resolucoes_e_importar_xml(
            xml,
            hash_analisado=analise["hash_sha256"],
            decisoes=[decisao],
            usuario=self.usuario,
        )
        self.produto.refresh_from_db()
        self.assertEqual(self.produto.unidade_compra, "CX")
        self.assertEqual(self.produto.fator_conversao_compra, Decimal("12.000"))
        self.assertEqual(entrada.itens.get().quantidade, Decimal("24.000"))
        self.assertEqual(
            CodigoBarrasProduto.objects.get(codigo=codigo_fardo).fator_conversao,
            Decimal("24.000"),
        )

    def test_endpoint_ajax_analisa_e_confirma_reenviando_arquivo(self):
        xml = self._xml()
        analise_response = self.client.post(
            "/compras/importar-xml/",
            {
                "acao": "analisar",
                "arquivo_xml": SimpleUploadedFile("entrada.xml", xml, content_type="application/xml"),
                "gerar_conta_financeira": "on",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(analise_response.status_code, 200)
        analise = analise_response.json()
        self.assertEqual(analise["itens"][0]["status"], "CONVERSAO_NAO_CONFIGURADA")

        confirmacao = self.client.post(
            "/compras/importar-xml/",
            {
                "acao": "confirmar",
                "hash_sha256": analise["hash_sha256"],
                "decisoes": json.dumps([self._decisao_configurar()]),
                "arquivo_xml": SimpleUploadedFile("entrada.xml", xml, content_type="application/xml"),
                "gerar_conta_financeira": "on",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(confirmacao.status_code, 200)
        self.assertEqual(confirmacao.json()["redirect"], f"/compras/{EntradaCompra.objects.get().pk}/editar/")
