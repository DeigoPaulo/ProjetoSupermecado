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
    CONTRATO_MEMORIA_CALCULO_DEVOLUCAO_FORNECEDOR,
    CONTRATO_REVISAO_MEMORIA_CALCULO_DEVOLUCAO_FORNECEDOR,
    CONTRATO_PREPARACAO_DEVOLUCAO_FORNECEDOR,
    CONTRATO_RASCUNHO_DEVOLUCAO_FORNECEDOR,
    TRIBUTOS_MEMORIA_CALCULO,
    cancelar_rascunho_devolucao_fornecedor,
    preparar_devolucao_fornecedor,
    registrar_memoria_calculo_devolucao_fornecedor,
    registrar_parametrizacao_itens_devolucao_fornecedor,
    registrar_parecer_tributario_devolucao_fornecedor,
    revisar_memoria_calculo_devolucao_fornecedor,
    revisar_rascunho_devolucao_fornecedor,
    salvar_rascunho_devolucao_fornecedor,
    submeter_rascunho_devolucao_para_revisao,
)
from .models import (
    TransporteDevolucaoFornecedor,
    DocumentoDFeRecebido,
    DocumentoFiscal,
    CatalogoCFOP,
    DecisaoRevisaoDevolucaoFornecedor,
    DecisaoRevisaoMemoriaCalculoFornecedor,
    ItemRascunhoDevolucaoFornecedor,
    ItemCFOP,
    ItemMemoriaCalculoDevolucaoFornecedor,
    ItemParametrizacaoFiscalDevolucaoFornecedor,
    MemoriaCalculoDevolucaoFornecedor,
    ParecerTributarioDevolucaoFornecedor,
    ParametrizacaoFiscalDevolucaoFornecedor,
    RascunhoDevolucaoFornecedor,
    RevisaoDevolucaoFornecedor,
    RevisaoMemoriaCalculoDevolucaoFornecedor,
    StatusRascunhoDevolucaoFornecedor,
)


