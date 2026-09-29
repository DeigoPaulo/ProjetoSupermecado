import json
from datetime import date, datetime, time
from decimal import Decimal
from io import BytesIO
from zipfile import ZipFile

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.utils import timezone

from apps.empresas.models import Empresa, Filial
from apps.estoque.models import FechamentoEstoqueContabil, MovimentacaoEstoque, TipoMovimentacaoEstoque
from apps.pdv.models import Caixa
from apps.produtos.models import Categoria as CategoriaProduto, Produto
from apps.vendas.models import FormaPagamento, ItemVenda, PagamentoVenda, StatusVenda, Venda

from .models import (
    CategoriaFinanceira,
    CompetenciaFinanceiroContabil,
    ContaFinanceira,
    ContaMovimentoFinanceiro,
    EventoCompetenciaFinanceiroContabil,
    FechamentoMensalSnapshot,
    GrupoDRE,
    RecebivelEletronico,
    RegraLiquidacaoEletronica,
    StatusCompetenciaFinanceiroContabil,
    StatusContaFinanceira,
    StatusRecebivelEletronico,
    TipoContaFinanceira,
    TipoContaMovimento,
    TipoLancamentoFinanceiro,
)
from .services import registrar_lancamento
from .services_fechamento_mensal import (
    _json_canonico,
    calcular_hash_snapshot,
    diagnosticar_fechamento_mensal,
    fechar_competencia,
    obter_dre_competencia,
    reabrir_competencia,
    validar_hash_snapshot,
)


