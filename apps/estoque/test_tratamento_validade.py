from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import PerfilUsuario, TipoPerfil
from apps.auditoria.models import LogAuditoria
from apps.empresas.models import Empresa, Filial
from apps.produtos.models import Categoria, Produto

from .models import Estoque, LoteEstoque, MovimentacaoEstoque, PerdaEstoque, StatusTratamentoValidade


class TratamentoValidadeLoteTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(razao_social="Mercado Validade", nome_fantasia="Mercado Validade", cnpj="12345678000190")
        self.filial = Filial.objects.create(empresa=self.empresa, nome="Matriz Validade")
        self.usuario = get_user_model().objects.create_user("estoquista_validade", password="senha")
        PerfilUsuario.objects.create(usuario=self.usuario, filial=self.filial, tipo=TipoPerfil.ESTOQUISTA)
        categoria = Categoria.objects.create(nome="Validade")
        self.produto = Produto.objects.create(codigo_barras="7891000088881", nome="Produto validade", categoria=categoria, preco_custo=Decimal("5"), preco_venda=Decimal("9"))
        self.estoque = Estoque.objects.create(produto=self.produto, filial=self.filial, quantidade_atual=Decimal("10.000"))
        self.lote = LoteEstoque.objects.create(produto=self.produto, filial=self.filial, codigo="VAL-01", validade=timezone.localdate()+timedelta(days=5), quantidade_inicial=Decimal("10.000"), quantidade_atual=Decimal("10.000"), custo_unitario=Decimal("5"))
        self.url = reverse("estoque:tratamento_validade_lote", args=[self.lote.pk])
        self.client.force_login(self.usuario)

    def test_planeja_sem_baixar_estoque_e_registra_auditoria(self):
        response = self.client.post(self.url, {"status": StatusTratamentoValidade.SEPARADO, "observacao": "Separar na área de conferência."})
        self.assertRedirects(response, reverse("estoque:lotes"))
        self.lote.refresh_from_db(); self.estoque.refresh_from_db()
        self.assertEqual(self.lote.tratamento_validade_status, StatusTratamentoValidade.SEPARADO)
        self.assertEqual(self.estoque.quantidade_atual, Decimal("10.000"))
        self.assertFalse(MovimentacaoEstoque.objects.exists())
        self.assertFalse(PerdaEstoque.objects.exists())
        self.assertEqual(LogAuditoria.objects.filter(acao="PLANEJAMENTO_TRATAMENTO_VALIDADE").count(), 1)
        repeticao = self.client.post(self.url, {"status": StatusTratamentoValidade.SEPARADO, "observacao": "Separar na área de conferência."})
        self.assertEqual(repeticao.status_code, 302)
        self.assertEqual(LogAuditoria.objects.filter(acao="PLANEJAMENTO_TRATAMENTO_VALIDADE").count(), 1)

    def test_lote_vencido_recusa_promocao_e_aceita_descarte_apenas_planejado(self):
        self.lote.validade = timezone.localdate()-timedelta(days=1); self.lote.save(update_fields=["validade"])
        recusado = self.client.post(self.url, {"status": StatusTratamentoValidade.PROMOCAO_PLANEJADA, "observacao": "Promoção"})
        self.assertEqual(recusado.status_code, 200)
        self.assertContains(recusado, "Lote vencido não pode")
        aprovado = self.client.post(self.url, {"status": StatusTratamentoValidade.DESCARTE_PLANEJADO, "observacao": "Aguardar conferência e baixa autorizada."})
        self.assertEqual(aprovado.status_code, 302)
        self.lote.refresh_from_db()
        self.assertEqual(self.lote.quantidade_atual, Decimal("10.000"))
        self.assertEqual(self.lote.tratamento_validade_status, StatusTratamentoValidade.DESCARTE_PLANEJADO)

    def test_recusa_lote_fora_da_janela_e_isola_empresa(self):
        self.lote.validade = timezone.localdate()+timedelta(days=31); self.lote.save(update_fields=["validade"])
        fora = self.client.post(self.url, {"status": StatusTratamentoValidade.SEPARADO, "observacao": "Antecipado"})
        self.assertEqual(fora.status_code, 200)
        self.assertContains(fora, "a vencer em até 30 dias")
        outra = Empresa.objects.create(razao_social="Outra", nome_fantasia="Outra", cnpj="11222333000144")
        filial = Filial.objects.create(empresa=outra, nome="Outra filial")
        lote = LoteEstoque.objects.create(produto=self.produto, filial=filial, codigo="EXT", validade=timezone.localdate(), quantidade_inicial=Decimal("1"), quantidade_atual=Decimal("1"), custo_unitario=Decimal("5"))
        self.assertEqual(self.client.get(reverse("estoque:tratamento_validade_lote", args=[lote.pk])).status_code, 404)
