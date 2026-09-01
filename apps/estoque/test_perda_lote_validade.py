from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.auditoria.models import LogAuditoria
from apps.empresas.models import Empresa, Filial
from apps.produtos.models import Categoria, Produto

from .models import Estoque, LoteEstoque, MovimentacaoLoteEstoque, PerdaEstoque, StatusTratamentoValidade
from .services import planejar_tratamento_validade_lote, registrar_conferencia_fisica_validade_lote, registrar_perda_lote_validade


class PerdaLoteValidadeTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_superuser("master_validade", "master@example.com", "senha")
        empresa = Empresa.objects.create(razao_social="Mercado Perda Lote", nome_fantasia="Mercado Perda Lote", cnpj="12345678000190")
        self.filial = Filial.objects.create(empresa=empresa, nome="Matriz")
        categoria = Categoria.objects.create(nome="Perda lote")
        self.produto = Produto.objects.create(codigo_barras="7891000077771", nome="Produto vencido", categoria=categoria, preco_custo=Decimal("4"), preco_venda=Decimal("8"))
        self.estoque = Estoque.objects.create(produto=self.produto, filial=self.filial, quantidade_atual=Decimal("8.000"))
        self.outro = LoteEstoque.objects.create(produto=self.produto, filial=self.filial, codigo="ANTIGO", validade=timezone.localdate()-timedelta(days=10), quantidade_inicial=Decimal("3"), quantidade_atual=Decimal("3"), custo_unitario=Decimal("3"))
        self.alvo = LoteEstoque.objects.create(produto=self.produto, filial=self.filial, codigo="ALVO", validade=timezone.localdate()-timedelta(days=2), quantidade_inicial=Decimal("5"), quantidade_atual=Decimal("5"), custo_unitario=Decimal("4"))

    def _planejar(self):
        planejar_tratamento_validade_lote(lote=self.alvo, status=StatusTratamentoValidade.DESCARTE_PLANEJADO, observacao="Conferido para descarte", usuario=self.usuario)

    def _conferir(self, quantidade=None):
        self.alvo.refresh_from_db()
        return registrar_conferencia_fisica_validade_lote(
            lote=self.alvo,
            quantidade_observada=quantidade if quantidade is not None else self.alvo.quantidade_atual,
            observacao="Contagem física antes da baixa.",
            confirmar_dados=True,
            usuario=self.usuario,
        )

    def test_baixa_somente_lote_exato_e_reconcilia_estoque(self):
        self._planejar()
        self._conferir()
        perda = registrar_perda_lote_validade(lote=self.alvo, quantidade=Decimal("2"), motivo="Vencimento confirmado", usuario=self.usuario, supervisor=self.usuario)
        self.alvo.refresh_from_db(); self.outro.refresh_from_db(); self.estoque.refresh_from_db()
        self.assertEqual(perda.lote, self.alvo)
        self.assertEqual(self.alvo.quantidade_atual, Decimal("3.000"))
        self.assertEqual(self.outro.quantidade_atual, Decimal("3.000"))
        self.assertEqual(self.estoque.quantidade_atual, Decimal("6.000"))
        self.assertEqual(MovimentacaoLoteEstoque.objects.get().lote, self.alvo)
        self.assertEqual(LogAuditoria.objects.filter(acao="REGISTRO_PERDA_LOTE_VALIDADE").count(), 1)
        self._conferir()
        registrar_perda_lote_validade(lote=self.alvo, quantidade=Decimal("3"), motivo="Saldo restante", usuario=self.usuario, supervisor=self.usuario)
        self.alvo.refresh_from_db()
        self.assertEqual(self.alvo.tratamento_validade_status, StatusTratamentoValidade.BAIXA_CONCLUIDA)

    def test_recusa_sem_plano_quantidade_excessiva_e_lote_nao_vencido(self):
        with self.assertRaisesMessage(ValidationError, "descarte planejado"):
            registrar_perda_lote_validade(lote=self.alvo, quantidade=Decimal("1"), motivo="Teste", usuario=self.usuario)
        self._planejar()
        with self.assertRaisesMessage(ValidationError, "não pode superar"):
            registrar_perda_lote_validade(lote=self.alvo, quantidade=Decimal("6"), motivo="Teste", usuario=self.usuario)
        self.alvo.validade = timezone.localdate(); self.alvo.save(update_fields=["validade"])
        with self.assertRaisesMessage(ValidationError, "efetivamente vencido"):
            registrar_perda_lote_validade(lote=self.alvo, quantidade=Decimal("1"), motivo="Teste", usuario=self.usuario)
        self.assertFalse(PerdaEstoque.objects.exists())

    def test_tela_exige_supervisor_e_conclui_no_lote(self):
        self._planejar(); self._conferir(); self.client.force_login(self.usuario)
        url = reverse("estoque:perda_lote_validade", args=[self.alvo.pk])
        pagina = self.client.get(url)
        self.assertContains(pagina, "Confirmar baixa deste lote")
        resposta = self.client.post(url, {"quantidade": "1.000", "motivo": "Baixa autorizada", "supervisor_usuario": self.usuario.username, "supervisor_senha": "senha"})
        self.assertRedirects(resposta, reverse("estoque:perdas"))
        self.assertEqual(PerdaEstoque.objects.get().lote, self.alvo)
