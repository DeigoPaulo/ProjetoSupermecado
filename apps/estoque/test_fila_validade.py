from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import PerfilUsuario, TipoPerfil
from apps.empresas.models import Empresa, Filial
from apps.produtos.models import Categoria, Produto

from .models import (
    LoteEstoque,
    MovimentacaoEstoque,
    PerdaEstoque,
    StatusTratamentoValidade,
)


from .services import registrar_conferencia_fisica_validade_lote


class FilaValidadeLoteTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(
            razao_social="Mercado Fila Validade",
            nome_fantasia="Mercado Fila Validade",
            cnpj="98765432000110",
        )
        self.filial = Filial.objects.create(empresa=self.empresa, nome="Matriz")
        self.usuario = get_user_model().objects.create_user("estoquista_fila", password="senha")
        PerfilUsuario.objects.create(
            usuario=self.usuario,
            filial=self.filial,
            tipo=TipoPerfil.ESTOQUISTA,
        )
        categoria = Categoria.objects.create(nome="Fila de validade")
        self.produto = Produto.objects.create(
            codigo_barras="7891000077779",
            nome="Produto da fila",
            categoria=categoria,
            preco_custo=Decimal("4.00"),
            preco_venda=Decimal("7.00"),
        )
        self.client.force_login(self.usuario)
        self.url = reverse("estoque:lotes")

    def criar_lote(
        self,
        codigo,
        dias,
        status=StatusTratamentoValidade.NAO_INICIADO,
        quantidade=Decimal("2.000"),
        filial=None,
    ):
        return LoteEstoque.objects.create(
            produto=self.produto,
            filial=filial or self.filial,
            codigo=codigo,
            validade=timezone.localdate() + timedelta(days=dias),
            quantidade_inicial=max(quantidade, Decimal("2.000")),
            quantidade_atual=quantidade,
            custo_unitario=Decimal("4.00"),
            tratamento_validade_status=status,
        )

    def test_fila_prioriza_vencimento_e_status_sem_alterar_estoque(self):
        vencido_sem_plano = self.criar_lote("VENC-SEM", -2)
        vencido_planejado = self.criar_lote(
            "VENC-PLAN",
            -10,
            StatusTratamentoValidade.DESCARTE_PLANEJADO,
        )
        proximo_sem_plano = self.criar_lote("PROX-SEM", 20)
        proximo_planejado = self.criar_lote(
            "PROX-PLAN",
            1,
            StatusTratamentoValidade.SEPARADO,
        )
        self.criar_lote("ENCERRADO", -5, StatusTratamentoValidade.BAIXA_CONCLUIDA)
        self.criar_lote("FORA-JANELA", 31)
        self.criar_lote("SEM-SALDO", 3, quantidade=Decimal("0.000"))

        response = self.client.get(self.url, {"situacao": "FILA_VALIDADE"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [lote.pk for lote in response.context["lotes"]],
            [
                vencido_sem_plano.pk,
                vencido_planejado.pk,
                proximo_sem_plano.pk,
                proximo_planejado.pk,
            ],
        )
        self.assertEqual(response.context["resumo_lotes"]["fila_validade"], 4)
        self.assertEqual(response.context["resumo_lotes"]["sem_tratamento"], 2)
        self.assertContains(response, "A fila distingue conferência pendente ou desatualizada")
        self.assertContains(response, "Vencido há 2 dias")
        self.assertFalse(MovimentacaoEstoque.objects.exists())
        self.assertFalse(PerdaEstoque.objects.exists())

    def test_filtro_de_tratamento_aplica_codigo_valido_e_ignora_invalido(self):
        separado = self.criar_lote("SEPARADO", 5, StatusTratamentoValidade.SEPARADO)
        self.criar_lote("PENDENTE", 4)
        filtrado = self.client.get(
            self.url,
            {"situacao": "FILA_VALIDADE", "tratamento": StatusTratamentoValidade.SEPARADO},
        )
        self.assertEqual([lote.pk for lote in filtrado.context["lotes"]], [separado.pk])
        self.assertEqual(
            filtrado.context["tratamento_selecionado"],
            StatusTratamentoValidade.SEPARADO,
        )

        invalido = self.client.get(
            self.url,
            {"situacao": "FILA_VALIDADE", "tratamento": "STATUS_INVENTADO"},
        )
        self.assertEqual(len(invalido.context["lotes"]), 2)
        self.assertEqual(invalido.context["tratamento_selecionado"], "")

    def test_fila_respeita_escopo_da_empresa(self):
        proprio = self.criar_lote("PROPRIO", 2)
        outra_empresa = Empresa.objects.create(
            razao_social="Outro Mercado",
            nome_fantasia="Outro Mercado",
            cnpj="11222333000155",
        )
        outra_filial = Filial.objects.create(empresa=outra_empresa, nome="Outra filial")
        externo = self.criar_lote("EXTERNO", -1, filial=outra_filial)

        response = self.client.get(self.url, {"situacao": "FILA_VALIDADE"})

        ids = [lote.pk for lote in response.context["lotes"]]
        self.assertEqual(ids, [proprio.pk])
        self.assertNotIn(externo.pk, ids)
        self.assertEqual(response.context["resumo_lotes"]["fila_validade"], 1)

    def conferir(self, lote, quantidade_observada, observacao="Contagem física."):
        return registrar_conferencia_fisica_validade_lote(
            lote=lote,
            quantidade_observada=Decimal(quantidade_observada),
            observacao=observacao,
            confirmar_dados=True,
            usuario=self.usuario,
        )

    def test_classifica_conferencia_pendente_divergente_pronta_e_desatualizada(self):
        pendente = self.criar_lote("CONF-PEND", 2)
        divergente = self.criar_lote("CONF-DIV", 2)
        pronto = self.criar_lote("CONF-OK", 2)
        desatualizado = self.criar_lote("CONF-OLD", 2)
        self.conferir(divergente, "1.000", "Uma unidade não localizada.")
        self.conferir(pronto, "2.000")
        self.conferir(desatualizado, "2.000")
        LoteEstoque.objects.filter(pk=desatualizado.pk).update(quantidade_atual=Decimal("1.000"))

        response = self.client.get(self.url, {"situacao": "FILA_VALIDADE"})

        estados = {lote.codigo: lote.estado_conferencia_fila for lote in response.context["lotes"]}
        self.assertEqual(estados[pendente.codigo], "PENDENTE")
        self.assertEqual(estados[desatualizado.codigo], "PENDENTE")
        self.assertEqual(estados[divergente.codigo], "DIVERGENTE")
        self.assertEqual(estados[pronto.codigo], "PRONTO")
        self.assertEqual(response.context["resumo_lotes"]["conferencia_pendente"], 2)
        self.assertEqual(response.context["resumo_lotes"]["conferencia_divergente"], 1)
        self.assertEqual(response.context["resumo_lotes"]["conferencia_pronta"], 1)
        self.assertContains(response, "Pendente ou desatualizada")
        self.assertContains(response, "Divergente")
        self.assertContains(response, "Pronto para decisão")
        self.assertFalse(MovimentacaoEstoque.objects.exists())
        self.assertFalse(PerdaEstoque.objects.exists())

    def test_filtro_de_conferencia_e_validado_no_servidor(self):
        pendente = self.criar_lote("FILTRO-PEND", 1)
        divergente = self.criar_lote("FILTRO-DIV", 1)
        pronto = self.criar_lote("FILTRO-OK", 1)
        self.conferir(divergente, "1.000", "Diferença confirmada.")
        self.conferir(pronto, "2.000")

        filtrado = self.client.get(
            self.url,
            {"situacao": "FILA_VALIDADE", "conferencia": "DIVERGENTE"},
        )
        self.assertEqual([lote.pk for lote in filtrado.context["lotes"]], [divergente.pk])
        self.assertEqual(filtrado.context["conferencia_selecionada"], "DIVERGENTE")

        invalido = self.client.get(
            self.url,
            {"situacao": "FILA_VALIDADE", "conferencia": "LIBERADO_INVENTADO"},
        )
        self.assertEqual(
            {lote.pk for lote in invalido.context["lotes"]},
            {pendente.pk, divergente.pk, pronto.pk},
        )
        self.assertEqual(invalido.context["conferencia_selecionada"], "")

