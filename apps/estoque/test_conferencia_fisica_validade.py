from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import PerfilUsuario, TipoPerfil
from apps.auditoria.models import LogAuditoria
from apps.empresas.models import Empresa, Filial
from apps.produtos.models import Categoria, Produto

from .models import (
    ConferenciaFisicaValidadeLote,
    Estoque,
    LoteEstoque,
    MovimentacaoEstoque,
    PerdaEstoque,
    StatusTratamentoValidade,
)
from .services import (
    conferencia_fisica_vigente_lote,
    planejar_tratamento_validade_lote,
    registrar_conferencia_fisica_validade_lote,
    registrar_perda_lote_validade,
)


class ConferenciaFisicaValidadeLoteTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(
            razao_social="Mercado Conferência",
            nome_fantasia="Mercado Conferência",
            cnpj="55666777000188",
        )
        self.filial = Filial.objects.create(empresa=self.empresa, nome="Matriz")
        self.usuario = get_user_model().objects.create_user("conferente_validade", password="senha")
        PerfilUsuario.objects.create(
            usuario=self.usuario,
            filial=self.filial,
            tipo=TipoPerfil.ESTOQUISTA,
        )
        categoria = Categoria.objects.create(nome="Conferência física")
        self.produto = Produto.objects.create(
            codigo_barras="7891000066665",
            nome="Produto conferido",
            categoria=categoria,
            preco_custo=Decimal("5.00"),
            preco_venda=Decimal("9.00"),
        )
        self.estoque = Estoque.objects.create(
            produto=self.produto,
            filial=self.filial,
            quantidade_atual=Decimal("10.000"),
        )
        self.lote = LoteEstoque.objects.create(
            produto=self.produto,
            filial=self.filial,
            codigo="CONF-01",
            validade=timezone.localdate() - timedelta(days=2),
            quantidade_inicial=Decimal("10.000"),
            quantidade_atual=Decimal("10.000"),
            custo_unitario=Decimal("5.00"),
        )
        self.client.force_login(self.usuario)

    def registrar(self, quantidade="10.000", observacao="Contagem confirmada."):
        return registrar_conferencia_fisica_validade_lote(
            lote=self.lote,
            quantidade_observada=Decimal(quantidade),
            observacao=observacao,
            confirmar_dados=True,
            usuario=self.usuario,
        )

    def test_registra_snapshot_imutavel_sem_ajustar_estoque(self):
        conferencia = self.registrar("8.000", "Duas unidades não localizadas; separar para inventário.")
        self.estoque.refresh_from_db()
        self.lote.refresh_from_db()

        self.assertEqual(conferencia.quantidade_sistema_snapshot, Decimal("10.000"))
        self.assertEqual(conferencia.quantidade_observada, Decimal("8.000"))
        self.assertEqual(conferencia.diferenca_snapshot, Decimal("-2.000"))
        self.assertEqual(conferencia.lote_codigo_snapshot, "CONF-01")
        self.assertEqual(conferencia.produto_nome_snapshot, "Produto conferido")
        self.assertEqual(len(conferencia.conteudo_sha256), 64)
        self.assertEqual(self.estoque.quantidade_atual, Decimal("10.000"))
        self.assertEqual(self.lote.quantidade_atual, Decimal("10.000"))
        self.assertFalse(MovimentacaoEstoque.objects.exists())
        self.assertFalse(PerdaEstoque.objects.exists())
        self.assertEqual(LogAuditoria.objects.filter(acao="CONFERENCIA_FISICA_VALIDADE_LOTE").count(), 1)

        conferencia.observacao = "Tentativa de alteração"
        with self.assertRaisesMessage(ValidationError, "imutável"):
            conferencia.save()
        with self.assertRaisesMessage(ValidationError, "imutável"):
            conferencia.delete()

    def test_divergencia_exige_observacao_e_snapshot_fica_invalido_se_saldo_mudar(self):
        with self.assertRaisesMessage(ValidationError, "Explique a divergência"):
            self.registrar("9.000", "")
        conferencia = self.registrar()
        self.assertEqual(conferencia_fisica_vigente_lote(self.lote), conferencia)

        LoteEstoque.objects.filter(pk=self.lote.pk).update(quantidade_atual=Decimal("9.000"))
        self.lote.refresh_from_db()
        self.assertIsNone(conferencia_fisica_vigente_lote(self.lote))

    def test_perda_exige_conferencia_atual_e_respeita_quantidade_observada(self):
        planejar_tratamento_validade_lote(
            lote=self.lote,
            status=StatusTratamentoValidade.DESCARTE_PLANEJADO,
            observacao="Descarte após conferência.",
            usuario=self.usuario,
        )
        with self.assertRaisesMessage(ValidationError, "conferência física válida hoje"):
            registrar_perda_lote_validade(
                lote=self.lote,
                quantidade=Decimal("1.000"),
                motivo="Vencimento",
                usuario=self.usuario,
                supervisor=self.usuario,
            )
        self.registrar("2.000", "Somente duas unidades localizadas.")
        with self.assertRaisesMessage(ValidationError, "quantidade observada"):
            registrar_perda_lote_validade(
                lote=self.lote,
                quantidade=Decimal("3.000"),
                motivo="Vencimento",
                usuario=self.usuario,
                supervisor=self.usuario,
            )
        perda = registrar_perda_lote_validade(
            lote=self.lote,
            quantidade=Decimal("2.000"),
            motivo="Vencimento confirmado",
            usuario=self.usuario,
            supervisor=self.usuario,
        )
        self.assertEqual(perda.quantidade, Decimal("2.000"))

    def test_tela_isola_empresa_e_registra_sem_movimentar(self):
        url = reverse("estoque:conferencia_fisica_validade_lote", args=[self.lote.pk])
        pagina = self.client.get(url)
        self.assertContains(pagina, "Registrar conferência sem ajuste")
        resposta = self.client.post(
            url,
            {
                "quantidade_observada": "10.000",
                "observacao": "Contagem visual e física.",
                "confirmar_dados": "on",
            },
        )
        self.assertRedirects(
            resposta,
            reverse("estoque:tratamento_validade_lote", args=[self.lote.pk]),
        )
        self.assertEqual(ConferenciaFisicaValidadeLote.objects.count(), 1)
        self.assertFalse(MovimentacaoEstoque.objects.exists())

        outra = Empresa.objects.create(
            razao_social="Outro Mercado",
            nome_fantasia="Outro Mercado",
            cnpj="99888777000166",
        )
        outra_filial = Filial.objects.create(empresa=outra, nome="Outra filial")
        externo = LoteEstoque.objects.create(
            produto=self.produto,
            filial=outra_filial,
            codigo="EXTERNO",
            validade=timezone.localdate(),
            quantidade_inicial=Decimal("1.000"),
            quantidade_atual=Decimal("1.000"),
            custo_unitario=Decimal("5.00"),
        )
        self.assertEqual(
            self.client.get(
                reverse("estoque:conferencia_fisica_validade_lote", args=[externo.pk])
            ).status_code,
            404,
        )
