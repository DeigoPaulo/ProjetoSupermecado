from datetime import date
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
    registrar_parecer_tributario_devolucao_fornecedor,
    revisar_rascunho_devolucao_fornecedor,
    salvar_rascunho_devolucao_fornecedor,
    submeter_rascunho_devolucao_para_revisao,
)
from .models import (
    DocumentoDFeRecebido,
    DocumentoFiscal,
    CatalogoCFOP,
    DecisaoRevisaoDevolucaoFornecedor,
    ItemRascunhoDevolucaoFornecedor,
    ItemCFOP,
    ParecerTributarioDevolucaoFornecedor,
    RascunhoDevolucaoFornecedor,
    RevisaoDevolucaoFornecedor,
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
        self.revisor = get_user_model().objects.create_user("contador_devolucao")
        PerfilUsuario.objects.create(
            usuario=self.revisor,
            filial=self.filial,
            tipo=TipoPerfil.CONTABILIDADE,
        )
        self.financeiro = get_user_model().objects.create_user("financeiro_devolucao")
        PerfilUsuario.objects.create(
            usuario=self.financeiro,
            filial=self.filial,
            tipo=TipoPerfil.FINANCEIRO,
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
          <det nItem="1"><prod><cProd>7891111111111</cProd><xProd>Produto recebido</xProd><NCM>10063021</NCM><CFOP>5102</CFOP><uCom>UN</uCom><qCom>2.0000</qCom><vUnCom>10.00</vUnCom><vProd>20.00</vProd></prod>
          <imposto><ICMS><ICMS00><orig>0</orig><CST>00</CST><vBC>20.00</vBC><pICMS>17.00</pICMS><vICMS>3.40</vICMS></ICMS00></ICMS></imposto></det>
          </infNFe></NFe><protNFe><infProt><chNFe>{self.CHAVE}</chNFe><cStat>100</cStat></infProt></protNFe>
        </nfeProc>"""

    def _rascunho_submetido(self):
        self._registrar_dfe()
        rascunho, _ = salvar_rascunho_devolucao_fornecedor(
            self.entrada,
            selecoes={self.item_entrada.pk: "1.000"},
            motivo_operacional="Mercadoria avariada na conferência",
            usuario=self.usuario,
        )
        return submeter_rascunho_devolucao_para_revisao(
            self.entrada,
            usuario=self.usuario,
        )

    def _rascunho_aprovado(self):
        rascunho = self._rascunho_submetido()
        _, aprovado = revisar_rascunho_devolucao_fornecedor(
            rascunho,
            decisao=DecisaoRevisaoDevolucaoFornecedor.APROVAR,
            justificativa="Preparação documental aprovada para receber parecer tributário.",
            revisor=self.revisor,
        )
        return aprovado

    def _registrar_catalogo_cfop(self):
        catalogo = CatalogoCFOP.objects.create(
            versao="teste-devolucao-2026",
            referencia_em=date(2026, 1, 1),
            ato="Convênio s/nº de 1970",
            fonte_nome="Portal Nacional da NF-e",
            fonte_url="https://www.confaz.fazenda.gov.br/legislacao/convenios/s-n-de-1970",
            fonte_sha256="a" * 64,
            ativo=True,
            quantidade_itens=2,
        )
        ItemCFOP.objects.create(
            catalogo=catalogo,
            codigo="5202",
            codigo_formatado="5.202",
            titulo="Devolução de compra para comercialização",
            nota_explicativa="Item de teste do catálogo oficial versionado.",
            direcao=ItemCFOP.Direcao.SAIDA,
            alcance=ItemCFOP.Alcance.INTERNA,
        )
        ItemCFOP.objects.create(
            catalogo=catalogo,
            codigo="1202",
            codigo_formatado="1.202",
            titulo="Devolução de venda de mercadoria adquirida de terceiros",
            nota_explicativa="Item de entrada usado para validar a direção.",
            direcao=ItemCFOP.Direcao.ENTRADA,
            alcance=ItemCFOP.Alcance.INTERNA,
        )
        return catalogo

    def _dados_parecer(self, **alteracoes):
        dados = {
            "vigencia_referencia": "2026-09-09",
            "regime_tributario_referencia": "Regime informado pelo contador para o caso",
            "natureza_operacao": "Devolução de compra para comercialização",
            "cfop": "5202",
            "tratamento_icms": "Aplicar conforme memória de cálculo validada pelo contador.",
            "tratamento_icms_st_fcp": "Não aplicável neste caso conforme orientação registrada.",
            "tratamento_ipi": "Não aplicável neste caso conforme orientação registrada.",
            "tratamento_pis": "Aplicar conforme orientação profissional anexada ao caso.",
            "tratamento_cofins": "Aplicar conforme orientação profissional anexada ao caso.",
            "tratamento_cbenef": "Não aplicável neste caso conforme orientação registrada.",
            "tratamento_ibs_cbs": "Tratar conforme regra vigente na data de referência informada.",
            "fundamentacao": "Orientação formal do responsável contábil para este caso concreto.",
        }
        dados.update(alteracoes)
        return dados

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
        self.assertEqual(item.numero_item_xml, "1")
        self.assertEqual(item.item_xml_snapshot["codigo_produto"], "7891111111111")
        self.assertEqual(item.item_xml_snapshot["valor_icms"], "3.40")
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

    def test_submissao_congela_mapeamento_e_hash_sem_emitir(self):
        self._registrar_dfe()
        rascunho, _ = salvar_rascunho_devolucao_fornecedor(
            self.entrada,
            selecoes={self.item_entrada.pk: "1.000"},
            motivo_operacional="Produto divergente",
            usuario=self.usuario,
        )

        submetido = submeter_rascunho_devolucao_para_revisao(
            self.entrada,
            usuario=self.usuario,
        )

        self.assertEqual(submetido.pk, rascunho.pk)
        self.assertEqual(
            submetido.status,
            StatusRascunhoDevolucaoFornecedor.AGUARDANDO_REVISAO,
        )
        self.assertEqual(submetido.submetido_por, self.usuario)
        self.assertIsNotNone(submetido.submetido_em)
        self.assertEqual(len(submetido.xml_origem_sha256), 64)
        self.assertFalse(DocumentoFiscal.objects.exists())
        with self.assertRaisesMessage(ValidationError, "não pode ser alterado"):
            salvar_rascunho_devolucao_fornecedor(
                self.entrada,
                selecoes={self.item_entrada.pk: "0.500"},
                motivo_operacional="Tentativa posterior",
                usuario=self.usuario,
            )

    def test_submissao_rejeita_snapshot_xml_adulterado(self):
        self._registrar_dfe()
        salvar_rascunho_devolucao_fornecedor(
            self.entrada,
            selecoes={self.item_entrada.pk: "1.000"},
            motivo_operacional="Teste de integridade",
            usuario=self.usuario,
        )
        item = ItemRascunhoDevolucaoFornecedor.objects.get()
        item.item_xml_snapshot = {**item.item_xml_snapshot, "valor_icms": "99.99"}
        item.save(update_fields=["item_xml_snapshot"])

        with self.assertRaisesMessage(ValidationError, "não está íntegro"):
            submeter_rascunho_devolucao_para_revisao(
                self.entrada,
                usuario=self.usuario,
            )

        self.assertEqual(
            RascunhoDevolucaoFornecedor.objects.get().status,
            StatusRascunhoDevolucaoFornecedor.RASCUNHO,
        )

    def test_submissao_rejeita_soma_de_lotes_acima_do_nitem_original(self):
        segundo_item = ItemEntradaCompra.objects.create(
            entrada=self.entrada,
            produto=self.item_entrada.produto,
            quantidade=Decimal("1.000"),
            custo_unitario=Decimal("10.00"),
            total=Decimal("10.00"),
            codigo_lote="LOTE-2",
        )
        self._registrar_dfe()
        salvar_rascunho_devolucao_fornecedor(
            self.entrada,
            selecoes={self.item_entrada.pk: "2.000", segundo_item.pk: "1.000"},
            motivo_operacional="Dois lotes do mesmo item fiscal",
            usuario=self.usuario,
        )

        with self.assertRaisesMessage(ValidationError, "soma selecionada"):
            submeter_rascunho_devolucao_para_revisao(
                self.entrada,
                usuario=self.usuario,
            )

        self.assertFalse(DocumentoFiscal.objects.exists())

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
        self.assertContains(resposta, "nItem 1")
        self.assertContains(resposta, 'value="1.500"', html=False)
        self.assertNotContains(resposta, "Emitir devolução")

        submetido = self.client.post(
            f"/compras/{self.entrada.pk}/devolucao-fornecedor/rascunho/submeter/",
            follow=True,
        )
        self.assertContains(submetido, "Rascunho submetido à revisão fiscal")
        self.assertContains(submetido, "Integridade do XML original")
        self.assertNotContains(submetido, "Emitir devolução")

        cancelado = self.client.post(
            f"/compras/{self.entrada.pk}/devolucao-fornecedor/rascunho/cancelar/",
            follow=True,
        )
        self.assertContains(cancelado, "Preparação fiscal cancelada")
        self.assertEqual(
            RascunhoDevolucaoFornecedor.objects.get().status,
            StatusRascunhoDevolucaoFornecedor.CANCELADO,
        )

    def test_revisor_aprova_preparacao_sem_efeito_fiscal_e_historico_e_imutavel(self):
        rascunho = self._rascunho_submetido()

        revisao, aprovado = revisar_rascunho_devolucao_fornecedor(
            rascunho,
            decisao=DecisaoRevisaoDevolucaoFornecedor.APROVAR,
            justificativa="Documentos e quantidades conferidos para a próxima etapa.",
            revisor=self.revisor,
        )

        self.assertEqual(aprovado.status, StatusRascunhoDevolucaoFornecedor.APROVADO)
        self.assertEqual(revisao.sequencia, 1)
        self.assertEqual(len(revisao.conteudo_sha256), 64)
        self.assertEqual(revisao.revisor, self.revisor)
        self.assertEqual(revisao.conteudo_snapshot["itens"][0]["quantidade"], "1.000")
        self.assertFalse(DocumentoFiscal.objects.exists())
        with self.assertRaisesMessage(ValueError, "imutáveis"):
            revisao.justificativa = "Tentativa de alteração"
            revisao.save()
        with self.assertRaisesMessage(ValueError, "imutáveis"):
            RevisaoDevolucaoFornecedor.objects.filter(pk=revisao.pk).update(
                justificativa="Tentativa"
            )
        with self.assertRaisesMessage(ValidationError, "não pode ser cancelada"):
            cancelar_rascunho_devolucao_fornecedor(
                self.entrada,
                usuario=self.usuario,
            )

    def test_revisor_devolve_para_correcao_e_preserva_historico(self):
        rascunho = self._rascunho_submetido()

        revisao, devolvido = revisar_rascunho_devolucao_fornecedor(
            rascunho,
            decisao=DecisaoRevisaoDevolucaoFornecedor.DEVOLVER_CORRECAO,
            justificativa="Corrigir a quantidade informada antes de nova submissão.",
            revisor=self.revisor,
        )

        self.assertEqual(devolvido.status, StatusRascunhoDevolucaoFornecedor.RASCUNHO)
        self.assertEqual(devolvido.xml_origem_sha256, "")
        self.assertIsNone(devolvido.submetido_em)
        self.assertIsNone(devolvido.submetido_por)
        self.assertTrue(RevisaoDevolucaoFornecedor.objects.filter(pk=revisao.pk).exists())
        corrigido, criado = salvar_rascunho_devolucao_fornecedor(
            self.entrada,
            selecoes={self.item_entrada.pk: "0.500"},
            motivo_operacional="Quantidade corrigida após revisão fiscal",
            usuario=self.usuario,
        )
        self.assertFalse(criado)
        self.assertEqual(corrigido.pk, rascunho.pk)
        self.assertEqual(corrigido.itens.get().quantidade, Decimal("0.500"))
        revisao.refresh_from_db()
        self.assertEqual(revisao.conteudo_snapshot["itens"][0]["quantidade"], "1.000")
        self.assertFalse(DocumentoFiscal.objects.exists())

    def test_revisao_bloqueia_xml_alterado_depois_da_submissao(self):
        rascunho = self._rascunho_submetido()
        dfe = DocumentoDFeRecebido.objects.get(entrada_compra=self.entrada)
        dfe.xml_conteudo = dfe.xml_conteudo.replace("3.40", "3.41")
        dfe.save(update_fields=["xml_conteudo"])

        with self.assertRaisesMessage(ValidationError, "XML original divergiu"):
            revisar_rascunho_devolucao_fornecedor(
                rascunho,
                decisao=DecisaoRevisaoDevolucaoFornecedor.APROVAR,
                justificativa="Tentativa com documento original modificado.",
                revisor=self.revisor,
            )

        self.assertFalse(RevisaoDevolucaoFornecedor.objects.exists())
        rascunho.refresh_from_db()
        self.assertEqual(
            rascunho.status,
            StatusRascunhoDevolucaoFornecedor.AGUARDANDO_REVISAO,
        )

    def test_fila_de_revisao_exclui_compras_e_financeiro(self):
        rascunho = self._rascunho_submetido()

        for usuario in (self.usuario, self.financeiro):
            with self.subTest(usuario=usuario.username):
                self.client.force_login(usuario)
                self.assertEqual(
                    self.client.get("/fiscal/devolucoes-fornecedor/revisao/").status_code,
                    403,
                )
                self.assertEqual(
                    self.client.get(
                        f"/fiscal/devolucoes-fornecedor/revisao/{rascunho.pk}/"
                    ).status_code,
                    403,
                )

    def test_contabilidade_revisa_pela_tela_e_aprovacao_some_das_acoes_de_compras(self):
        rascunho = self._rascunho_submetido()
        self.client.force_login(self.revisor)

        fila = self.client.get("/fiscal/devolucoes-fornecedor/revisao/")
        detalhe = self.client.get(
            f"/fiscal/devolucoes-fornecedor/revisao/{rascunho.pk}/"
        )
        resposta = self.client.post(
            f"/fiscal/devolucoes-fornecedor/revisao/{rascunho.pk}/decidir/",
            {
                "decisao": DecisaoRevisaoDevolucaoFornecedor.APROVAR,
                "justificativa": "Preparação documental conferida pelo responsável fiscal.",
            },
            follow=True,
        )

        self.assertEqual(fila.status_code, 200)
        self.assertContains(fila, "Aprovar não significa emitir")
        self.assertEqual(detalhe.status_code, 200)
        self.assertContains(detalhe, "Aprovar somente a preparação")
        self.assertContains(resposta, "continua sem autorização para emitir")
        self.assertFalse(DocumentoFiscal.objects.exists())

        self.client.force_login(self.usuario)
        compra = self.client.get(f"/compras/{self.entrada.pk}/")
        self.assertContains(compra, "Preparação aprovada pela revisão fiscal")
        self.assertNotContains(compra, "Salvar rascunho sem emitir")
        self.assertNotContains(compra, "Enviar para revisão fiscal")
        self.assertNotContains(compra, "Cancelar preparação")

    def test_revisor_nao_enxerga_rascunho_de_outra_empresa(self):
        rascunho = self._rascunho_submetido()
        outra_empresa = Empresa.objects.create(
            razao_social="Outro Mercado Ltda",
            nome_fantasia="Outro Mercado",
            cnpj="33.333.333/0001-33",
        )
        outra_filial = Filial.objects.create(
            empresa=outra_empresa,
            nome="Outra Matriz",
            cnpj=outra_empresa.cnpj,
            uf="GO",
        )
        outro_revisor = get_user_model().objects.create_user("outro_contador")
        PerfilUsuario.objects.create(
            usuario=outro_revisor,
            filial=outra_filial,
            tipo=TipoPerfil.CONTABILIDADE,
        )
        self.client.force_login(outro_revisor)

        fila = self.client.get("/fiscal/devolucoes-fornecedor/revisao/")
        detalhe = self.client.get(
            f"/fiscal/devolucoes-fornecedor/revisao/{rascunho.pk}/"
        )

        self.assertNotContains(fila, self.CHAVE)
        self.assertEqual(detalhe.status_code, 404)

    def test_parecer_tributario_versionado_e_imutavel_nao_emite(self):
        rascunho = self._rascunho_aprovado()
        self._registrar_catalogo_cfop()

        parecer, criado = registrar_parecer_tributario_devolucao_fornecedor(
            rascunho,
            dados=self._dados_parecer(),
            responsavel=self.revisor,
        )

        self.assertTrue(criado)
        self.assertEqual(parecer.versao, 1)
        self.assertEqual(parecer.cfop, "5202")
        self.assertEqual(parecer.vigencia_referencia, date(2026, 9, 9))
        self.assertEqual(parecer.conteudo_snapshot["cfop"], "5202")
        self.assertEqual(parecer.conteudo_snapshot["catalogo_cfop_sha256"], "a" * 64)
        self.assertEqual(len(parecer.conteudo_sha256), 64)
        self.assertFalse(DocumentoFiscal.objects.exists())
        with self.assertRaisesMessage(ValueError, "imutáveis"):
            parecer.cfop = "6202"
            parecer.save()
        with self.assertRaisesMessage(ValueError, "imutáveis"):
            ParecerTributarioDevolucaoFornecedor.objects.filter(pk=parecer.pk).delete()

    def test_parecer_identico_e_idempotente_e_mudanca_cria_nova_versao(self):
        rascunho = self._rascunho_aprovado()
        self._registrar_catalogo_cfop()

        primeiro, criado = registrar_parecer_tributario_devolucao_fornecedor(
            rascunho,
            dados=self._dados_parecer(),
            responsavel=self.revisor,
        )
        repetido, criado_repetido = registrar_parecer_tributario_devolucao_fornecedor(
            rascunho,
            dados=self._dados_parecer(),
            responsavel=self.revisor,
        )
        segundo, criado_segundo = registrar_parecer_tributario_devolucao_fornecedor(
            rascunho,
            dados=self._dados_parecer(
                fundamentacao="Orientação profissional revisada e formalizada para este caso."
            ),
            responsavel=self.revisor,
        )

        self.assertTrue(criado)
        self.assertFalse(criado_repetido)
        self.assertEqual(repetido.pk, primeiro.pk)
        self.assertTrue(criado_segundo)
        self.assertEqual(segundo.versao, 2)
        self.assertEqual(ParecerTributarioDevolucaoFornecedor.objects.count(), 2)
        self.assertFalse(DocumentoFiscal.objects.exists())

    def test_parecer_exige_aprovacao_catalogo_e_cfop_de_saida(self):
        rascunho = self._rascunho_submetido()
        self._registrar_catalogo_cfop()

        with self.assertRaisesMessage(ValidationError, "previamente aprovada"):
            registrar_parecer_tributario_devolucao_fornecedor(
                rascunho,
                dados=self._dados_parecer(),
                responsavel=self.revisor,
            )

        revisar_rascunho_devolucao_fornecedor(
            rascunho,
            decisao=DecisaoRevisaoDevolucaoFornecedor.APROVAR,
            justificativa="Preparação aprovada para testar o controle do CFOP.",
            revisor=self.revisor,
        )
        with self.assertRaisesMessage(ValidationError, "não de saída"):
            registrar_parecer_tributario_devolucao_fornecedor(
                rascunho,
                dados=self._dados_parecer(cfop="1202"),
                responsavel=self.revisor,
            )
        self.assertFalse(ParecerTributarioDevolucaoFornecedor.objects.exists())

    def test_parecer_bloqueia_quando_nao_ha_catalogo_oficial_vigente(self):
        rascunho = self._rascunho_aprovado()

        with self.assertRaisesMessage(ValidationError, "catálogo CFOP oficial"):
            registrar_parecer_tributario_devolucao_fornecedor(
                rascunho,
                dados=self._dados_parecer(),
                responsavel=self.revisor,
            )

        self.assertFalse(ParecerTributarioDevolucaoFornecedor.objects.exists())

    def test_contabilidade_registra_parecer_pela_tela_e_financeiro_nao_acessa(self):
        rascunho = self._rascunho_aprovado()
        self._registrar_catalogo_cfop()
        url = f"/fiscal/devolucoes-fornecedor/revisao/{rascunho.pk}/parecer/"

        self.client.force_login(self.financeiro)
        self.assertEqual(self.client.post(url, self._dados_parecer()).status_code, 403)

        self.client.force_login(self.revisor)
        detalhe = self.client.get(
            f"/fiscal/devolucoes-fornecedor/revisao/{rascunho.pk}/"
        )
        resposta = self.client.post(url, self._dados_parecer(), follow=True)

        self.assertContains(detalhe, "Registrar nova versão do parecer")
        self.assertContains(detalhe, "Não há preenchimento automático")
        self.assertContains(resposta, "Parecer tributário versão 1 registrado sem liberar emissão")
        self.assertContains(resposta, "CFOP 5202")
        self.assertFalse(DocumentoFiscal.objects.exists())
