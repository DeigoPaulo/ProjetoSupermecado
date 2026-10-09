from decimal import Decimal
from xml.etree import ElementTree as ET

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.empresas.models import Empresa, Filial
from apps.fiscal.models import (
    AmbienteFiscal, ConfiguracaoFiscal, DocumentoFiscal, NaturezaOperacao,
    ParametrizacaoBeneficioFiscalProduto, SerieFiscal, SituacaoBeneficioFiscalICMS,
    TipoDocumentoFiscal,
)
from apps.fiscal.services import (
    NFE_NS, preparar_documento_pedido_online, validar_vinculos_pagamentos_xml,
)
from apps.fiscal.test_support_identidades_fiscais import obter_identidade_fiscal_teste
from apps.pdv.models import Caixa
from apps.produtos.models import Categoria, Produto
from apps.vendas.models import (
    ConfirmacaoPagamentoIntegrado, FormaPagamento, FormaPagamentoFilial,
    StatusPagamento, TipoDocumentoConsumidor,
)

from .models import (
    CanalPedido, ItemPedidoOnline, OrigemRecebimentoPedido, PagamentoPedido,
    PedidoOnline, StatusPagamentoPedido, TipoEntrega,
)


class FiscalPagamentoPedidoTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_superuser(
            "fiscal_pedido", "fiscal_pedido@example.com", "senha",
        )
        empresa = Empresa.objects.create(
            razao_social="Mercado Fiscal", nome_fantasia="Mercado Fiscal",
            cnpj="12345678000195",
        )
        self.filial = Filial.objects.create(
            empresa=empresa, nome="Matriz", uf="SP", codigo_municipio_ibge="3550308",
            cnpj=obter_identidade_fiscal_teste("FILIAL", finalidade="TESTE_INTEGRACAO_LOCAL"),
        )
        produto = Produto.objects.create(
            codigo_barras="789100000001", nome="Arroz", categoria=Categoria.objects.create(nome="Mercearia"),
            preco_custo=Decimal("10.00"), preco_venda=Decimal("30.00"),
            ncm="10063021", origem_mercadoria="0", cst_icms="00", aliquota_icms=Decimal("18.00"),
            cst_pis="01", aliquota_pis=Decimal("1.6500"), cst_cofins="01",
            aliquota_cofins=Decimal("7.6000"),
        )
        ConfiguracaoFiscal.objects.create(
            filial=self.filial, ambiente=AmbienteFiscal.HOMOLOGACAO,
            regime_tributario="Regime normal", inscricao_estadual="123456789",
            certificado_a1_criptografado=b"certificado", certificado_senha_criptografada=b"senha",
        )
        self.serie = SerieFiscal.objects.create(
            filial=self.filial, tipo_documento=TipoDocumentoFiscal.NFE, serie=55, proximo_numero=200,
        )
        natureza = NaturezaOperacao.objects.create(
            empresa=empresa, descricao="Venda online de mercadorias", cfop="5102",
            tipo_documento=TipoDocumentoFiscal.NFE,
        )
        ParametrizacaoBeneficioFiscalProduto.objects.create(
            produto=produto, natureza_operacao=natureza,
            situacao=SituacaoBeneficioFiscalICMS.SEM_BENEFICIO, atualizado_por=self.usuario,
        )
        self.pedido = PedidoOnline.objects.create(
            filial=self.filial, nome_cliente="Cliente", usuario=self.usuario,
            canal=CanalPedido.PDV, tipo_entrega=TipoEntrega.ENTREGA,
            endereco_entrega="Rua do Consumidor, 100",
            documento_cliente_tipo=TipoDocumentoConsumidor.CNPJ,
            documento_cliente=obter_identidade_fiscal_teste("CLIENTE_PJ", finalidade="TESTE_INTEGRACAO_LOCAL"),
            destinatario_indicador_ie="9", destinatario_logradouro="Rua do Consumidor",
            destinatario_numero="100", destinatario_bairro="Centro",
            destinatario_codigo_municipio_ibge="3550308", destinatario_municipio="São Paulo",
            destinatario_uf="SP", destinatario_cep="01001000",
        )
        ItemPedidoOnline.objects.create(
            pedido=self.pedido, produto=produto, quantidade=Decimal("1"), preco_unitario=Decimal("30.00"),
        )
        self.pedido.recalcular()
        self.caixa = Caixa.objects.create(filial=self.filial, usuario_abertura=self.usuario)
        self.dinheiro = self._forma("Dinheiro", "DINHEIRO")

    def _forma(self, nome, tipo, **configuracao):
        forma = FormaPagamento.objects.create(nome=nome, tipo=tipo, permite_troco=tipo == "DINHEIRO")
        FormaPagamentoFilial.objects.create(filial=self.filial, forma_pagamento=forma, **configuracao)
        return forma

    def _parcela(self, forma, valor, *, informado=None, status=StatusPagamento.CONFIRMADO, **dados):
        parcela = PagamentoPedido(
            pedido=self.pedido, forma_pagamento=forma, valor=Decimal(valor),
            valor_informado=Decimal(informado or valor), status=status,
            origem_recebimento=OrigemRecebimentoPedido.CAIXA_PDV,
            caixa_recebimento=self.caixa, usuario_recebimento=self.usuario, **dados,
        )
        parcela.full_clean()
        parcela.save()
        return parcela

    def _marcar_pago(self):
        self.pedido.status_pagamento = StatusPagamentoPedido.PAGO
        self.pedido.valor_pago = self.pedido.total
        self.pedido.save(update_fields=["status_pagamento", "valor_pago"])

    def _detalhes(self, documento):
        raiz = ET.fromstring(documento.xml_conteudo)
        inf = raiz.find(f"{{{NFE_NS}}}infNFe")
        return inf, inf.findall(f"{{{NFE_NS}}}pag/{{{NFE_NS}}}detPag")

    def test_service_bloqueia_pagamento_posterior_sem_consumir_serie(self):
        with self.assertRaisesMessage(ValidationError, "Pagamento posterior"):
            preparar_documento_pedido_online(self.pedido, self.usuario)
        self.assertEqual(DocumentoFiscal.objects.count(), 0)
        self.serie.refresh_from_db()
        self.assertEqual(self.serie.proximo_numero, 200)

    def test_view_continua_bloqueando_pagamento_posterior(self):
        self.client.force_login(self.usuario)
        resposta = self.client.post(f"/pedidos-online/{self.pedido.pk}/acao/", {"acao": "preparar_nfe"})
        self.assertEqual(resposta.status_code, 302)
        self.assertFalse(DocumentoFiscal.objects.exists())

    def test_pago_sem_parcela_bloqueia(self):
        self._marcar_pago()
        with self.assertRaisesMessage(ValidationError, "ao menos uma parcela"):
            preparar_documento_pedido_online(self.pedido, self.usuario)

    def test_pago_com_soma_insuficiente_bloqueia(self):
        self._parcela(self.dinheiro, "20.00")
        self._marcar_pago()
        with self.assertRaisesMessage(ValidationError, "divergem do total"):
            preparar_documento_pedido_online(self.pedido, self.usuario)

    def test_forma_sem_troco_nao_aceita_valor_informado_maior(self):
        credito = self._forma("Crédito", "CREDITO")
        parcela = self._parcela(
            credito, "30.00", transacao_externa_id="pos-1", nsu="nsu-1",
            codigo_autorizacao="auth-1", tipo_integracao="2",
        )
        parcela.valor_informado = Decimal("40.00")
        parcela.save(update_fields=["valor_informado"])
        self._marcar_pago()
        with self.assertRaisesMessage(ValidationError, "não permite troco"):
            preparar_documento_pedido_online(self.pedido, self.usuario)

    def test_parcelas_recusada_estornada_e_estorno_pendente_nao_contam(self):
        for status in (StatusPagamento.RECUSADO, StatusPagamento.ESTORNADO, StatusPagamento.ESTORNO_PENDENTE):
            with self.subTest(status=status):
                parcela = self._parcela(self.dinheiro, "30.00", status=status)
                self._marcar_pago()
                with self.assertRaisesMessage(ValidationError, "ao menos uma parcela"):
                    preparar_documento_pedido_online(self.pedido, self.usuario)
                parcela.delete()

    def test_dinheiro_uma_parcela_e_troco(self):
        self._parcela(self.dinheiro, "30.00", informado="50.00")
        self._marcar_pago()
        documento = preparar_documento_pedido_online(self.pedido, self.usuario)
        inf, detalhes = self._detalhes(documento)
        self.assertEqual(len(detalhes), 1)
        self.assertEqual(detalhes[0].findtext(f"{{{NFE_NS}}}tPag"), "01")
        self.assertEqual(detalhes[0].findtext(f"{{{NFE_NS}}}vPag"), "50.00")
        self.assertEqual(inf.findtext(f"{{{NFE_NS}}}pag/{{{NFE_NS}}}vTroco"), "20.00")
        validar_vinculos_pagamentos_xml(documento, inf)

    def test_dividido_preserva_ordem_forma_e_valor(self):
        credito = self._forma("Crédito", "CREDITO")
        item = self.pedido.itens.get()
        item.preco_unitario = Decimal("100.00")
        item.save()
        self.pedido.recalcular()
        self._parcela(self.dinheiro, "40.00")
        self._parcela(
            credito, "60.00", transacao_externa_id="pos-1", nsu="nsu-1",
            codigo_autorizacao="aut-1", tipo_integracao="2",
        )
        self._marcar_pago()
        documento = preparar_documento_pedido_online(self.pedido, self.usuario)
        inf, detalhes = self._detalhes(documento)
        self.assertEqual(len(detalhes), 2)
        self.assertEqual(
            [(det.findtext(f"{{{NFE_NS}}}tPag"), det.findtext(f"{{{NFE_NS}}}vPag")) for det in detalhes],
            [("01", "40.00"), ("03", "60.00")],
        )
        card = detalhes[1].find(f"{{{NFE_NS}}}card")
        self.assertEqual(card.findtext(f"{{{NFE_NS}}}tpIntegra"), "2")
        self.assertIsNone(card.find(f"{{{NFE_NS}}}cAut"))
        validar_vinculos_pagamentos_xml(documento, inf)

    def test_tpag_e_xpag_usam_configuracao_da_filial(self):
        configuracao = FormaPagamentoFilial.objects.get(
            filial=self.filial, forma_pagamento=self.dinheiro,
        )
        configuracao.codigo_fiscal_tpag = "99"
        configuracao.descricao_fiscal_xpag = "Pagamento especial"
        configuracao.full_clean()
        configuracao.save()
        self._parcela(self.dinheiro, "30.00")
        self._marcar_pago()
        documento = preparar_documento_pedido_online(self.pedido, self.usuario)
        _, detalhes = self._detalhes(documento)
        self.assertEqual(detalhes[0].findtext(f"{{{NFE_NS}}}tPag"), "99")
        self.assertEqual(detalhes[0].findtext(f"{{{NFE_NS}}}xPag"), "Pagamento especial")

    def test_integrado_exige_confirmacao_servidor_e_detecta_adulteracao(self):
        credito = self._forma("Crédito", "CREDITO")
        instituicao = obter_identidade_fiscal_teste("FILIAL", finalidade="TESTE_INTEGRACAO_LOCAL")
        dados = {
            "status": StatusPagamento.CONFIRMADO,
            "transacao_externa_id": "provedor-1", "nsu": "nsu-1",
            "codigo_autorizacao": "aut-1", "tipo_integracao": "1",
            "cnpj_instituicao_pagamento": instituicao, "bandeira_cartao": "01",
            "cnpj_beneficiario_pagamento": "", "identificador_terminal_pagamento": "",
        }
        confirmacao = ConfirmacaoPagamentoIntegrado.objects.create(
            caixa=self.caixa, forma_pagamento=credito, tipo_forma="CREDITO",
            valor=Decimal("30.00"), provedor="teste-local",
            transacao_externa_id="provedor-1", dados=dados,
        )
        parcela = self._parcela(
            credito, "30.00", confirmacao_integracao=confirmacao,
            **{campo: dados[campo] for campo in dados if campo != "status"},
        )
        self._marcar_pago()
        documento = preparar_documento_pedido_online(self.pedido, self.usuario)
        inf, detalhes = self._detalhes(documento)
        card = detalhes[0].find(f"{{{NFE_NS}}}card")
        self.assertEqual(card.findtext(f"{{{NFE_NS}}}tpIntegra"), "1")
        self.assertEqual(card.findtext(f"{{{NFE_NS}}}cAut"), "aut-1")
        validar_vinculos_pagamentos_xml(documento, inf)
        parcela.nsu = "adulterado"
        parcela.save(update_fields=["nsu"])
        with self.assertRaisesMessage(ValidationError, "divergem"):
            validar_vinculos_pagamentos_xml(documento, inf)

    def test_integrado_sem_confirmacao_confiavel_bloqueia(self):
        credito = self._forma("Crédito", "CREDITO")
        self._parcela(
            credito, "30.00", transacao_externa_id="manual", nsu="nsu-manual",
            codigo_autorizacao="auth-manual", tipo_integracao="1",
        )
        self._marcar_pago()
        with self.assertRaisesMessage(ValidationError, "confirmação confiável"):
            preparar_documento_pedido_online(self.pedido, self.usuario)

    def test_adulteracao_do_xml_ou_da_parcela_bloqueia_paridade(self):
        parcela = self._parcela(self.dinheiro, "30.00")
        self._marcar_pago()
        documento = preparar_documento_pedido_online(self.pedido, self.usuario)
        inf, detalhes = self._detalhes(documento)
        detalhes[0].find(f"{{{NFE_NS}}}vPag").text = "29.00"
        with self.assertRaisesMessage(ValidationError, "divergem"):
            validar_vinculos_pagamentos_xml(documento, inf)
        parcela.valor_informado = Decimal("31.00")
        parcela.save(update_fields=["valor_informado"])
        inf, _ = self._detalhes(documento)
        with self.assertRaisesMessage(ValidationError, "divergem"):
            validar_vinculos_pagamentos_xml(documento, inf)

    def test_pagamento_de_outro_pedido_nao_serve(self):
        outro = PedidoOnline.objects.create(filial=self.filial, usuario=self.usuario, nome_cliente="Outro")
        parcela = self._parcela(self.dinheiro, "30.00")
        parcela.pedido = outro
        parcela.save(update_fields=["pedido"])
        self._marcar_pago()
        with self.assertRaisesMessage(ValidationError, "ao menos uma parcela"):
            preparar_documento_pedido_online(self.pedido, self.usuario)

    def test_caixa_de_outra_filial_bloqueia(self):
        outra = Filial.objects.create(empresa=self.filial.empresa, nome="Outra")
        caixa = Caixa.objects.create(filial=outra, usuario_abertura=self.usuario)
        parcela = self._parcela(self.dinheiro, "30.00")
        parcela.caixa_recebimento = caixa
        parcela.save(update_fields=["caixa_recebimento"])
        self._marcar_pago()
        with self.assertRaisesMessage(ValidationError, "outra filial"):
            preparar_documento_pedido_online(self.pedido, self.usuario)

    def test_externo_legado_preserva_xml_atual(self):
        self.pedido.canal = CanalPedido.LOJA_ONLINE
        self.pedido.forma_pagamento = "DINHEIRO"
        self.pedido.status_pagamento = StatusPagamentoPedido.PAGO
        self.pedido.valor_pago = self.pedido.total
        self.pedido.save(update_fields=["canal", "forma_pagamento", "status_pagamento", "valor_pago"])
        documento = preparar_documento_pedido_online(self.pedido, self.usuario)
        _, detalhes = self._detalhes(documento)
        self.assertEqual(len(detalhes), 1)
        self.assertEqual(detalhes[0].findtext(f"{{{NFE_NS}}}vPag"), "30.00")