class FechamentoMensalFinanceiroContabilTests(TestCase):
    competencia = date(2026, 8, 1)
    fim = date(2026, 8, 31)

    def setUp(self):
        self.usuario = get_user_model().objects.create_superuser(
            "fechamento-master", "fechamento@example.com", "123"
        )
        self.empresa = Empresa.objects.create(
            razao_social="Mercado Fechamento Ltda",
            nome_fantasia="Mercado Fechamento",
            cnpj="41.111.111/0001-41",
        )
        self.filial = Filial.objects.create(
            empresa=self.empresa, nome="Matriz", cnpj=self.empresa.cnpj
        )
        self.conta_movimento = ContaMovimentoFinanceiro.objects.create(
            filial=self.filial,
            nome="Banco fechamento",
            tipo=TipoContaMovimento.BANCO,
            saldo_inicial=Decimal("100.00"),
        )
        self._criar_fechamento_estoque()

    def _criar_fechamento_estoque(self, filial=None):
        filial = filial or self.filial
        conteudo = {
            "filial_id": filial.pk,
            "data_referencia": self.fim.isoformat(),
            "criterio_custo": "CUSTO_MEDIO_PONDERADO_MOVEL",
            "itens": [],
        }
        return FechamentoEstoqueContabil.objects.create(
            filial=filial,
            data_referencia=self.fim,
            criterio_custo="CUSTO_MEDIO_PONDERADO_MOVEL",
            total_itens=0,
            valor_total_custo=Decimal("0.00"),
            conteudo_sha256=calcular_hash_snapshot(conteudo),
            capturado_por=self.usuario,
        )

    def _fechar(self, empresa=None):
        empresa = empresa or self.empresa
        return fechar_competencia(
            empresa=empresa,
            competencia=self.competencia,
            usuario=self.usuario,
            confirmacao="Confirmo o fechamento da competência 08/2026",
        )

    def _lancamento(self, valor, tipo=TipoLancamentoFinanceiro.ENTRADA, data_operacao=None, conta=None, categoria=None):
        conta = conta or self.conta_movimento
        return registrar_lancamento(
            conta=conta,
            tipo=tipo,
            descricao="Movimento de teste",
            valor=Decimal(valor),
            data=data_operacao or date(2026, 8, 15),
            usuario=self.usuario,
            origem="MANUAL",
            conta_contabil=categoria.conta_contabil if categoria and categoria.conta_contabil_id else None,
        )

    def _venda_com_cmv(self, *, custo_snapshot=Decimal("60.000000"), custo_movimento=Decimal("60.000000")):
        indice = Produto.objects.count() + 1
        categoria = CategoriaProduto.all_objects.create(nome=f"Categoria CMV {indice}")
        produto = Produto.objects.create(
            codigo_barras=f"789188{indice:07d}", nome=f"Produto CMV {indice}", categoria=categoria,
            preco_custo=Decimal("60.000000"), preco_venda=Decimal("100.00"),
        )
        caixa = Caixa.objects.create(filial=self.filial, usuario_abertura=self.usuario)
        venda = Venda.objects.create(
            filial=self.filial, caixa=caixa, usuario=self.usuario,
            total_bruto=Decimal("100.00"), desconto=Decimal("0.00"), total_liquido=Decimal("100.00"),
            status=StatusVenda.FINALIZADA,
        )
        momento = timezone.make_aware(datetime.combine(date(2026, 8, 10), time(12)))
        Venda.objects.filter(pk=venda.pk).update(data=momento)
        ItemVenda.objects.create(
            venda=venda, produto=produto, quantidade=Decimal("1.000"),
            preco_unitario_venda=Decimal("100.00"), total=Decimal("100.00"),
            custo_unitario_no_momento=custo_snapshot,
        )
        movimento = MovimentacaoEstoque.objects.create(
            produto=produto, filial=self.filial, tipo=TipoMovimentacaoEstoque.VENDA,
            quantidade=Decimal("1.000"), referencia=f"venda:{venda.pk}",
            custo_unitario=custo_movimento, custo_total=custo_movimento, usuario=self.usuario,
        )
        MovimentacaoEstoque.objects.filter(pk=movimento.pk).update(data=momento)
        return venda

    def test_fechamento_simples_cria_snapshot_hash_evento_e_bloqueia_mutacao(self):
        diagnostico = diagnosticar_fechamento_mensal(self.empresa, self.competencia)
        self.assertTrue(diagnostico["pronto"])

        snapshot = self._fechar()
        estado = CompetenciaFinanceiroContabil.objects.get(empresa=self.empresa, competencia=self.competencia)

        self.assertEqual(estado.status, StatusCompetenciaFinanceiroContabil.FECHADA)
        self.assertEqual(estado.fechamento_vigente, snapshot)
        self.assertEqual(snapshot.versao, 1)
        self.assertTrue(validar_hash_snapshot(snapshot))
        self.assertEqual(snapshot.conteudo_sha256, calcular_hash_snapshot({
            "contrato": "financial_monthly_close_v1",
            "competencia": self.competencia.isoformat(),
            "versao": 1,
            "periodo": {"inicio": self.competencia.isoformat(), "fim": self.fim.isoformat()},
            "filiais": snapshot.filiais_snapshot,
            "dre": snapshot.dre_snapshot,
            "financeiro": snapshot.financeiro_snapshot,
            "contas": snapshot.contas_snapshot,
            "recebiveis": snapshot.recebiveis_snapshot,
            "inventario": snapshot.inventario_snapshot,
            "fiscal": snapshot.fiscal_snapshot,
            "diagnostico": snapshot.diagnostico_snapshot,
            "com_ressalvas": snapshot.com_ressalvas,
        }))
        self.assertEqual(EventoCompetenciaFinanceiroContabil.objects.filter(competencia=estado).count(), 1)
        with self.assertRaisesMessage(ValidationError, "já está fechada"):
            self._fechar()
        with self.assertRaisesMessage(ValidationError, "imutáveis"):
            FechamentoMensalSnapshot.objects.filter(pk=snapshot.pk).update(observacao="alterado")
        with self.assertRaisesMessage(ValidationError, "imutáveis"):
            snapshot.save()
        with self.assertRaisesMessage(ValidationError, "imutáveis"):
            snapshot.delete()

    def test_sem_fechamento_estoque_e_cmv_incompleto_bloqueiam(self):
        filial_sem_fechamento = Filial.objects.create(
            empresa=self.empresa, nome="Filial sem fechamento", cnpj="41.111.111/0002-22"
        )
        diagnostico = diagnosticar_fechamento_mensal(self.empresa, self.competencia)
        self.assertIn("ESTOQUE_SEM_FECHAMENTO", {item["codigo"] for item in diagnostico["bloqueios"]})

        categoria = CategoriaProduto.all_objects.create(nome="Categoria fechamento")
        produto = Produto.objects.create(
            codigo_barras="7891880000001", nome="Produto sem custo", categoria=categoria,
            preco_custo=Decimal("1.000000"), preco_venda=Decimal("10.00"),
        )
        caixa = Caixa.objects.create(filial=self.filial, usuario_abertura=self.usuario)
        venda = Venda.objects.create(
            filial=self.filial, caixa=caixa, usuario=self.usuario,
            total_bruto=Decimal("10.00"), desconto=ZERO, total_liquido=Decimal("10.00"),
            status=StatusVenda.FINALIZADA,
        )
        Venda.objects.filter(pk=venda.pk).update(data=timezone.make_aware(datetime.combine(date(2026, 8, 10), time(12))))
        ItemVenda.objects.create(
            venda=venda, produto=produto, quantidade=Decimal("1.000"),
            preco_unitario_venda=Decimal("10.00"), total=Decimal("10.00"),
            custo_unitario_no_momento=None,
        )
        self._criar_fechamento_estoque(filial_sem_fechamento)
        diagnostico = diagnosticar_fechamento_mensal(self.empresa, self.competencia)
        self.assertIn("CMV_INCOMPLETO", {item["codigo"] for item in diagnostico["bloqueios"]})

    def test_nao_classificado_e_tributo_sao_ressalvas_sem_bloquear(self):
        self._lancamento("12.00", tipo=TipoLancamentoFinanceiro.SAIDA)
        diagnostico = diagnosticar_fechamento_mensal(self.empresa, self.competencia)
        codigos = {item["codigo"] for item in diagnostico["alertas"]}
        self.assertTrue(diagnostico["pronto"])
        self.assertIn("DRE_NAO_CLASSIFICADA", codigos)
        self.assertIn("TRIBUTOS_NAO_APURADOS", codigos)
        self.assertTrue(self._fechar().com_ressalvas)

    def test_reconciliacao_cmv_divergente_bloqueia(self):
        self._venda_com_cmv(custo_movimento=Decimal("55.000000"))
        diagnostico = diagnosticar_fechamento_mensal(self.empresa, self.competencia)
        self.assertFalse(diagnostico["pronto"])
        self.assertIn("CMV_DIVERGENTE", {item["codigo"] for item in diagnostico["bloqueios"]})

    def test_saldo_historico_e_conta_paga_depois(self):
        self._lancamento("50.00")
        self._lancamento("20.00", tipo=TipoLancamentoFinanceiro.SAIDA)
        self._lancamento("500.00", data_operacao=date(2026, 9, 10))
        conta_pagar = ContaFinanceira.objects.create(
            tipo=TipoContaFinanceira.PAGAR,
            status=StatusContaFinanceira.PAGA,
            descricao="Conta paga em setembro",
            filial=self.filial,
            valor=Decimal("80.00"),
            vencimento=date(2026, 8, 20),
            data_pagamento=date(2026, 9, 10),
            valor_pago=Decimal("80.00"),
            usuario=self.usuario,
        )
        ContaFinanceira.objects.filter(pk=conta_pagar.pk).update(
            criado_em=timezone.make_aware(datetime.combine(date(2026, 8, 5), time(10)))
        )

        snapshot = self._fechar()

        self.assertEqual(snapshot.financeiro_snapshot["saldos_contas"][0]["saldo"], "130.00")
        self.assertEqual(snapshot.contas_snapshot["PAGAR"]["quantidade_aberta"], 1)
        self.assertEqual(snapshot.contas_snapshot["PAGAR"]["valor_aberto"], "80.00")
        self.assertIsNotNone(conta_pagar.pk)

    def test_recebivel_pendente_de_mes_posterior_nao_bloqueia(self):
        venda = self._venda_com_cmv()
        forma = FormaPagamento.objects.create(nome="Cartão futuro", tipo="CARTAO")
        pagamento = PagamentoVenda.objects.create(venda=venda, forma_pagamento=forma, valor=Decimal("100.00"))
        regra = RegraLiquidacaoEletronica.objects.create(filial=self.filial, forma_pagamento=forma)
        RecebivelEletronico.objects.create(
            pagamento=pagamento, regra=regra, status=StatusRecebivelEletronico.PENDENTE,
            data_venda=date(2026, 8, 10), data_prevista=date(2026, 9, 10),
            valor_bruto=Decimal("100.00"), valor_liquido_previsto=Decimal("97.00"),
            taxa_prevista=Decimal("3.00"),
        )

        diagnostico = diagnosticar_fechamento_mensal(self.empresa, self.competencia)

        self.assertTrue(diagnostico["pronto"])
        self.assertEqual(diagnostico["recebiveis"]["pendentes"], 1)

    def test_reabertura_preserva_v1_e_novo_fechamento_cria_v2(self):
        primeiro = self._fechar()
        hash_v1 = primeiro.conteudo_sha256
        estado = primeiro.competencia
        reabrir_competencia(
            competencia=estado,
            usuario=self.usuario,
            motivo="Correção operacional documentada",
            confirmacao="Confirmo a reabertura da competência 08/2026",
        )
        estado.refresh_from_db()
        self.assertEqual(estado.status, StatusCompetenciaFinanceiroContabil.ABERTA)
        self.assertIsNone(estado.fechamento_vigente)
        self._lancamento("25.00")

        segundo = self._fechar()
        primeiro.refresh_from_db()

        self.assertEqual(segundo.versao, 2)
        self.assertEqual(primeiro.conteudo_sha256, hash_v1)
        self.assertNotEqual(segundo.conteudo_sha256, hash_v1)
        self.assertEqual(estado.snapshots.count(), 2)
        self.assertEqual(estado.eventos.count(), 3)

    def test_bloqueio_retroativo_evento_atual_e_multiempresa(self):
        self._fechar()
        with self.assertRaisesMessage(ValidationError, "08/2026 está fechada"):
            self._lancamento("10.00")
        atual = self._lancamento("10.00", data_operacao=date(2026, 9, 15))
        self.assertIsNotNone(atual.pk)

        outra_empresa = Empresa.objects.create(
            razao_social="Outra Empresa Ltda", nome_fantasia="Outra Empresa", cnpj="42.222.222/0001-42"
        )
        outra_filial = Filial.objects.create(empresa=outra_empresa, nome="Matriz B", cnpj=outra_empresa.cnpj)
        outra_conta = ContaMovimentoFinanceiro.objects.create(
            filial=outra_filial, nome="Banco B", tipo=TipoContaMovimento.BANCO
        )
        permitido = self._lancamento("11.00", conta=outra_conta)
        self.assertIsNotNone(permitido.pk)

    def test_dre_fechada_permanece_congelada(self):
        categoria = CategoriaFinanceira.objects.create(
            empresa=self.empresa, nome="Classificação mutável", tipo=TipoContaFinanceira.PAGAR,
            grupo_dre=GrupoDRE.NAO_CLASSIFICADO,
        )
        conta = ContaFinanceira.objects.create(
            tipo=TipoContaFinanceira.PAGAR, descricao="Despesa", categoria=categoria,
            filial=self.filial, valor=Decimal("30.00"), vencimento=date(2026, 8, 20), usuario=self.usuario,
        )
        registrar_lancamento(
            conta=self.conta_movimento, tipo=TipoLancamentoFinanceiro.SAIDA,
            descricao="Despesa", valor=Decimal("30.00"), data=date(2026, 8, 20),
            usuario=self.usuario, origem="BAIXA_CONTA", conta_financeira=conta,
        )
        snapshot = self._fechar()
        categoria.grupo_dre = GrupoDRE.DESPESA_OPERACIONAL
        categoria.save(update_fields=["grupo_dre"])

        dre, metadados = obter_dre_competencia(
            empresa=self.empresa, data_inicio=self.competencia, data_fim=self.fim,
            filial_ids=[self.filial.pk],
        )

        self.assertEqual(metadados["fonte"], "SNAPSHOT_FECHADO")
        self.assertEqual(metadados["versao"], 1)
        self.assertEqual(dre, snapshot.dre_snapshot)
        self.assertEqual(dre["saidas_nao_classificadas"]["valor"], "30.00")
        cliente = Client(HTTP_HOST="localhost")
        cliente.force_login(self.usuario)
        resposta = cliente.get(
            "/financeiro/dre.json",
            {"data_inicio": "2026-08-01", "data_fim": "2026-08-31", "empresa": self.empresa.pk},
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()["fechamento"]["fonte"], "SNAPSHOT_FECHADO")
        self.assertEqual(resposta.json()["fechamento"]["versao"], 1)

    def test_pacote_v2_fechado_inclui_snapshot_e_manifesto(self):
        snapshot = self._fechar()
        cliente = Client(HTTP_HOST="localhost")
        cliente.force_login(self.usuario)

        resposta = cliente.get("/financeiro/contabilidade/pacote-mensal.zip", {"competencia": "2026-08"})

        self.assertEqual(resposta.status_code, 200)
        with ZipFile(BytesIO(resposta.content)) as pacote:
            nomes = set(pacote.namelist())
            manifesto = json.loads(pacote.read("manifesto.json"))
            fechamento = json.loads(pacote.read("financeiro/fechamento-mensal.json"))
            dre = json.loads(pacote.read("financeiro/dre-gerencial-v2.json"))
        self.assertIn("financeiro/fechamento-mensal.json", nomes)
        self.assertTrue(manifesto["fechamento_mensal"]["fechado"])
        self.assertEqual(manifesto["fechamento_mensal"]["sha256"], snapshot.conteudo_sha256)
        self.assertEqual(fechamento["dre_snapshot"], dre)
        self.assertEqual(dre, snapshot.dre_snapshot)

    def test_pacote_aberto_nao_inventa_fechamento(self):
        cliente = Client(HTTP_HOST="localhost")
        cliente.force_login(self.usuario)
        resposta = cliente.get("/financeiro/contabilidade/pacote-mensal.zip", {"competencia": "2026-08"})
        self.assertEqual(resposta.status_code, 200)
        with ZipFile(BytesIO(resposta.content)) as pacote:
            manifesto = json.loads(pacote.read("manifesto.json"))
            nomes = set(pacote.namelist())
        self.assertFalse(manifesto["fechamento_mensal"])
        self.assertNotIn("financeiro/fechamento-mensal.json", nomes)

    def test_interface_lista_e_detalhe(self):
        cliente = Client(HTTP_HOST="localhost")
        cliente.force_login(self.usuario)
        lista = cliente.get("/financeiro/fechamentos/")
        detalhe = cliente.get(
            "/financeiro/fechamentos/detalhe/",
            {"empresa": self.empresa.pk, "competencia": "2026-08"},
        )
        self.assertEqual(lista.status_code, 200)
        self.assertEqual(detalhe.status_code, 200)
        self.assertContains(detalhe, "Fechar competência")
        self.assertContains(detalhe, "TRIBUTOS_NAO_APURADOS")
        snapshot = self._fechar()
        fechado = cliente.get(
            "/financeiro/fechamentos/detalhe/",
            {"empresa": self.empresa.pk, "competencia": "2026-08"},
        )
        self.assertEqual(fechado.status_code, 200)
        self.assertContains(fechado, "v1")
        self.assertContains(fechado, snapshot.conteudo_sha256)
        self.assertContains(fechado, "Reabrir competência")

    def test_hash_canonico_independe_da_ordem_das_chaves(self):
        primeiro = {"valor": Decimal("10.00"), "data": self.fim, "itens": [1, 2]}
        segundo = {"itens": [1, 2], "data": self.fim, "valor": Decimal("10.00")}
        self.assertEqual(_json_canonico(primeiro), _json_canonico(segundo))
        self.assertEqual(calcular_hash_snapshot(primeiro), calcular_hash_snapshot(segundo))


ZERO = Decimal("0.00")