from .transporte_devolucao import TransporteDevolucaoForm, registrar_transporte
from .composicao_devolucao import ComposicaoDevolucaoForm, registrar_composicao
from .composicao_devolucao import RevisaoComposicaoForm, revisar_composicao
from .rateio_devolucao import registrar_rateio
from .reflexos_devolucao import registrar_reflexos
from .reflexos_devolucao import revisar_reflexos, validar_reflexos_atuais, RevisaoReflexosForm


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
        self.segundo_revisor = get_user_model().objects.create_user("contador_revisor_devolucao")
        PerfilUsuario.objects.create(
            usuario=self.segundo_revisor,
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

    def _parecer_registrado(self):
        rascunho = self._rascunho_aprovado()
        self._registrar_catalogo_cfop()
        parecer, _ = registrar_parecer_tributario_devolucao_fornecedor(
            rascunho,
            dados=self._dados_parecer(),
            responsavel=self.revisor,
        )
        return rascunho, parecer

    def _dados_parametros(self, rascunho, **alteracoes):
        item = rascunho.itens.get()
        dados = {
            f"tipo_codigo_icms_{item.pk}": "CST",
            f"origem_icms_{item.pk}": "0",
            f"codigo_icms_{item.pk}": "00",
            f"codigo_ipi_{item.pk}": "NA",
            f"codigo_pis_{item.pk}": "01",
            f"codigo_cofins_{item.pk}": "01",
            f"codigo_cbenef_{item.pk}": "NA",
            f"tratamento_icms_st_fcp_{item.pk}": "Não aplicável segundo o parecer selecionado.",
            f"tratamento_cbenef_{item.pk}": "Não aplicável segundo o parecer selecionado.",
            f"tratamento_ibs_cbs_{item.pk}": "Aplicar a orientação textual do parecer selecionado.",
            f"observacao_{item.pk}": "Classificação informada para teste sem cálculo.",
        }
        dados.update(alteracoes)
        return dados

    def _parametrizacao_registrada(self):
        rascunho, parecer = self._parecer_registrado()
        parametros, _ = registrar_parametrizacao_itens_devolucao_fornecedor(
            rascunho,
            parecer_id=parecer.pk,
            dados=self._dados_parametros(rascunho),
            responsavel=self.revisor,
        )
        return rascunho, parametros

    def _dados_memoria(self, parametrizacao, **alteracoes):
        item = parametrizacao.itens.get()
        dados = {
            "criterio_arredondamento": "Valores expressamente informados com fechamento por item em centavos.",
            f"valor_operacao_{item.pk}": "10,00",
            "total_valor_operacao": "10,00",
        }
        valores = {
            "icms": ("10,00", "17,0000", "1,70"),
            "pis": ("10,00", "1,6500", "0,17"),
            "cofins": ("10,00", "7,6000", "0,76"),
        }
        for chave, _rotulo in TRIBUTOS_MEMORIA_CALCULO:
            base, aliquota, valor = valores.get(chave, ("0,00", "0,0000", "0,00"))
            dados[f"base_{chave}_{item.pk}"] = base
            dados[f"aliquota_{chave}_{item.pk}"] = aliquota
            dados[f"valor_{chave}_{item.pk}"] = valor
            dados[f"total_base_{chave}"] = base
            dados[f"total_valor_{chave}"] = valor
        dados[f"observacao_memoria_{item.pk}"] = "Memória informada somente para conferência estrutural."
        dados.update(alteracoes)
        return dados

    def _memoria_registrada(self):
        rascunho, parametrizacao = self._parametrizacao_registrada()
        memoria, _ = registrar_memoria_calculo_devolucao_fornecedor(
            rascunho,
            parametrizacao_id=parametrizacao.pk,
            dados=self._dados_memoria(parametrizacao),
            responsavel=self.revisor,
        )
        return rascunho, parametrizacao, memoria

    def _dados_transporte(self):
        return {"modalidade": "9", "quantidade_volumes": "0", "peso_liquido": "0", "peso_bruto": "0"}

    def _dados_composicao(self):
        return {"valor_base": "10,00", "frete": "2,00", "seguro": "1,00", "despesas": "0,50", "desconto": "0,50", "total": "13,00", "criterio": "Componentes conferidos para a devolução.", "confirmar_componentes": "on"}

    def _composicao_registrada(self):
        rascunho, _, memoria = self._memoria_registrada()
        revisar_memoria_calculo_devolucao_fornecedor(rascunho, memoria_id=memoria.pk, decisao="APROVAR", justificativa="Conferência independente concluída.", revisor=self.segundo_revisor)
        ficha, _ = registrar_composicao(rascunho, dados=self._dados_composicao(), responsavel=self.revisor)
        return rascunho, ficha

    def _dados_revisao_composicao(self):
        return {"decisao": "APROVAR", "justificativa": "Composição conferida pelo responsável contábil.", **{campo: "Orientação explícita de teste para os componentes informados." for campo in ("reflexos_icms", "reflexos_ipi", "reflexos_pis_cofins", "reflexos_ibs_cbs", "fundamentacao")}}

    def test_revisao_composicao_exige_orientacao_na_aprovacao(self):
        self.assertTrue(RevisaoComposicaoForm(self._dados_revisao_composicao()).is_valid())
        for campo in ("reflexos_icms", "reflexos_ipi", "reflexos_pis_cofins", "reflexos_ibs_cbs", "fundamentacao"):
            with self.subTest(campo=campo):
                self.assertFalse(RevisaoComposicaoForm({**self._dados_revisao_composicao(), campo: ""}).is_valid())
        self.assertTrue(RevisaoComposicaoForm({"decisao": "DEVOLVER_CORRECAO", "justificativa": "Corrigir a composição apresentada."}).is_valid())

    def test_rateio_aprovacao_idempotencia_imutabilidade_e_tela(self):
        rascunho, ficha = self._composicao_registrada()
        item = ficha.memoria.itens.get()
        dados = {"criterio": "Componentes informados para o item.", **{f"{campo}_{item.pk}": self._dados_composicao()[campo] for campo in ("frete", "seguro", "despesas", "desconto")}}
        with self.assertRaisesMessage(ValidationError, "precisam estar aprovadas"):
            registrar_rateio(rascunho, composicao_id=ficha.pk, dados=dados, responsavel=self.revisor)
        revisar_composicao(rascunho, composicao_id=ficha.pk, dados=self._dados_revisao_composicao(), revisor=self.segundo_revisor)
        rateio, criado = registrar_rateio(rascunho, composicao_id=ficha.pk, dados=dados, responsavel=self.revisor)
        self.assertTrue(criado)
        self.assertEqual(rateio.conteudo_snapshot["itens"][0]["total"], "13.00")
        self.assertFalse(rateio.conteudo_snapshot["permite_emissao"])
        repetido, criado = registrar_rateio(rascunho, composicao_id=ficha.pk, dados=dados, responsavel=self.revisor)
        self.assertFalse(criado)
        self.assertEqual(rateio.pk, repetido.pk)
        with self.assertRaises(ValueError):
            rateio.save()
        with self.assertRaises(ValueError):
            rateio.delete()
        novo, _ = registrar_rateio(rascunho, composicao_id=ficha.pk, dados={**dados, "criterio": "Novo detalhamento do critério informado."}, responsavel=self.revisor)
        self.assertEqual(novo.versao, 2)
        url = f"/fiscal/devolucoes-fornecedor/revisao/{rascunho.pk}/composicao/rateio/"
        self.client.force_login(self.financeiro)
        self.assertEqual(self.client.post(url, dados).status_code, 403)
        self.client.force_login(self.revisor)
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertContains(self.client.post(url, {**dados, "composicao_id": ficha.pk}, follow=True), "conteúdo já registrado")
        self.assertFalse(DocumentoFiscal.objects.exists())

    def _preparar_reflexos(self):
        rascunho, ficha = self._composicao_registrada()
        revisar_composicao(rascunho, composicao_id=ficha.pk, dados=self._dados_revisao_composicao(), revisor=self.segundo_revisor)
        item = ficha.memoria.itens.get()
        dados_rateio = {"criterio": "Componentes informados para o item.", **{f"{c}_{item.pk}": self._dados_composicao()[c] for c in ("frete", "seguro", "despesas", "desconto")}}
        rateio, _ = registrar_rateio(rascunho, composicao_id=ficha.pk, dados=dados_rateio, responsavel=self.revisor)
        dados = {"fundamentacao": "Orientação sintética para conferir as bases."}
        for tributo in ("icms", "icms_st", "fcp", "ipi", "pis", "cofins", "ibs", "cbs"):
            dados[f"total_base_{tributo}"] = getattr(item, f"base_{tributo}")
            dados[f"item_{item.pk}_{tributo}_base_final"] = getattr(item, f"base_{tributo}")
            for c in ("frete", "seguro", "despesas", "desconto"):
                dados[f"item_{item.pk}_{tributo}_{c}"] = "0"
        return rascunho, rateio, dados, dados_rateio

    def test_reflexos_historico_idempotencia_imutabilidade_e_tela(self):
        rascunho, rateio, dados, _ = self._preparar_reflexos()
        registro, criado = registrar_reflexos(rascunho, rateio_id=rateio.pk, dados=dados, responsavel=self.revisor)
        self.assertTrue(criado)
        self.assertEqual(registro.conteudo_snapshot["rateio_sha256"], rateio.conteudo_sha256)
        self.assertFalse(registro.conteudo_snapshot["permite_emissao"])
        repetido, criado = registrar_reflexos(rascunho, rateio_id=rateio.pk, dados=dados, responsavel=self.revisor)
        self.assertFalse(criado)
        self.assertEqual(repetido.pk, registro.pk)
        novo, _ = registrar_reflexos(rascunho, rateio_id=rateio.pk, dados={**dados, "fundamentacao": "Nova orientação sintética registrada."}, responsavel=self.revisor)
        self.assertEqual(novo.versao, 2)
        for operacao in (registro.save, registro.delete, lambda: rateio.reflexos.update(versao=8), rateio.reflexos.all().delete):
            with self.assertRaises(ValueError):
                operacao()
        self.client.force_login(self.revisor)
        url = f"/fiscal/devolucoes-fornecedor/revisao/{rascunho.pk}/reflexos/"
        self.assertEqual(self.client.get(url).status_code, 405)
        resposta = self.client.post(url, {**dados, "rateio_id": rateio.pk}, follow=True)
        self.assertContains(resposta, "conteúdo já registrado")
        self.assertContains(resposta, "Nova orientação sintética registrada.")
        self.assertFalse(DocumentoFiscal.objects.exists())

    def test_reflexos_permissoes_id_invalido_e_somas(self):
        rascunho, rateio, dados, _ = self._preparar_reflexos()
        for user in (self.financeiro, self.usuario):
            with self.assertRaisesMessage(ValidationError, "Sem permissão"):
                registrar_reflexos(rascunho, rateio_id=rateio.pk, dados=dados, responsavel=user)
            self.client.force_login(user)
            self.assertEqual(self.client.post(f"/fiscal/devolucoes-fornecedor/revisao/{rascunho.pk}/reflexos/", {**dados, "rateio_id": rateio.pk}).status_code, 403)
        for pk in ("abc", None, 999999):
            with self.assertRaises(ValidationError):
                registrar_reflexos(rascunho, rateio_id=pk, dados=dados, responsavel=self.revisor)
        with self.assertRaisesMessage(ValidationError, "diverge dos itens"):
            registrar_reflexos(rascunho, rateio_id=rateio.pk, dados={**dados, "total_base_icms": "999"}, responsavel=self.revisor)
        self.assertFalse(rateio.reflexos.exists())

    def test_reflexos_bloqueia_rateio_superado_e_xml_alterado(self):
        rascunho, rateio, dados, dados_rateio = self._preparar_reflexos()
        dfe = DocumentoDFeRecebido.objects.get(entrada_compra=self.entrada)
        dfe.xml_conteudo += " "
        dfe.save(update_fields=["xml_conteudo"])
        with self.assertRaisesMessage(ValidationError, "XML original divergiu"):
            registrar_reflexos(rascunho, rateio_id=rateio.pk, dados=dados, responsavel=self.revisor)
        dfe.xml_conteudo = dfe.xml_conteudo[:-1]
        dfe.save(update_fields=["xml_conteudo"])
        registrar_rateio(rascunho, composicao_id=rateio.composicao_id, dados={**dados_rateio, "criterio": "Novo rateio informado para conferência."}, responsavel=self.revisor)
        with self.assertRaisesMessage(ValidationError, "superado"):
            registrar_reflexos(rascunho, rateio_id=rateio.pk, dados=dados, responsavel=self.revisor)
        self.assertFalse(rateio.reflexos.exists())

    def test_reflexos_confere_hash_e_itens_do_rateio(self):
        from .reflexos_devolucao import validar_rateio_atual
        from .devolucao_fornecedor import _hash_conteudo_revisao
        rascunho, rateio, _, _ = self._preparar_reflexos()
        rateio.conteudo_snapshot["itens"][0]["frete"] = "3.00"
        with self.assertRaisesMessage(ValidationError, "integridade"):
            validar_rateio_atual(rascunho, rateio)
        rateio.conteudo_sha256 = _hash_conteudo_revisao(rateio.conteudo_snapshot)
        with self.assertRaisesMessage(ValidationError, "divergiram"):
            validar_rateio_atual(rascunho, rateio)

    def _reflexos_registrados(self):
        rascunho, rateio, dados, dados_rateio = self._preparar_reflexos()
        registro, _ = registrar_reflexos(rascunho, rateio_id=rateio.pk, dados=dados, responsavel=self.revisor)
        return rascunho, registro, dados, dados_rateio

    def test_revisao_reflexos_segregada_unica_e_imutavel(self):
        rascunho, registro, _, _ = self._reflexos_registrados()
        dados = {"decisao": "APROVAR", "justificativa": "Bases conferidas de forma independente."}
        with self.assertRaisesMessage(ValidationError, "outro responsável"):
            revisar_reflexos(rascunho, reflexos_id=registro.pk, dados=dados, revisor=self.revisor)
        revisao = revisar_reflexos(rascunho, reflexos_id=registro.pk, dados=dados, revisor=self.segundo_revisor)
        self.assertEqual(revisao.conteudo_snapshot["reflexos_sha256"], registro.conteudo_sha256)
        self.assertFalse(revisao.conteudo_snapshot["permite_emissao"])
        with self.assertRaisesMessage(ValidationError, "decisão imutável"):
            revisar_reflexos(rascunho, reflexos_id=registro.pk, dados=dados, revisor=self.segundo_revisor)
        for operacao in (revisao.save, revisao.delete, lambda: type(revisao).objects.filter(pk=revisao.pk).update(decisao="APROVAR"), lambda: type(revisao).objects.filter(pk=revisao.pk).delete()):
            with self.assertRaises(ValueError):
                operacao()
        self.assertFalse(DocumentoFiscal.objects.exists())

    def test_revisao_reflexos_tela_permissoes_e_correcao(self):
        rascunho, registro, dados_registro, _ = self._reflexos_registrados()
        url = f"/fiscal/devolucoes-fornecedor/revisao/{rascunho.pk}/reflexos/revisar/"
        dados = {"reflexos_id": registro.pk, "decisao": "DEVOLVER_CORRECAO", "justificativa": "Corrigir os impactos informados nas bases."}
        for user in (self.financeiro, self.usuario):
            self.client.force_login(user)
            self.assertEqual(self.client.post(url, dados).status_code, 403)
            with self.assertRaisesMessage(ValidationError, "Sem permissão"):
                revisar_reflexos(rascunho, reflexos_id=registro.pk, dados=dados, revisor=user)
        self.client.force_login(self.revisor)
        self.assertNotContains(self.client.get(f"/fiscal/devolucoes-fornecedor/revisao/{rascunho.pk}/"), "Registrar revisão dos reflexos")
        self.client.force_login(self.segundo_revisor)
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertContains(self.client.get(f"/fiscal/devolucoes-fornecedor/revisao/{rascunho.pk}/"), "Registrar revisão dos reflexos")
        self.assertContains(self.client.post(url, dados, follow=True), "Reflexos devolvidos para correção")
        novo, _ = registrar_reflexos(rascunho, rateio_id=registro.rateio_id, dados={**dados_registro, "fundamentacao": "Orientação corrigida para nova conferência."}, responsavel=self.revisor)
        self.assertEqual(novo.versao, 2)
        self.assertEqual(registro.revisao.decisao, "DEVOLVER_CORRECAO")

    def test_revisao_reflexos_bloqueia_versoes_superadas_e_xml(self):
        rascunho, registro, dados, dados_rateio = self._reflexos_registrados()
        revisao = {"decisao": "APROVAR", "justificativa": "Conferência independente das bases."}
        novo, _ = registrar_reflexos(rascunho, rateio_id=registro.rateio_id, dados={**dados, "fundamentacao": "Nova orientação para bases declaradas."}, responsavel=self.revisor)
        with self.assertRaisesMessage(ValidationError, "superados"):
            revisar_reflexos(rascunho, reflexos_id=registro.pk, dados=revisao, revisor=self.segundo_revisor)
        dfe = DocumentoDFeRecebido.objects.get(entrada_compra=self.entrada)
        original = dfe.xml_conteudo
        dfe.xml_conteudo += " "
        dfe.save(update_fields=["xml_conteudo"])
        with self.assertRaisesMessage(ValidationError, "XML original divergiu"):
            revisar_reflexos(rascunho, reflexos_id=novo.pk, dados=revisao, revisor=self.segundo_revisor)
        dfe.xml_conteudo = original
        dfe.save(update_fields=["xml_conteudo"])
        registrar_rateio(rascunho, composicao_id=registro.rateio.composicao_id, dados={**dados_rateio, "criterio": "Rateio atualizado para conferência."}, responsavel=self.revisor)
        with self.assertRaisesMessage(ValidationError, "rateio foi superado"):
            revisar_reflexos(rascunho, reflexos_id=novo.pk, dados=revisao, revisor=self.segundo_revisor)

    def test_revisao_reflexos_confere_integridade_e_somas(self):
        from .devolucao_fornecedor import _hash_conteudo_revisao
        rascunho, registro, _, _ = self._reflexos_registrados()
        registro.conteudo_snapshot["totais_bases"]["icms"] = "999.00"
        with self.assertRaisesMessage(ValidationError, "integridade"):
            validar_reflexos_atuais(rascunho, registro)
        registro.conteudo_sha256 = _hash_conteudo_revisao(registro.conteudo_snapshot)
        with self.assertRaisesMessage(ValidationError, "divergiram"):
            validar_reflexos_atuais(rascunho, registro)

    def test_revisao_reflexos_outra_empresa_e_ids_invalidos(self):
        rascunho, registro, _, _ = self._reflexos_registrados()
        dados = {"decisao": "APROVAR", "justificativa": "Conferência independente das bases."}
        for pk in (None, "abc", 999999):
            with self.assertRaises(ValidationError):
                revisar_reflexos(rascunho, reflexos_id=pk, dados=dados, revisor=self.segundo_revisor)
        empresa = Empresa.objects.create(razao_social="Outra empresa", nome_fantasia="Outra", cnpj="33.333.333/0001-33")
        filial = Filial.objects.create(empresa=empresa, nome="Outra filial", cnpj=empresa.cnpj, uf="GO")
        user = get_user_model().objects.create_user("revisor_outra_empresa_reflexos")
        PerfilUsuario.objects.create(usuario=user, filial=filial, tipo=TipoPerfil.CONTABILIDADE)
        with self.assertRaisesMessage(ValidationError, "outra empresa"):
            revisar_reflexos(rascunho, reflexos_id=registro.pk, dados=dados, revisor=user)
        self.client.force_login(user)
        self.assertEqual(self.client.post(f"/fiscal/devolucoes-fornecedor/revisao/{rascunho.pk}/reflexos/revisar/", {**dados, "reflexos_id": registro.pk}).status_code, 404)

    def test_revisao_reflexos_exige_decisao_e_justificativa(self):
        for dados in ({}, {"decisao": "APROVAR", "justificativa": "curta"}, {"decisao": "EMITIR", "justificativa": "Conferência independente das bases."}):
            self.assertFalse(RevisaoReflexosForm(dados).is_valid())

    def test_rateio_rejeita_soma_versao_superada_e_xml_alterado(self):
        rascunho, ficha = self._composicao_registrada()
        revisar_composicao(rascunho, composicao_id=ficha.pk, dados=self._dados_revisao_composicao(), revisor=self.segundo_revisor)
        item = ficha.memoria.itens.get()
        dados = {"criterio": "Componentes informados para o item.", **{f"{campo}_{item.pk}": "0" for campo in ("frete", "seguro", "despesas", "desconto")}}
        with self.assertRaisesMessage(ValidationError, "soma de frete"):
            registrar_rateio(rascunho, composicao_id=ficha.pk, dados=dados, responsavel=self.revisor)
        dfe = DocumentoDFeRecebido.objects.get(entrada_compra=self.entrada)
        dfe.xml_conteudo += " "
        dfe.save(update_fields=["xml_conteudo"])
        with self.assertRaisesMessage(ValidationError, "XML original divergiu"):
            registrar_rateio(rascunho, composicao_id=ficha.pk, dados=dados, responsavel=self.revisor)
        dfe.xml_conteudo = dfe.xml_conteudo[:-1]
        dfe.save(update_fields=["xml_conteudo"])
        registrar_composicao(rascunho, dados={**self._dados_composicao(), "criterio": "Nova composição comercial informada."}, responsavel=self.revisor)
        with self.assertRaisesMessage(ValidationError, "superada"):
            registrar_rateio(rascunho, composicao_id=ficha.pk, dados=dados, responsavel=self.revisor)
        self.assertFalse(ficha.rateios.exists())

    def test_revisao_composicao_segregada_unica_imutavel(self):
        rascunho, ficha = self._composicao_registrada()
        with self.assertRaisesMessage(ValidationError, "outro responsável"):
            revisar_composicao(rascunho, composicao_id=ficha.pk, dados=self._dados_revisao_composicao(), revisor=self.revisor)
        revisao = revisar_composicao(rascunho, composicao_id=ficha.pk, dados=self._dados_revisao_composicao(), revisor=self.segundo_revisor)
        self.assertEqual(revisao.conteudo_snapshot["composicao_sha256"], ficha.conteudo_sha256)
        self.assertFalse(revisao.conteudo_snapshot["permite_emissao"])
        with self.assertRaisesMessage(ValidationError, "decisão imutável"):
            revisar_composicao(rascunho, composicao_id=ficha.pk, dados=self._dados_revisao_composicao(), revisor=self.segundo_revisor)
        with self.assertRaises(ValueError):
            revisao.save()
        self.assertFalse(DocumentoFiscal.objects.exists())

    def test_revisao_composicao_bloqueia_versao_superada_e_xml_adulterado(self):
        rascunho, antiga = self._composicao_registrada()
        atual, _ = registrar_composicao(rascunho, dados={**self._dados_composicao(), "criterio": "Composição revisada para conferência."}, responsavel=self.revisor)
        with self.assertRaisesMessage(ValidationError, "superada"):
            revisar_composicao(rascunho, composicao_id=antiga.pk, dados=self._dados_revisao_composicao(), revisor=self.segundo_revisor)
        dfe = DocumentoDFeRecebido.objects.get(entrada_compra=self.entrada)
        dfe.xml_conteudo += " "
        dfe.save(update_fields=["xml_conteudo"])
        with self.assertRaisesMessage(ValidationError, "XML original divergiu"):
            revisar_composicao(rascunho, composicao_id=atual.pk, dados=self._dados_revisao_composicao(), revisor=self.segundo_revisor)

    def test_revisao_composicao_tela_permissoes_e_correcao(self):
        rascunho, ficha = self._composicao_registrada()
        url = f"/fiscal/devolucoes-fornecedor/revisao/{rascunho.pk}/composicao/revisar/"
        dados = {"composicao_id": ficha.pk, "decisao": "DEVOLVER_CORRECAO", "justificativa": "Corrigir os valores informados."}
        self.client.force_login(self.financeiro)
        self.assertEqual(self.client.post(url, dados).status_code, 403)
        self.client.force_login(self.revisor)
        self.assertNotContains(self.client.get(f"/fiscal/devolucoes-fornecedor/revisao/{rascunho.pk}/"), "Registrar revisão da composição")
        self.client.force_login(self.segundo_revisor)
        resposta = self.client.post(url, dados, follow=True)
        self.assertContains(resposta, "Devolvida para correção")
        nova, _ = registrar_composicao(rascunho, dados={**self._dados_composicao(), "criterio": "Valores conferidos após devolução para correção."}, responsavel=self.revisor)
        self.assertEqual(nova.versao, 2)
        self.assertEqual(ficha.revisao.decisao, "DEVOLVER_CORRECAO")

    def test_composicao_exige_aprovacao_e_preserva_versoes(self):
        rascunho, _, memoria = self._memoria_registrada()
        with self.assertRaisesMessage(ValidationError, "mais recente precisa estar aprovada"):
            registrar_composicao(rascunho, dados=self._dados_composicao(), responsavel=self.revisor)
        revisar_memoria_calculo_devolucao_fornecedor(rascunho, memoria_id=memoria.pk, decisao="APROVAR", justificativa="Conferência independente concluída.", revisor=self.segundo_revisor)
        primeira, criada = registrar_composicao(rascunho, dados=self._dados_composicao(), responsavel=self.revisor)
        repetida, nova = registrar_composicao(rascunho, dados=self._dados_composicao(), responsavel=self.revisor)
        segunda, _ = registrar_composicao(rascunho, dados={**self._dados_composicao(), "frete": "3,00", "total": "14,00"}, responsavel=self.revisor)
        self.assertTrue(criada)
        self.assertFalse(nova)
        self.assertEqual(primeira.pk, repetida.pk)
        self.assertEqual(segunda.versao, 2)
        self.assertEqual(primeira.conteudo_snapshot["dados"]["total"], "13.00")
        with self.assertRaises(ValueError):
            primeira.save()
        with self.assertRaisesMessage(ValidationError, "valor base diverge"):
            registrar_composicao(rascunho, dados={**self._dados_composicao(), "valor_base": "11,00", "total": "14,00"}, responsavel=self.revisor)
        self.assertEqual(rascunho.composicoes.count(), 2)
        self.assertFalse(DocumentoFiscal.objects.exists())

    def test_composicao_recusa_inconsistencia_e_ausencia_de_confirmacao(self):
        self.assertTrue(ComposicaoDevolucaoForm(self._dados_composicao()).is_valid())
        for alteracao in ({"total": "14,00"}, {"frete": "-1"}, {"seguro": ""}, {"despesas": "0,001"}, {"confirmar_componentes": ""}, {"total": "NaN"}):
            with self.subTest(alteracao=alteracao):
                self.assertFalse(ComposicaoDevolucaoForm({**self._dados_composicao(), **alteracao}).is_valid())

    def test_composicao_tela_permissao_e_xml_adulterado(self):
        rascunho, _, memoria = self._memoria_registrada()
        revisar_memoria_calculo_devolucao_fornecedor(rascunho, memoria_id=memoria.pk, decisao="APROVAR", justificativa="Conferência independente concluída.", revisor=self.segundo_revisor)
        url = f"/fiscal/devolucoes-fornecedor/revisao/{rascunho.pk}/composicao/"
        self.client.force_login(self.financeiro)
        self.assertEqual(self.client.post(url, self._dados_composicao()).status_code, 403)
        self.client.force_login(self.revisor)
        self.assertContains(self.client.post(url, self._dados_composicao(), follow=True), "Composição versão 1")
        dfe = DocumentoDFeRecebido.objects.get(entrada_compra=self.entrada)
        dfe.xml_conteudo += " "
        dfe.save(update_fields=["xml_conteudo"])
        with self.assertRaisesMessage(ValidationError, "XML original divergiu"):
            registrar_composicao(rascunho, dados=self._dados_composicao(), responsavel=self.revisor)
        self.assertEqual(rascunho.composicoes.count(), 1)

    def test_transporte_exige_memoria_aprovada_e_e_versionado(self):
        rascunho, _, memoria = self._memoria_registrada()
        with self.assertRaisesMessage(ValidationError, "mais recente precisa estar aprovada"):
            registrar_transporte(rascunho, dados=self._dados_transporte(), responsavel=self.revisor)
        revisar_memoria_calculo_devolucao_fornecedor(rascunho, memoria_id=memoria.pk, decisao="APROVAR", justificativa="Conferência independente concluída.", revisor=self.segundo_revisor)
        primeira, criada = registrar_transporte(rascunho, dados=self._dados_transporte(), responsavel=self.revisor)
        repetida, criada_repetida = registrar_transporte(rascunho, dados=self._dados_transporte(), responsavel=self.revisor)
        segunda, _ = registrar_transporte(rascunho, dados={**self._dados_transporte(), "observacao": "Nova informação logística"}, responsavel=self.revisor)
        self.assertTrue(criada)
        self.assertFalse(criada_repetida)
        self.assertEqual(primeira.pk, repetida.pk)
        self.assertEqual(segunda.versao, 2)
        with self.assertRaisesMessage(ValueError, "imutáveis"):
            primeira.save()
        self.assertFalse(DocumentoFiscal.objects.exists())

    def test_transporte_valida_modalidade_pesos_e_ausencia_de_defaults(self):
        for alteracao in (
            {"modalidade": ""}, {"modalidade": "9", "nome": "Transportadora"},
            {"quantidade_volumes": "1", "peso_liquido": "2", "peso_bruto": "1"},
            {"peso_bruto": "-1"}, {"peso_bruto": "0.0001"},
            {"especie": "Caixa"},
        ):
            with self.subTest(alteracao=alteracao):
                self.assertFalse(TransporteDevolucaoForm({**self._dados_transporte(), **alteracao}).is_valid())
        self.assertTrue(TransporteDevolucaoForm({"modalidade": "2", "quantidade_volumes": "2", "peso_liquido": "1,500", "peso_bruto": "2,000", "especie": "Caixas"}).is_valid())

    def test_transporte_respeita_permissao_e_xml_original(self):
        rascunho, _, memoria = self._memoria_registrada()
        revisar_memoria_calculo_devolucao_fornecedor(rascunho, memoria_id=memoria.pk, decisao="APROVAR", justificativa="Conferência independente concluída.", revisor=self.segundo_revisor)
        url = f"/fiscal/devolucoes-fornecedor/revisao/{rascunho.pk}/transporte/"
        self.client.force_login(self.financeiro)
        self.assertEqual(self.client.post(url, self._dados_transporte()).status_code, 403)
        self.client.force_login(self.revisor)
        self.assertContains(self.client.post(url, self._dados_transporte(), follow=True), "Transporte versão 1")
        dfe = DocumentoDFeRecebido.objects.get(entrada_compra=self.entrada)
        dfe.xml_conteudo += " "
        dfe.save(update_fields=["xml_conteudo"])
        with self.assertRaisesMessage(ValidationError, "XML original divergiu"):
            registrar_transporte(rascunho, dados=self._dados_transporte(), responsavel=self.revisor)
        self.assertEqual(TransporteDevolucaoFornecedor.objects.count(), 1)

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

    def test_parametrizacao_por_item_versionada_e_imutavel_nao_calcula_nem_emite(self):
        rascunho, parecer = self._parecer_registrado()

        parametros, criado = registrar_parametrizacao_itens_devolucao_fornecedor(
            rascunho,
            parecer_id=parecer.pk,
            dados=self._dados_parametros(rascunho),
            responsavel=self.revisor,
        )

        self.assertTrue(criado)
        self.assertEqual(parametros.versao, 1)
        self.assertEqual(parametros.parecer, parecer)
        self.assertEqual(parametros.conteudo_snapshot["parecer_sha256"], parecer.conteudo_sha256)
        item = parametros.itens.get()
        self.assertEqual(item.numero_item_xml, "1")
        self.assertEqual(item.tipo_codigo_icms, "CST")
        self.assertEqual(item.origem_icms, "0")
        self.assertEqual(item.codigo_icms, "00")
        self.assertEqual(item.codigo_ipi, "NA")
        self.assertEqual(item.codigo_cbenef, "NA")
        self.assertFalse(DocumentoFiscal.objects.exists())
        with self.assertRaisesMessage(ValueError, "imutáveis"):
            parametros.conteudo_sha256 = "b" * 64
            parametros.save()
        with self.assertRaisesMessage(ValueError, "imutáveis"):
            item.codigo_icms = "20"
            item.save()

    def test_parametrizacao_incompleta_ou_codigo_invalido_e_atomica(self):
        rascunho, parecer = self._parecer_registrado()
        item = rascunho.itens.get()
        incompleto = self._dados_parametros(rascunho)
        incompleto.pop(f"tratamento_cbenef_{item.pk}")

        with self.assertRaisesMessage(ValidationError, "tratamento do cBenef"):
            registrar_parametrizacao_itens_devolucao_fornecedor(
                rascunho,
                parecer_id=parecer.pk,
                dados=incompleto,
                responsavel=self.revisor,
            )
        with self.assertRaisesMessage(ValidationError, "dois dígitos"):
            registrar_parametrizacao_itens_devolucao_fornecedor(
                rascunho,
                parecer_id=parecer.pk,
                dados=self._dados_parametros(
                    rascunho, **{f"codigo_icms_{item.pk}": "102"}
                ),
                responsavel=self.revisor,
            )

        self.assertFalse(ParametrizacaoFiscalDevolucaoFornecedor.objects.exists())
        self.assertFalse(ItemParametrizacaoFiscalDevolucaoFornecedor.objects.exists())

    def test_parametrizacao_identica_e_idempotente_e_mudanca_cria_versao(self):
        rascunho, parecer = self._parecer_registrado()
        item = rascunho.itens.get()
        dados = self._dados_parametros(rascunho)

        primeira, criada = registrar_parametrizacao_itens_devolucao_fornecedor(
            rascunho,
            parecer_id=parecer.pk,
            dados=dados,
            responsavel=self.revisor,
        )
        repetida, criada_repetida = registrar_parametrizacao_itens_devolucao_fornecedor(
            rascunho,
            parecer_id=parecer.pk,
            dados=dados,
            responsavel=self.revisor,
        )
        segunda, criada_segunda = registrar_parametrizacao_itens_devolucao_fornecedor(
            rascunho,
            parecer_id=parecer.pk,
            dados=self._dados_parametros(
                rascunho,
                **{f"observacao_{item.pk}": "Segunda orientação expressamente revisada."},
            ),
            responsavel=self.revisor,
        )

        self.assertTrue(criada)
        self.assertFalse(criada_repetida)
        self.assertEqual(primeira.pk, repetida.pk)
        self.assertTrue(criada_segunda)
        self.assertEqual(segunda.versao, 2)
        self.assertEqual(ParametrizacaoFiscalDevolucaoFornecedor.objects.count(), 2)
        self.assertFalse(DocumentoFiscal.objects.exists())

    def test_parametrizacao_bloqueia_xml_divergente(self):
        rascunho, parecer = self._parecer_registrado()
        dfe = DocumentoDFeRecebido.objects.get(entrada_compra=self.entrada)
        dfe.xml_conteudo = dfe.xml_conteudo.replace("3.40", "3.42")
        dfe.save(update_fields=["xml_conteudo"])

        with self.assertRaisesMessage(ValidationError, "XML original divergiu"):
            registrar_parametrizacao_itens_devolucao_fornecedor(
                rascunho,
                parecer_id=parecer.pk,
                dados=self._dados_parametros(rascunho),
                responsavel=self.revisor,
            )

        self.assertFalse(ParametrizacaoFiscalDevolucaoFornecedor.objects.exists())

    def test_contabilidade_registra_parametros_pela_tela_e_financeiro_nao_acessa(self):
        rascunho, parecer = self._parecer_registrado()
        url = f"/fiscal/devolucoes-fornecedor/revisao/{rascunho.pk}/parametros-itens/"
        dados = {"parecer_id": str(parecer.pk), **self._dados_parametros(rascunho)}

        self.client.force_login(self.financeiro)
        self.assertEqual(self.client.post(url, dados).status_code, 403)

        self.client.force_login(self.revisor)
        detalhe = self.client.get(
            f"/fiscal/devolucoes-fornecedor/revisao/{rascunho.pk}/"
        )
        resposta = self.client.post(url, dados, follow=True)

        self.assertContains(detalhe, "Registrar nova versão dos parâmetros por item")
        self.assertContains(detalhe, "Selecione conscientemente")
        self.assertContains(resposta, "Parâmetros por item versão 1 registrados")
        self.assertContains(resposta, "CST 00")
        self.assertFalse(DocumentoFiscal.objects.exists())

    def test_memoria_calculo_versionada_imutavel_confere_totais_sem_emitir(self):
        rascunho, parametrizacao = self._parametrizacao_registrada()

        memoria, criado = registrar_memoria_calculo_devolucao_fornecedor(
            rascunho,
            parametrizacao_id=parametrizacao.pk,
            dados=self._dados_memoria(parametrizacao),
            responsavel=self.revisor,
        )

        self.assertTrue(criado)
        self.assertEqual(memoria.contrato, CONTRATO_MEMORIA_CALCULO_DEVOLUCAO_FORNECEDOR)
        self.assertEqual(memoria.versao, 1)
        self.assertEqual(memoria.parametrizacao, parametrizacao)
        self.assertEqual(memoria.totais_snapshot["valor_operacao"], "10.00")
        self.assertEqual(memoria.totais_snapshot["valor_icms"], "1.70")
        self.assertEqual(
            memoria.conteudo_snapshot["parametrizacao_sha256"],
            parametrizacao.conteudo_sha256,
        )
        item = memoria.itens.get()
        self.assertEqual(item.numero_item_xml, "1")
        self.assertEqual(item.base_icms, Decimal("10.00"))
        self.assertEqual(item.aliquota_icms, Decimal("17.0000"))
        self.assertEqual(item.valor_icms, Decimal("1.70"))
        self.assertFalse(DocumentoFiscal.objects.exists())
        with self.assertRaisesMessage(ValueError, "imutáveis"):
            memoria.criterio_arredondamento = "Tentativa de alteração"
            memoria.save()
        with self.assertRaisesMessage(ValueError, "imutáveis"):
            item.valor_icms = Decimal("1.71")
            item.save()

    def test_memoria_exige_campos_nao_aplicaveis_e_totais_atomicos(self):
        rascunho, parametrizacao = self._parametrizacao_registrada()
        item = parametrizacao.itens.get()
        incompleto = self._dados_memoria(parametrizacao)
        incompleto.pop(f"base_cbs_{item.pk}")

        with self.assertRaisesMessage(ValidationError, "base de CBS"):
            registrar_memoria_calculo_devolucao_fornecedor(
                rascunho,
                parametrizacao_id=parametrizacao.pk,
                dados=incompleto,
                responsavel=self.revisor,
            )
        with self.assertRaisesMessage(ValidationError, "não confere"):
            registrar_memoria_calculo_devolucao_fornecedor(
                rascunho,
                parametrizacao_id=parametrizacao.pk,
                dados=self._dados_memoria(parametrizacao, total_valor_icms="1,71"),
                responsavel=self.revisor,
            )
        with self.assertRaisesMessage(ValidationError, "IPI está marcado como não aplicável"):
            registrar_memoria_calculo_devolucao_fornecedor(
                rascunho,
                parametrizacao_id=parametrizacao.pk,
                dados=self._dados_memoria(
                    parametrizacao,
                    **{f"valor_ipi_{item.pk}": "0,01", "total_valor_ipi": "0,01"},
                ),
                responsavel=self.revisor,
            )

        self.assertFalse(MemoriaCalculoDevolucaoFornecedor.objects.exists())
        self.assertFalse(ItemMemoriaCalculoDevolucaoFornecedor.objects.exists())

    def test_memoria_identica_e_idempotente_e_mudanca_cria_versao(self):
        rascunho, parametrizacao = self._parametrizacao_registrada()
        item = parametrizacao.itens.get()
        dados = self._dados_memoria(parametrizacao)

        primeira, criada = registrar_memoria_calculo_devolucao_fornecedor(
            rascunho,
            parametrizacao_id=parametrizacao.pk,
            dados=dados,
            responsavel=self.revisor,
        )
        repetida, criada_repetida = registrar_memoria_calculo_devolucao_fornecedor(
            rascunho,
            parametrizacao_id=parametrizacao.pk,
            dados=dados,
            responsavel=self.revisor,
        )
        segunda, criada_segunda = registrar_memoria_calculo_devolucao_fornecedor(
            rascunho,
            parametrizacao_id=parametrizacao.pk,
            dados=self._dados_memoria(
                parametrizacao,
                **{f"observacao_memoria_{item.pk}": "Nova conferência expressamente informada."},
            ),
            responsavel=self.revisor,
        )

        self.assertTrue(criada)
        self.assertFalse(criada_repetida)
        self.assertEqual(primeira.pk, repetida.pk)
        self.assertTrue(criada_segunda)
        self.assertEqual(segunda.versao, 2)
        self.assertEqual(MemoriaCalculoDevolucaoFornecedor.objects.count(), 2)
        self.assertFalse(DocumentoFiscal.objects.exists())

    def test_memoria_bloqueia_xml_divergente(self):
        rascunho, parametrizacao = self._parametrizacao_registrada()
        dfe = DocumentoDFeRecebido.objects.get(entrada_compra=self.entrada)
        dfe.xml_conteudo = dfe.xml_conteudo.replace("3.40", "3.43")
        dfe.save(update_fields=["xml_conteudo"])

        with self.assertRaisesMessage(ValidationError, "XML original divergiu"):
            registrar_memoria_calculo_devolucao_fornecedor(
                rascunho,
                parametrizacao_id=parametrizacao.pk,
                dados=self._dados_memoria(parametrizacao),
                responsavel=self.revisor,
            )

        self.assertFalse(MemoriaCalculoDevolucaoFornecedor.objects.exists())

    def test_contabilidade_registra_memoria_pela_tela_e_financeiro_nao_acessa(self):
        rascunho, parametrizacao = self._parametrizacao_registrada()
        url = f"/fiscal/devolucoes-fornecedor/revisao/{rascunho.pk}/memoria-calculo/"
        dados = {
            "parametrizacao_id": str(parametrizacao.pk),
            **self._dados_memoria(parametrizacao),
        }

        self.client.force_login(self.financeiro)
        self.assertEqual(self.client.post(url, dados).status_code, 403)

        self.client.force_login(self.revisor)
        detalhe = self.client.get(f"/fiscal/devolucoes-fornecedor/revisao/{rascunho.pk}/")
        resposta = self.client.post(url, dados, follow=True)

        self.assertContains(detalhe, "Registrar nova memória de cálculo")
        self.assertContains(detalhe, "usando zero explícito")
        self.assertContains(resposta, "Memória de cálculo versão 1 registrada")
        self.assertContains(resposta, "totais conferidos")
        self.assertFalse(DocumentoFiscal.objects.exists())

    def test_revisao_memoria_em_quatro_olhos_e_imutavel_nao_libera_emissao(self):
        rascunho, _parametrizacao, memoria = self._memoria_registrada()

        revisao = revisar_memoria_calculo_devolucao_fornecedor(
            rascunho,
            memoria_id=memoria.pk,
            decisao=DecisaoRevisaoMemoriaCalculoFornecedor.APROVAR,
            justificativa="Bases, alíquotas, valores e totalizações conferidos integralmente.",
            revisor=self.segundo_revisor,
        )

        self.assertEqual(
            revisao.contrato,
            CONTRATO_REVISAO_MEMORIA_CALCULO_DEVOLUCAO_FORNECEDOR,
        )
        self.assertEqual(revisao.memoria, memoria)
        self.assertEqual(revisao.decisao, DecisaoRevisaoMemoriaCalculoFornecedor.APROVAR)
        self.assertEqual(revisao.conteudo_snapshot["memoria_sha256"], memoria.conteudo_sha256)
        self.assertNotEqual(revisao.revisor, memoria.responsavel)
        self.assertFalse(DocumentoFiscal.objects.exists())
        with self.assertRaisesMessage(ValueError, "imutáveis"):
            revisao.justificativa = "Tentativa de alteração"
            revisao.save()
        with self.assertRaisesMessage(ValueError, "imutáveis"):
            RevisaoMemoriaCalculoDevolucaoFornecedor.objects.filter(pk=revisao.pk).delete()

    def test_revisao_memoria_bloqueia_autorrevisao_e_versao_superada(self):
        rascunho, parametrizacao, primeira = self._memoria_registrada()
        item = parametrizacao.itens.get()

        with self.assertRaisesMessage(ValidationError, "outro responsável fiscal"):
            revisar_memoria_calculo_devolucao_fornecedor(
                rascunho,
                memoria_id=primeira.pk,
                decisao=DecisaoRevisaoMemoriaCalculoFornecedor.APROVAR,
                justificativa="Tentativa de aprovar a própria memória de cálculo fiscal.",
                revisor=self.revisor,
            )

        segunda, _ = registrar_memoria_calculo_devolucao_fornecedor(
            rascunho,
            parametrizacao_id=parametrizacao.pk,
            dados=self._dados_memoria(
                parametrizacao,
                **{f"observacao_memoria_{item.pk}": "Segunda versão para revisão segregada."},
            ),
            responsavel=self.revisor,
        )
        with self.assertRaisesMessage(ValidationError, "versão mais recente"):
            revisar_memoria_calculo_devolucao_fornecedor(
                rascunho,
                memoria_id=primeira.pk,
                decisao=DecisaoRevisaoMemoriaCalculoFornecedor.APROVAR,
                justificativa="Tentativa de aprovar uma memória que já foi superada.",
                revisor=self.segundo_revisor,
            )

        self.assertEqual(segunda.versao, 2)
        self.assertFalse(RevisaoMemoriaCalculoDevolucaoFornecedor.objects.exists())

    def test_revisao_memoria_e_unica_e_bloqueia_xml_divergente(self):
        rascunho, _parametrizacao, memoria = self._memoria_registrada()
        dfe = DocumentoDFeRecebido.objects.get(entrada_compra=self.entrada)
        dfe.xml_conteudo = dfe.xml_conteudo.replace("3.40", "3.44")
        dfe.save(update_fields=["xml_conteudo"])

        with self.assertRaisesMessage(ValidationError, "XML original divergiu"):
            revisar_memoria_calculo_devolucao_fornecedor(
                rascunho,
                memoria_id=memoria.pk,
                decisao=DecisaoRevisaoMemoriaCalculoFornecedor.APROVAR,
                justificativa="Tentativa de revisar após alteração da evidência original.",
                revisor=self.segundo_revisor,
            )
        dfe.xml_conteudo = dfe.xml_conteudo.replace("3.44", "3.40")
        dfe.save(update_fields=["xml_conteudo"])
        revisar_memoria_calculo_devolucao_fornecedor(
            rascunho,
            memoria_id=memoria.pk,
            decisao=DecisaoRevisaoMemoriaCalculoFornecedor.DEVOLVER_CORRECAO,
            justificativa="Revisão devolvida para ajuste documentado em nova versão.",
            revisor=self.segundo_revisor,
        )
        with self.assertRaisesMessage(ValidationError, "decisão imutável"):
            revisar_memoria_calculo_devolucao_fornecedor(
                rascunho,
                memoria_id=memoria.pk,
                decisao=DecisaoRevisaoMemoriaCalculoFornecedor.APROVAR,
                justificativa="Tentativa de substituir a decisão já registrada.",
                revisor=self.segundo_revisor,
            )

        self.assertEqual(RevisaoMemoriaCalculoDevolucaoFornecedor.objects.count(), 1)
        self.assertFalse(DocumentoFiscal.objects.exists())

    def test_segundo_contador_revisa_memoria_pela_tela_e_financeiro_nao_acessa(self):
        rascunho, _parametrizacao, memoria = self._memoria_registrada()
        url = f"/fiscal/devolucoes-fornecedor/revisao/{rascunho.pk}/memoria-calculo/revisar/"
        dados = {
            "memoria_id": str(memoria.pk),
            "decisao": DecisaoRevisaoMemoriaCalculoFornecedor.APROVAR,
            "justificativa": "Conferência segregada concluída pelo segundo responsável fiscal.",
        }

        self.client.force_login(self.financeiro)
        self.assertEqual(self.client.post(url, dados).status_code, 403)

        self.client.force_login(self.revisor)
        detalhe_autor = self.client.get(f"/fiscal/devolucoes-fornecedor/revisao/{rascunho.pk}/")
        self.assertContains(detalhe_autor, "O autor da memória não pode aprovar")
        self.assertNotContains(detalhe_autor, "Aprovar somente a memória")

        self.client.force_login(self.segundo_revisor)
        detalhe = self.client.get(f"/fiscal/devolucoes-fornecedor/revisao/{rascunho.pk}/")
        resposta = self.client.post(url, dados, follow=True)

        self.assertContains(detalhe, "Aprovar somente a memória")
        self.assertContains(detalhe, "Devolver memória para correção")
        self.assertContains(resposta, "aprovada sem liberar XML ou emissão")
        self.assertContains(resposta, "Aprovar memória")
        self.assertFalse(DocumentoFiscal.objects.exists())
