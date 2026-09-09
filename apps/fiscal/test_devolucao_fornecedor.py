from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.accounts.models import PerfilUsuario, TipoPerfil
from apps.compras.models import EntradaCompra, ItemEntradaCompra, StatusEntradaCompra
from apps.compras.services import cancelar_entrada_compra
from apps.empresas.models import Empresa, Filial
from apps.fornecedores.models import Fornecedor
from apps.produtos.models import Categoria, Produto

from .devolucao_fornecedor import (
    CONTRATO_PREPARACAO_DEVOLUCAO_FORNECEDOR,
    CONTRATO_RASCUNHO_DEVOLUCAO_FORNECEDOR,
    cancelar_rascunho_devolucao_fornecedor,
    preparar_devolucao_fornecedor,
    salvar_rascunho_devolucao_fornecedor,
)
from .models import (
    DocumentoDFeRecebido,
    DocumentoFiscal,
    ItemRascunhoDevolucaoFornecedor,
    RascunhoDevolucaoFornecedor,
    StatusRascunhoDevolucaoFornecedor,
)


class PreparacaoDevolucaoFornecedorTests(TestCase):
    CHAVE = "52260811111111000111550010000001231000001230"

    def setUp(self):
        self.usuario = get_user_model().objects.create_user("compras_devolucao")
        self.empresa = Empresa.objects.create(
            razao_social="Mercado Destino Ltda",
            nome_fantasia="Mercado Destino",
            cnpj="22.222.222/0001-22",
        )
        self.filial = Filial.objects.create(
            empresa=self.empresa,
            nome="Matriz",
            cnpj=self.empresa.cnpj,
            uf="GO",
        )
        PerfilUsuario.objects.create(
            usuario=self.usuario,
            filial=self.filial,
            tipo=TipoPerfil.COMPRAS,
        )
        self.fornecedor = Fornecedor.objects.create(
            empresa=self.empresa,
            razao_social="Fornecedor Origem Ltda",
            cnpj="11.111.111/0001-11",
        )
        categoria = Categoria.all_objects.create(nome="Devolução fiscal")
        produto = Produto.objects.create(
            codigo_barras="7891111111111",
            nome="Produto recebido",
            categoria=categoria,
            preco_custo=Decimal("10.00"),
            preco_venda=Decimal("15.00"),
        )
        self.entrada = EntradaCompra.objects.create(
            fornecedor=self.fornecedor,
            filial=self.filial,
            usuario=self.usuario,
            chave_acesso_xml=self.CHAVE,
            status=StatusEntradaCompra.FINALIZADA,
            total_produtos=Decimal("20.00"),
        )
        self.item_entrada = ItemEntradaCompra.objects.create(
            entrada=self.entrada,
            produto=produto,
            quantidade=Decimal("2.000"),
            custo_unitario=Decimal("10.00"),
            total=Decimal("20.00"),
        )

    def _registrar_dfe(self, xml=None):
        return DocumentoDFeRecebido.objects.create(
            empresa=self.empresa,
            filial_destino=self.filial,
            entrada_compra=self.entrada,
            chave_acesso=self.CHAVE,
            emitente_cnpj="11111111000111",
            xml_conteudo=xml or self._xml(),
        )

    def _xml(self):
        return f"""<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">
          <NFe><infNFe Id="NFe{self.CHAVE}"><ide><mod>55</mod><finNFe>1</finNFe><dhEmi>2026-09-01T10:00:00-03:00</dhEmi></ide>
          <emit><CNPJ>11111111000111</CNPJ></emit><dest><CNPJ>22222222000122</CNPJ></dest>
          <det nItem="1"><prod><cProd>ABC</cProd><xProd>Produto recebido</xProd><NCM>10063021</NCM><CFOP>5102</CFOP><uCom>UN</uCom><qCom>2.0000</qCom><vUnCom>10.00</vUnCom><vProd>20.00</vProd></prod>
          <imposto><ICMS><ICMS00><orig>0</orig><CST>00</CST><vBC>20.00</vBC><pICMS>17.00</pICMS><vICMS>3.40</vICMS></ICMS00></ICMS></imposto></det>
          </infNFe></NFe><protNFe><infProt><chNFe>{self.CHAVE}</chNFe><cStat>100</cStat></infProt></protNFe>
        </nfeProc>"""

    def test_consolida_evidencias_sem_criar_documento_ou_escolher_tributacao(self):
        self._registrar_dfe()

        resultado = preparar_devolucao_fornecedor(self.entrada)

        self.assertEqual(resultado["contrato"], CONTRATO_PREPARACAO_DEVOLUCAO_FORNECEDOR)
        self.assertEqual(resultado["estado"], "BASE_DOCUMENTAL_DISPONIVEL")
        self.assertFalse(resultado["permite_emissao"])
        self.assertFalse(resultado["permite_transmissao"])
        self.assertEqual(resultado["documento_planejado"]["finalidade"], "4")
        self.assertIsNone(resultado["documento_planejado"]["cfop"])
        self.assertIsNone(resultado["documento_planejado"]["tributacao"])
        self.assertEqual(resultado["itens_xml_original"][0]["cfop"], "5102")
        self.assertEqual(resultado["itens_xml_original"][0]["valor_icms"], "3.40")
        self.assertFalse(DocumentoFiscal.objects.exists())

    def test_sem_xml_integral_mostra_bloqueios_em_vez_de_inventar_dados(self):
        resultado = preparar_devolucao_fornecedor(self.entrada)

        self.assertEqual(resultado["estado"], "INCOMPLETA")
        self.assertIn("XML autorizado original preservado", resultado["bloqueios_documentais"])
        self.assertIn("Itens fiscais originais disponíveis", resultado["bloqueios_documentais"])
        self.assertEqual(resultado["itens_xml_original"], [])
        self.assertFalse(resultado["permite_emissao"])

    def test_identidades_divergentes_bloqueiam_preparacao(self):
        self._registrar_dfe(
            self._xml().replace("11111111000111", "99999999000199")
        )

        resultado = preparar_devolucao_fornecedor(self.entrada)

        self.assertIn("Fornecedor corresponde ao emitente original", resultado["bloqueios_documentais"])
        self.assertFalse(resultado["permite_emissao"])

    def test_tela_da_entrada_exibe_diagnostico_sem_oferecer_emissao(self):
        self.client.force_login(self.usuario)

        resposta = self.client.get(f"/compras/{self.entrada.pk}/")

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Preparação fiscal para devolução ao fornecedor")
        self.assertContains(resposta, "Preparação documental incompleta")
        self.assertContains(resposta, "Emissão permanece bloqueada")
        self.assertNotContains(resposta, "Emitir devolução")

    def test_salva_e_atualiza_um_unico_rascunho_sem_efeito_fiscal(self):
        self._registrar_dfe()

        rascunho, criado = salvar_rascunho_devolucao_fornecedor(
            self.entrada,
            selecoes={self.item_entrada.pk: "1.250"},
            motivo_operacional="Avaria conferida no recebimento",
            usuario=self.usuario,
        )
        atualizado, criado_novamente = salvar_rascunho_devolucao_fornecedor(
            self.entrada,
            selecoes={self.item_entrada.pk: "0.750"},
            motivo_operacional="Quantidade revisada",
            usuario=self.usuario,
        )

        self.assertTrue(criado)
        self.assertFalse(criado_novamente)
        self.assertEqual(atualizado.pk, rascunho.pk)
        self.assertEqual(atualizado.contrato, CONTRATO_RASCUNHO_DEVOLUCAO_FORNECEDOR)
        self.assertEqual(RascunhoDevolucaoFornecedor.objects.count(), 1)
        item = ItemRascunhoDevolucaoFornecedor.objects.get()
        self.assertEqual(item.quantidade, Decimal("0.750"))
        self.assertEqual(item.quantidade_recebida_snapshot, Decimal("2.000"))
        self.assertFalse(DocumentoFiscal.objects.exists())

    def test_rejeita_quantidade_acima_do_recebido_sem_criar_rascunho(self):
        self._registrar_dfe()

        with self.assertRaisesMessage(ValidationError, "excede o saldo devolvível"):
            salvar_rascunho_devolucao_fornecedor(
                self.entrada,
                selecoes={self.item_entrada.pk: "2.001"},
                motivo_operacional="Teste de limite",
                usuario=self.usuario,
            )

        self.assertFalse(RascunhoDevolucaoFornecedor.objects.exists())
        self.assertFalse(DocumentoFiscal.objects.exists())

    def test_rejeita_quantidade_nao_finita_ou_fora_da_precisao(self):
        self._registrar_dfe()

        for quantidade in ("NaN", "Infinity", "0.0001", "1000000000"):
            with self.subTest(quantidade=quantidade):
                with self.assertRaises(ValidationError):
                    salvar_rascunho_devolucao_fornecedor(
                        self.entrada,
                        selecoes={self.item_entrada.pk: quantidade},
                        motivo_operacional="Teste de número inválido",
                        usuario=self.usuario,
                    )

        self.assertFalse(RascunhoDevolucaoFornecedor.objects.exists())

    def test_cancelamento_libera_preparacao_e_preserva_historico(self):
        self._registrar_dfe()
        rascunho, _ = salvar_rascunho_devolucao_fornecedor(
            self.entrada,
            selecoes={self.item_entrada.pk: "1.000"},
            motivo_operacional="Embalagem danificada",
            usuario=self.usuario,
        )

        cancelar_rascunho_devolucao_fornecedor(self.entrada, usuario=self.usuario)
        novo, criado = salvar_rascunho_devolucao_fornecedor(
            self.entrada,
            selecoes={self.item_entrada.pk: "2.000"},
            motivo_operacional="Nova conferência",
            usuario=self.usuario,
        )

        rascunho.refresh_from_db()
        self.assertEqual(rascunho.status, StatusRascunhoDevolucaoFornecedor.CANCELADO)
        self.assertTrue(criado)
        self.assertNotEqual(novo.pk, rascunho.pk)
        self.assertEqual(RascunhoDevolucaoFornecedor.objects.count(), 2)

    def test_entrada_nao_pode_ser_cancelada_com_preparacao_ativa(self):
        self._registrar_dfe()
        salvar_rascunho_devolucao_fornecedor(
            self.entrada,
            selecoes={self.item_entrada.pk: "1.000"},
            motivo_operacional="Separação iniciada",
            usuario=self.usuario,
        )

        with self.assertRaisesMessage(ValidationError, "Cancele a preparação fiscal"):
            cancelar_entrada_compra(
                self.entrada,
                usuario=self.usuario,
                motivo="Cancelamento incompatível",
            )

        self.entrada.refresh_from_db()
        self.assertEqual(self.entrada.status, StatusEntradaCompra.FINALIZADA)

    def test_tela_salva_e_cancela_rascunho_sem_oferecer_emissao(self):
        self._registrar_dfe()
        self.client.force_login(self.usuario)

        resposta = self.client.post(
            f"/compras/{self.entrada.pk}/devolucao-fornecedor/rascunho/",
            {
                f"quantidade_{self.item_entrada.pk}": "1.500",
                "motivo_operacional": "Produto fora do pedido",
            },
            follow=True,
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Rascunho de devolução criado")
        self.assertContains(resposta, "Cancelar preparação")
        self.assertContains(resposta, 'value="1.500"', html=False)
        self.assertNotContains(resposta, "Emitir devolução")

        cancelado = self.client.post(
            f"/compras/{self.entrada.pk}/devolucao-fornecedor/rascunho/cancelar/",
            follow=True,
        )
        self.assertContains(cancelado, "Preparação fiscal cancelada")
        self.assertEqual(
            RascunhoDevolucaoFornecedor.objects.get().status,
            StatusRascunhoDevolucaoFornecedor.CANCELADO,
        )
