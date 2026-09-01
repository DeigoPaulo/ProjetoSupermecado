from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from apps.auditoria.models import LogAuditoria
from apps.empresas.models import Empresa, Filial
from apps.produtos.models import Categoria, Produto

from .fechamento_contabil import capturar_fechamento_estoque_contabil
from .models import Estoque, FechamentoEstoqueContabil, ItemFechamentoEstoqueContabil


class FechamentoEstoqueContabilTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_superuser("fechamento-estoque", "fechamento@example.com", "123")
        self.empresa = Empresa.objects.create(
            razao_social="Mercado Fechamento LTDA", nome_fantasia="Mercado Fechamento", cnpj="12.345.678/0001-90"
        )
        self.filial = Filial.objects.create(empresa=self.empresa, nome="Matriz", cnpj=self.empresa.cnpj)
        categoria = Categoria.objects.create(nome="Categoria fechamento")
        self.produto = Produto.objects.create(
            codigo_barras="7891111111111", nome="Produto fechamento", categoria=categoria,
            preco_custo=Decimal("4.00"), preco_venda=Decimal("7.00"), ncm="10063021", cest="1704900",
        )
        self.estoque = Estoque.objects.create(
            produto=self.produto, filial=self.filial, quantidade_atual=Decimal("12.000"),
            quantidade_reservada=Decimal("2.000"), custo_medio=Decimal("4.500000"),
        )

    def test_captura_imutavel_idempotente_com_hash_e_valor(self):
        fechamento, criado = capturar_fechamento_estoque_contabil(filial=self.filial, usuario=self.usuario)
        repetido, criado_novamente = capturar_fechamento_estoque_contabil(filial=self.filial, usuario=self.usuario)

        self.assertTrue(criado)
        self.assertFalse(criado_novamente)
        self.assertEqual(repetido.pk, fechamento.pk)
        self.assertEqual(fechamento.total_itens, 1)
        self.assertEqual(fechamento.valor_total_custo, Decimal("54.00"))
        self.assertEqual(len(fechamento.conteudo_sha256), 64)
        self.assertEqual(fechamento.capturado_por, self.usuario)
        self.assertTrue(LogAuditoria.objects.filter(acao="FECHAMENTO_ESTOQUE_CONTABIL", objeto_id=str(fechamento.pk)).exists())
        item = fechamento.itens.get()
        self.assertEqual(item.quantidade_disponivel, Decimal("10.000"))
        self.assertEqual(item.valor_custo, Decimal("54.00"))
        self.assertEqual(item.nome_produto, "Produto fechamento")
        with self.assertRaisesMessage(ValueError, "imutáveis"):
            fechamento.delete()
        with self.assertRaisesMessage(ValueError, "imutáveis"):
            ItemFechamentoEstoqueContabil.objects.filter(pk=item.pk).update(nome_produto="Alterado")

    def test_recusa_snapshot_retroativo_e_divergencia_apos_fechamento(self):
        with self.assertRaisesMessage(ValidationError, "snapshot retroativo"):
            capturar_fechamento_estoque_contabil(
                filial=self.filial, usuario=self.usuario, data_referencia=timezone.localdate() - timedelta(days=1)
            )
        capturar_fechamento_estoque_contabil(filial=self.filial, usuario=self.usuario)
        self.estoque.quantidade_atual = Decimal("13.000")
        self.estoque.save(update_fields=["quantidade_atual", "atualizado_em"])
        with self.assertRaisesMessage(ValidationError, "diverge"):
            capturar_fechamento_estoque_contabil(filial=self.filial, usuario=self.usuario)

    def test_recusa_responsavel_sem_perfil_autorizado(self):
        operador = get_user_model().objects.create_user("operador-fechamento")
        with self.assertRaisesMessage(ValidationError, "Administração ou Contabilidade"):
            capturar_fechamento_estoque_contabil(filial=self.filial, usuario=operador)

    def test_comando_exige_confirmacao_e_e_idempotente(self):
        with self.assertRaises(CommandError):
            call_command("capturar_fechamento_estoque_contabil", filial=self.filial.pk, usuario=self.usuario.username)
        saida = StringIO()
        call_command(
            "capturar_fechamento_estoque_contabil",
            filial=self.filial.pk,
            usuario=self.usuario.username,
            confirmar_fechamento=True,
            stdout=saida,
        )
        call_command(
            "capturar_fechamento_estoque_contabil",
            filial=self.filial.pk,
            usuario=self.usuario.username,
            confirmar_fechamento=True,
            stdout=saida,
        )
        self.assertEqual(FechamentoEstoqueContabil.objects.count(), 1)
        self.assertIn("já existentes: 1", saida.getvalue())
