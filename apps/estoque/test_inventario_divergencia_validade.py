from io import StringIO
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import PerfilUsuario, TipoPerfil
from apps.auditoria.models import LogAuditoria
from apps.empresas.models import Empresa, Filial
from apps.produtos.models import Categoria, Produto

from .models import (
    ContagemLoteInventarioValidade,
    EscopoLoteInventarioValidade,
    Estoque,
    InventarioEstoque,
    LoteEstoque,
    MovimentacaoEstoque,
    MovimentacaoLoteEstoque,
    OrigemInventario,
    OrigemItemInventarioValidade,
    RetificacaoCapacidadeLoteEstoque,
    StatusInventario,
)
from .services import (
    aplicar_inventario,
    cancelar_inventario,
    criar_inventario_divergencias_validade,
    expirar_inventarios_validade_vencidos,
    registrar_conferencia_fisica_validade_lote,
    registrar_contagem_lote_inventario_validade,
)


class InventarioDivergenciaValidadeTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(
            razao_social="Mercado Inventário Validade",
            nome_fantasia="Mercado Inventário Validade",
            cnpj="22333444000177",
        )
        self.filial = Filial.objects.create(empresa=self.empresa, nome="Matriz")
        self.usuario = get_user_model().objects.create_user("estoquista_inventario_validade", password="senha")
        PerfilUsuario.objects.create(
            usuario=self.usuario,
            filial=self.filial,
            tipo=TipoPerfil.ESTOQUISTA,
        )
        self.supervisor = get_user_model().objects.create_user(
            "gerente_inventario_validade", password="senha-gerente"
        )
        PerfilUsuario.objects.create(
            usuario=self.supervisor,
            filial=self.filial,
            tipo=TipoPerfil.GERENTE,
        )
        self.categoria = Categoria.objects.create(nome="Inventário por validade")
        self.produto = self.criar_produto("7891000055553", "Produto divergente")
        self.estoque = Estoque.objects.create(
            produto=self.produto,
            filial=self.filial,
            quantidade_atual=Decimal("10.000"),
        )
        self.client.force_login(self.usuario)

    def criar_produto(self, codigo, nome):
        return Produto.objects.create(
            codigo_barras=codigo,
            nome=nome,
            categoria=self.categoria,
            preco_custo=Decimal("5.00"),
            preco_venda=Decimal("9.00"),
        )

    def criar_lote(self, codigo, quantidade, produto=None, filial=None):
        return LoteEstoque.objects.create(
            produto=produto or self.produto,
            filial=filial or self.filial,
            codigo=codigo,
            validade=timezone.localdate() + timedelta(days=3),
            quantidade_inicial=Decimal(quantidade),
            quantidade_atual=Decimal(quantidade),
            custo_unitario=Decimal("5.00"),
        )

    def conferir(self, lote, observada, observacao="Divergência conferida."):
        return registrar_conferencia_fisica_validade_lote(
            lote=lote,
            quantidade_observada=Decimal(observada),
            observacao=observacao,
            confirmar_dados=True,
            usuario=self.usuario,
        )

    def test_cria_rascunho_deduplica_produto_e_nao_aplica_ajuste(self):
        lote_a = self.criar_lote("DIV-A", "4.000")
        lote_b = self.criar_lote("DIV-B", "6.000")
        self.conferir(lote_a, "3.000")
        self.conferir(lote_b, "5.000")

        inventario, criado = criar_inventario_divergencias_validade(
            filial=self.filial,
            lotes=[lote_a, lote_b],
            usuario=self.usuario,
        )

        self.assertTrue(criado)
        self.assertEqual(inventario.origem, OrigemInventario.DIVERGENCIA_VALIDADE)
        self.assertEqual(inventario.status, StatusInventario.ABERTO)
        self.assertEqual(len(inventario.chave_origem), 64)
        item = inventario.itens.get()
        self.assertEqual(item.produto, self.produto)
        self.assertEqual(item.quantidade_sistema, Decimal("10.000"))
        self.assertIsNone(item.quantidade_contada)
        self.assertIn("DIV-A", item.observacao)
        self.assertIn("DIV-B", item.observacao)
        origens = list(item.origens_validade.select_related("conferencia", "lote"))
        self.assertEqual(len(origens), 2)
        self.assertEqual({origem.lote.codigo for origem in origens}, {"DIV-A", "DIV-B"})
        self.assertEqual(
            {origem.conferencia_id for origem in origens},
            set(lote_a.conferencias_validade.values_list("id", flat=True))
            | set(lote_b.conferencias_validade.values_list("id", flat=True)),
        )
        origem = origens[0]
        with self.assertRaisesMessage(ValidationError, "imutável"):
            origem.save()
        with self.assertRaisesMessage(ValidationError, "imutável"):
            origem.delete()
        self.assertFalse(MovimentacaoEstoque.objects.exists())
        with self.assertRaisesMessage(ValidationError, "sem contagem física"):
            aplicar_inventario(inventario=inventario, usuario=self.usuario)
        self.estoque.refresh_from_db()
        self.assertEqual(self.estoque.quantidade_atual, Decimal("10.000"))
        item.quantidade_contada = Decimal("8.000")
        item.save(update_fields=["quantidade_contada"])
        with self.assertRaisesMessage(ValidationError, "precisam de contagem física específica"):
            aplicar_inventario(
                inventario=inventario,
                usuario=self.usuario,
                supervisor=self.usuario,
            )
        self.assertFalse(MovimentacaoEstoque.objects.exists())
        self.assertTrue(
            LogAuditoria.objects.filter(
                acao="PLANO_INVENTARIO_DIVERGENCIA_VALIDADE",
                objeto_id=str(inventario.pk),
            ).exists()
        )

        repetido, criado_novamente = criar_inventario_divergencias_validade(
            filial=self.filial,
            lotes=[lote_b, lote_a],
            usuario=self.usuario,
        )
        self.assertFalse(criado_novamente)
        self.assertEqual(repetido.pk, inventario.pk)
        self.assertEqual(InventarioEstoque.objects.count(), 1)
        self.assertEqual(OrigemItemInventarioValidade.objects.count(), 2)
        self.assertEqual(EscopoLoteInventarioValidade.objects.count(), 2)

    def test_recusa_conferencia_pronta_desatualizada_e_multifilial(self):
        pronto = self.criar_lote("PRONTO", "2.000")
        self.conferir(pronto, "2.000", "Contagem sem divergência.")
        with self.assertRaisesMessage(ValidationError, "conferência divergente"):
            criar_inventario_divergencias_validade(
                filial=self.filial,
                lotes=[pronto],
                usuario=self.usuario,
            )

        desatualizado = self.criar_lote("OLD", "2.000")
        self.conferir(desatualizado, "1.000")
        LoteEstoque.objects.filter(pk=desatualizado.pk).update(quantidade_atual=Decimal("1.000"))
        desatualizado.refresh_from_db()
        with self.assertRaisesMessage(ValidationError, "conferência divergente"):
            criar_inventario_divergencias_validade(
                filial=self.filial,
                lotes=[desatualizado],
                usuario=self.usuario,
            )

        outra_filial = Filial.objects.create(empresa=self.empresa, nome="Filial 2")
        outro_lote = self.criar_lote("OUTRA-FILIAL", "1.000", filial=outra_filial)
        self.conferir(outro_lote, "0.000")
        with self.assertRaisesMessage(ValidationError, "fora da filial"):
            criar_inventario_divergencias_validade(
                filial=self.filial,
                lotes=[outro_lote],
                usuario=self.usuario,
            )
        self.assertFalse(InventarioEstoque.objects.exists())

    def test_tela_seleciona_divergencia_e_cria_inventario_pendente(self):
        lote = self.criar_lote("TELA-DIV", "10.000")
        self.conferir(lote, "9.000")
        fila = self.client.get(reverse("estoque:lotes"), {"situacao": "FILA_VALIDADE"})
        self.assertContains(fila, "Criar inventário em rascunho")
        self.assertContains(fila, f'value="{lote.pk}"')

        resposta = self.client.post(
            reverse("estoque:criar_inventario_divergencias_validade"),
            {
                "lotes_divergentes": [str(lote.pk)],
                "descricao": "Recontagem dirigida pela validade",
            },
        )
        inventario = InventarioEstoque.objects.get()
        self.assertRedirects(
            resposta,
            reverse("estoque:inventario_detalhe", args=[inventario.pk]),
        )
        self.assertEqual(inventario.descricao, "Recontagem dirigida pela validade")
        detalhe = self.client.get(reverse("estoque:inventario_detalhe", args=[inventario.pk]))
        self.assertContains(detalhe, "Divergência de validade")
        self.assertContains(detalhe, "Reconciliação por lote ainda protegida")
        self.assertContains(detalhe, "Lote TELA-DIV")
        conferencia = lote.conferencias_validade.get()
        self.assertContains(
            detalhe,
            reverse("estoque:conferencia_fisica_validade_detalhe", args=[conferencia.pk]),
        )
        evidencia = self.client.get(
            reverse("estoque:conferencia_fisica_validade_detalhe", args=[conferencia.pk])
        )
        self.assertContains(evidencia, conferencia.conteudo_sha256)
        self.assertContains(evidencia, f"Inventário {inventario.pk}")
        self.assertFalse(MovimentacaoEstoque.objects.exists())

    def test_post_recusa_lote_fora_do_escopo_e_item_nao_divergente(self):
        pronto = self.criar_lote("SEM-DIV", "10.000")
        self.conferir(pronto, "10.000", "Sem divergência.")
        resposta = self.client.post(
            reverse("estoque:criar_inventario_divergencias_validade"),
            {"lotes_divergentes": [str(pronto.pk)]},
        )
        self.assertRedirects(resposta, reverse("estoque:lotes"))
        self.assertFalse(InventarioEstoque.objects.exists())

        outra_empresa = Empresa.objects.create(
            razao_social="Outro Mercado",
            nome_fantasia="Outro Mercado",
            cnpj="88777666000155",
        )
        outra_filial = Filial.objects.create(empresa=outra_empresa, nome="Outra filial")
        externo = self.criar_lote("EXTERNO", "1.000", filial=outra_filial)
        self.conferir(externo, "0.000")
        resposta = self.client.post(
            reverse("estoque:criar_inventario_divergencias_validade"),
            {"lotes_divergentes": [str(externo.pk)]},
        )
        self.assertRedirects(resposta, reverse("estoque:lotes"))
        self.assertFalse(InventarioEstoque.objects.exists())

    def test_detalhe_da_evidencia_respeita_escopo_da_empresa(self):
        proprio = self.criar_lote("EVID-PROPRIA", "10.000")
        conferencia_propria = self.conferir(proprio, "9.000")
        resposta = self.client.get(
            reverse(
                "estoque:conferencia_fisica_validade_detalhe",
                args=[conferencia_propria.pk],
            )
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Evidência da conferência")

        outra_empresa = Empresa.objects.create(
            razao_social="Empresa da evidência externa",
            nome_fantasia="Empresa externa",
            cnpj="44333222000111",
        )
        outra_filial = Filial.objects.create(empresa=outra_empresa, nome="Filial externa")
        lote_externo = self.criar_lote("EVID-EXTERNA", "1.000", filial=outra_filial)
        conferencia_externa = self.conferir(lote_externo, "0.000")
        resposta = self.client.get(
            reverse(
                "estoque:conferencia_fisica_validade_detalhe",
                args=[conferencia_externa.pk],
            )
        )
        self.assertEqual(resposta.status_code, 404)


    def contar_lote(self, escopo, quantidade, observacao="Contagem dirigida."):
        return registrar_contagem_lote_inventario_validade(
            escopo=escopo,
            quantidade_contada=Decimal(quantidade),
            observacao=observacao,
            confirmar_dados=True,
            usuario=self.usuario,
        )

    def test_contagem_por_lote_e_imutavel_e_recontagem_preserva_historico(self):
        lote = self.criar_lote("CONTAGEM-HIST", "10.000")
        self.conferir(lote, "9.000")
        inventario, _ = criar_inventario_divergencias_validade(
            filial=self.filial, lotes=[lote], usuario=self.usuario
        )
        escopo = inventario.itens.get().escopos_validade.get()

        primeira = self.contar_lote(escopo, "9.000")
        segunda = self.contar_lote(escopo, "8.500", "Recontagem confirmada.")

        self.assertEqual(escopo.contagens.count(), 2)
        self.assertEqual(escopo.contagens.first(), segunda)
        self.assertEqual(primeira.quantidade_sistema_snapshot, Decimal("10.000"))
        self.assertEqual(len(primeira.conteudo_sha256), 64)
        with self.assertRaisesMessage(ValidationError, "imutável"):
            primeira.save()
        with self.assertRaisesMessage(ValidationError, "imutável"):
            primeira.delete()
        self.assertFalse(MovimentacaoEstoque.objects.exists())

    def test_aplica_atomicamente_nos_lotes_exatos_quando_somas_conferem(self):
        lote_a = self.criar_lote("APLICA-A", "4.000")
        lote_b = self.criar_lote("APLICA-B", "6.000")
        self.conferir(lote_a, "3.000")
        self.conferir(lote_b, "5.000")
        inventario, _ = criar_inventario_divergencias_validade(
            filial=self.filial, lotes=[lote_a, lote_b], usuario=self.usuario
        )
        item = inventario.itens.get()
        escopos = {escopo.lote_id: escopo for escopo in item.escopos_validade.all()}
        self.contar_lote(escopos[lote_a.pk], "3.000")
        self.contar_lote(escopos[lote_b.pk], "5.000")
        item.quantidade_contada = Decimal("8.000")
        item.save(update_fields=["quantidade_contada"])

        aplicar_inventario(
            inventario=inventario,
            usuario=self.usuario,
            supervisor=self.usuario,
        )

        inventario.refresh_from_db()
        item.refresh_from_db()
        lote_a.refresh_from_db()
        lote_b.refresh_from_db()
        self.estoque.refresh_from_db()
        self.assertEqual(inventario.status, StatusInventario.APLICADO)
        self.assertEqual(item.diferenca, Decimal("-2.000"))
        self.assertEqual(lote_a.quantidade_atual, Decimal("3.000"))
        self.assertEqual(lote_b.quantidade_atual, Decimal("5.000"))
        self.assertEqual(self.estoque.quantidade_atual, Decimal("8.000"))
        self.assertEqual(
            set(MovimentacaoEstoque.objects.values_list("quantidade", flat=True)),
            {Decimal("-1.000")},
        )
        self.assertEqual(MovimentacaoEstoque.objects.count(), 2)
        self.assertEqual(MovimentacaoLoteEstoque.objects.count(), 2)
        self.assertTrue(
            LogAuditoria.objects.filter(
                acao="APLICACAO_INVENTARIO_VALIDADE_POR_LOTE",
                objeto_id=str(inventario.pk),
            ).exists()
        )

    def test_soma_divergente_bloqueia_toda_a_transacao(self):
        lote_a = self.criar_lote("SOMA-A", "4.000")
        lote_b = self.criar_lote("SOMA-B", "6.000")
        self.conferir(lote_a, "3.000")
        self.conferir(lote_b, "5.000")
        inventario, _ = criar_inventario_divergencias_validade(
            filial=self.filial, lotes=[lote_a, lote_b], usuario=self.usuario
        )
        item = inventario.itens.get()
        escopos = {escopo.lote_id: escopo for escopo in item.escopos_validade.all()}
        self.contar_lote(escopos[lote_a.pk], "3.000")
        self.contar_lote(escopos[lote_b.pk], "5.000")
        item.quantidade_contada = Decimal("7.000")
        item.save(update_fields=["quantidade_contada"])

        with self.assertRaisesMessage(ValidationError, "não corresponde à contagem total"):
            aplicar_inventario(
                inventario=inventario,
                usuario=self.usuario,
                supervisor=self.usuario,
            )

        lote_a.refresh_from_db()
        lote_b.refresh_from_db()
        self.estoque.refresh_from_db()
        inventario.refresh_from_db()
        self.assertEqual(lote_a.quantidade_atual, Decimal("4.000"))
        self.assertEqual(lote_b.quantidade_atual, Decimal("6.000"))
        self.assertEqual(self.estoque.quantidade_atual, Decimal("10.000"))
        self.assertEqual(inventario.status, StatusInventario.ABERTO)
        self.assertFalse(MovimentacaoEstoque.objects.exists())

    def test_saldo_alterado_apos_contagem_exige_nova_contagem_e_reverte_tudo(self):
        lote_a = self.criar_lote("STALE-A", "4.000")
        lote_b = self.criar_lote("STALE-B", "6.000")
        self.conferir(lote_a, "3.000")
        self.conferir(lote_b, "5.000")
        inventario, _ = criar_inventario_divergencias_validade(
            filial=self.filial, lotes=[lote_a, lote_b], usuario=self.usuario
        )
        item = inventario.itens.get()
        escopos = {escopo.lote_id: escopo for escopo in item.escopos_validade.all()}
        self.contar_lote(escopos[lote_a.pk], "3.000")
        self.contar_lote(escopos[lote_b.pk], "5.000")
        item.quantidade_contada = Decimal("8.000")
        item.save(update_fields=["quantidade_contada"])
        LoteEstoque.objects.filter(pk=lote_b.pk).update(quantidade_atual=Decimal("5.500"))
        Estoque.objects.filter(pk=self.estoque.pk).update(quantidade_atual=Decimal("9.500"))

        with self.assertRaisesMessage(ValidationError, "mudou após a contagem"):
            aplicar_inventario(
                inventario=inventario,
                usuario=self.usuario,
                supervisor=self.usuario,
            )

        lote_a.refresh_from_db()
        lote_b.refresh_from_db()
        inventario.refresh_from_db()
        self.assertEqual(lote_a.quantidade_atual, Decimal("4.000"))
        self.assertEqual(lote_b.quantidade_atual, Decimal("5.500"))
        self.assertEqual(inventario.status, StatusInventario.ABERTO)
        self.assertFalse(MovimentacaoEstoque.objects.exists())

    def test_lote_complementar_entra_no_escopo_e_permite_fechar_total(self):
        selecionado = self.criar_lote("ESCOPO-A", "4.000")
        complementar = self.criar_lote("ESCOPO-B", "6.000")
        self.conferir(selecionado, "3.000")
        inventario, _ = criar_inventario_divergencias_validade(
            filial=self.filial, lotes=[selecionado], usuario=self.usuario
        )
        item = inventario.itens.get()
        escopos = {escopo.lote_id: escopo for escopo in item.escopos_validade.all()}
        self.assertEqual(set(escopos), {selecionado.pk, complementar.pk})
        self.assertIsNotNone(escopos[selecionado.pk].origem)
        self.assertIsNone(escopos[complementar.pk].origem)

        self.contar_lote(escopos[selecionado.pk], "3.000")
        self.contar_lote(escopos[complementar.pk], "6.000")
        item.quantidade_contada = Decimal("9.000")
        item.save(update_fields=["quantidade_contada"])
        aplicar_inventario(
            inventario=inventario,
            usuario=self.usuario,
            supervisor=self.usuario,
        )

        selecionado.refresh_from_db()
        complementar.refresh_from_db()
        self.estoque.refresh_from_db()
        self.assertEqual(selecionado.quantidade_atual, Decimal("3.000"))
        self.assertEqual(complementar.quantidade_atual, Decimal("6.000"))
        self.assertEqual(self.estoque.quantidade_atual, Decimal("9.000"))

    def test_lote_novo_apos_abertura_fica_fora_do_escopo_e_bloqueia(self):
        selecionado = self.criar_lote("NOVO-A", "4.000")
        self.conferir(selecionado, "3.000")
        Estoque.objects.filter(pk=self.estoque.pk).update(quantidade_atual=Decimal("4.000"))
        inventario, _ = criar_inventario_divergencias_validade(
            filial=self.filial, lotes=[selecionado], usuario=self.usuario
        )
        item = inventario.itens.get()
        escopo = item.escopos_validade.get()
        self.contar_lote(escopo, "3.000")
        item.quantidade_contada = Decimal("3.000")
        item.save(update_fields=["quantidade_contada"])

        self.criar_lote("NOVO-B", "1.000")
        Estoque.objects.filter(pk=self.estoque.pk).update(quantidade_atual=Decimal("5.000"))
        with self.assertRaisesMessage(ValidationError, "lotes novos fora do escopo"):
            aplicar_inventario(
                inventario=inventario,
                usuario=self.usuario,
                supervisor=self.usuario,
            )
        self.assertFalse(MovimentacaoEstoque.objects.exists())
    def test_sobra_acima_da_capacidade_exige_justificativa(self):
        lote = self.criar_lote("SOBRA-JUST", "10.000")
        self.conferir(lote, "9.000")
        inventario, _ = criar_inventario_divergencias_validade(
            filial=self.filial, lotes=[lote], usuario=self.usuario
        )
        escopo = inventario.itens.get().escopos_validade.get()

        with self.assertRaisesMessage(ValidationError, "Justifique a sobra física"):
            self.contar_lote(escopo, "11.000", observacao="")
        self.assertFalse(ContagemLoteInventarioValidade.objects.exists())
        self.assertFalse(RetificacaoCapacidadeLoteEstoque.objects.exists())

    def test_sobra_autorizada_preserva_inicial_e_cria_retificacao_imutavel(self):
        lote = self.criar_lote("SOBRA-OK", "10.000")
        self.conferir(lote, "9.000")
        inventario, _ = criar_inventario_divergencias_validade(
            filial=self.filial, lotes=[lote], usuario=self.usuario
        )
        item = inventario.itens.get()
        escopo = item.escopos_validade.get()
        self.contar_lote(
            escopo,
            "11.000",
            "Mercadoria física localizada no fundo da área de armazenagem.",
        )
        item.quantidade_contada = Decimal("11.000")
        item.save(update_fields=["quantidade_contada"])

        aplicar_inventario(
            inventario=inventario,
            usuario=self.usuario,
            supervisor=self.usuario,
        )

        lote.refresh_from_db()
        self.estoque.refresh_from_db()
        retificacao = RetificacaoCapacidadeLoteEstoque.objects.get()
        self.assertEqual(lote.quantidade_inicial, Decimal("10.000"))
        self.assertEqual(lote.quantidade_acrescimos_auditados, Decimal("1.000"))
        self.assertEqual(lote.quantidade_maxima_auditada, Decimal("11.000"))
        self.assertEqual(lote.quantidade_atual, Decimal("11.000"))
        self.assertEqual(self.estoque.quantidade_atual, Decimal("11.000"))
        self.assertEqual(retificacao.acrescimo_autorizado, Decimal("1.000"))
        self.assertEqual(retificacao.nova_capacidade, Decimal("11.000"))
        self.assertEqual(retificacao.quantidade_contada, Decimal("11.000"))
        self.assertEqual(retificacao.autorizado_por, self.usuario)
        self.assertEqual(len(retificacao.conteudo_sha256), 64)
        self.assertEqual(MovimentacaoEstoque.objects.get().quantidade, Decimal("1.000"))
        with self.assertRaisesMessage(ValidationError, "imutável"):
            retificacao.save()
        with self.assertRaisesMessage(ValidationError, "imutável"):
            retificacao.delete()
        self.assertTrue(
            LogAuditoria.objects.filter(
                acao="RETIFICACAO_CAPACIDADE_LOTE",
                objeto_id=str(retificacao.pk),
            ).exists()
        )

    def test_retificacao_e_revertida_se_outro_lote_ficar_desatualizado(self):
        lote_a = self.criar_lote("SOBRA-ROLLBACK-A", "4.000")
        lote_b = self.criar_lote("SOBRA-ROLLBACK-B", "6.000")
        self.conferir(lote_a, "3.000")
        self.conferir(lote_b, "5.000")
        inventario, _ = criar_inventario_divergencias_validade(
            filial=self.filial, lotes=[lote_a, lote_b], usuario=self.usuario
        )
        item = inventario.itens.get()
        escopos = {escopo.lote_id: escopo for escopo in item.escopos_validade.all()}
        self.contar_lote(escopos[lote_a.pk], "5.000", "Uma unidade localizada após a primeira contagem.")
        self.contar_lote(escopos[lote_b.pk], "5.000")
        item.quantidade_contada = Decimal("10.000")
        item.save(update_fields=["quantidade_contada"])
        LoteEstoque.objects.filter(pk=lote_b.pk).update(quantidade_atual=Decimal("5.500"))
        Estoque.objects.filter(pk=self.estoque.pk).update(quantidade_atual=Decimal("9.500"))

        with self.assertRaisesMessage(ValidationError, "mudou após a contagem"):
            aplicar_inventario(
                inventario=inventario,
                usuario=self.usuario,
                supervisor=self.usuario,
            )

        lote_a.refresh_from_db()
        inventario.refresh_from_db()
        self.assertEqual(lote_a.quantidade_atual, Decimal("4.000"))
        self.assertEqual(lote_a.quantidade_acrescimos_auditados, Decimal("0.000"))
        self.assertEqual(inventario.status, StatusInventario.ABERTO)
        self.assertFalse(RetificacaoCapacidadeLoteEstoque.objects.exists())
        self.assertFalse(MovimentacaoEstoque.objects.exists())
        self.assertFalse(LogAuditoria.objects.filter(acao="RETIFICACAO_CAPACIDADE_LOTE").exists())
    def test_rascunho_de_validade_recebe_prazo_de_vinte_quatro_horas(self):
        lote = self.criar_lote("PRAZO-24H", "10.000")
        self.conferir(lote, "9.000")
        antes = timezone.now()
        inventario, _ = criar_inventario_divergencias_validade(
            filial=self.filial, lotes=[lote], usuario=self.usuario
        )
        depois = timezone.now()

        self.assertGreaterEqual(inventario.expira_em, antes + timedelta(hours=24))
        self.assertLessEqual(inventario.expira_em, depois + timedelta(hours=24))
        self.assertEqual(inventario.chave_origem_base, inventario.chave_origem)
        self.assertFalse(inventario.prazo_operacional_expirado)

    def test_cancelamento_preserva_evidencias_e_permite_nova_tentativa(self):
        lote = self.criar_lote("CANCELA-PRESERVA", "10.000")
        self.conferir(lote, "9.000")
        inventario, _ = criar_inventario_divergencias_validade(
            filial=self.filial, lotes=[lote], usuario=self.usuario
        )
        item = inventario.itens.get()
        escopo = item.escopos_validade.get()
        self.contar_lote(escopo, "9.000")
        chave_base = inventario.chave_origem_base

        cancelar_inventario(
            inventario=inventario,
            usuario=self.usuario,
            supervisor=self.supervisor,
            motivo="Contagem interrompida para troca da equipe responsável.",
        )

        inventario.refresh_from_db()
        self.assertEqual(inventario.status, StatusInventario.CANCELADO)
        self.assertEqual(inventario.encerrado_por, self.supervisor)
        self.assertIsNotNone(inventario.encerrado_em)
        self.assertIn("troca da equipe", inventario.motivo_encerramento)
        self.assertEqual(inventario.itens.count(), 1)
        self.assertEqual(item.origens_validade.count(), 1)
        self.assertEqual(escopo.contagens.count(), 1)
        self.assertFalse(MovimentacaoEstoque.objects.exists())
        self.assertTrue(
            LogAuditoria.objects.filter(
                acao="CANCELAMENTO_INVENTARIO",
                objeto_id=str(inventario.pk),
            ).exists()
        )

        novo, criado = criar_inventario_divergencias_validade(
            filial=self.filial, lotes=[lote], usuario=self.usuario
        )
        repetido, criado_repetido = criar_inventario_divergencias_validade(
            filial=self.filial, lotes=[lote], usuario=self.usuario
        )
        self.assertTrue(criado)
        self.assertNotEqual(novo.pk, inventario.pk)
        self.assertEqual(novo.chave_origem_base, chave_base)
        self.assertNotEqual(novo.chave_origem, inventario.chave_origem)
        self.assertFalse(criado_repetido)
        self.assertEqual(repetido.pk, novo.pk)

    def test_tela_cancela_com_supervisor_e_mantem_historico_somente_leitura(self):
        lote = self.criar_lote("TELA-CANCELA", "10.000")
        self.conferir(lote, "9.000")
        inventario, _ = criar_inventario_divergencias_validade(
            filial=self.filial, lotes=[lote], usuario=self.usuario
        )
        resposta = self.client.post(
            reverse("estoque:inventario_cancelar", args=[inventario.pk]),
            {
                "motivo_cancelamento": "Área isolada e contagem reiniciada em outro turno.",
                "supervisor_usuario": self.supervisor.username,
                "supervisor_senha": "senha-gerente",
            },
        )
        self.assertRedirects(
            resposta,
            reverse("estoque:inventario_detalhe", args=[inventario.pk]),
        )
        inventario.refresh_from_db()
        self.assertEqual(inventario.status, StatusInventario.CANCELADO)
        detalhe = self.client.get(
            reverse("estoque:inventario_detalhe", args=[inventario.pk])
        )
        self.assertContains(detalhe, "Cancelado sem ajuste de estoque")
        self.assertContains(detalhe, "Área isolada")
        self.assertNotContains(detalhe, "Aplicar por lote")
        self.assertNotContains(detalhe, "Contar lote")
        self.assertFalse(MovimentacaoEstoque.objects.exists())

    def test_prazo_vencido_bloqueia_mutacoes_antes_da_rotina(self):
        lote = self.criar_lote("PRAZO-BLOQUEIA", "10.000")
        self.conferir(lote, "9.000")
        inventario, _ = criar_inventario_divergencias_validade(
            filial=self.filial, lotes=[lote], usuario=self.usuario
        )
        InventarioEstoque.objects.filter(pk=inventario.pk).update(
            expira_em=timezone.now() - timedelta(minutes=1)
        )
        inventario.refresh_from_db()
        escopo = inventario.itens.get().escopos_validade.get()

        with self.assertRaisesMessage(ValidationError, "prazo operacional"):
            self.contar_lote(escopo, "9.000")
        with self.assertRaisesMessage(ValidationError, "prazo operacional"):
            aplicar_inventario(
                inventario=inventario,
                usuario=self.usuario,
                supervisor=self.supervisor,
            )
        detalhe = self.client.get(
            reverse("estoque:inventario_detalhe", args=[inventario.pk])
        )
        self.assertContains(detalhe, "Prazo operacional expirado")
        self.assertNotContains(detalhe, "Aplicar por lote")
        self.assertNotContains(detalhe, "Contar lote")
        self.assertEqual(inventario.status, StatusInventario.ABERTO)
        self.assertFalse(MovimentacaoEstoque.objects.exists())

    def test_rotina_expira_somente_validade_e_preserva_toda_a_trilha(self):
        lote = self.criar_lote("EXPIRA-TRILHA", "10.000")
        self.conferir(lote, "9.000")
        inventario, _ = criar_inventario_divergencias_validade(
            filial=self.filial, lotes=[lote], usuario=self.usuario
        )
        escopo = inventario.itens.get().escopos_validade.get()
        self.contar_lote(escopo, "9.000")
        momento = timezone.now()
        InventarioEstoque.objects.filter(pk=inventario.pk).update(
            expira_em=momento - timedelta(minutes=1)
        )
        manual = InventarioEstoque.objects.create(
            filial=self.filial,
            usuario=self.usuario,
            descricao="Manual sem expiração automática",
            origem=OrigemInventario.MANUAL,
            expira_em=momento - timedelta(minutes=1),
        )

        expirados = expirar_inventarios_validade_vencidos(momento=momento)

        inventario.refresh_from_db()
        manual.refresh_from_db()
        self.assertEqual([obj.pk for obj in expirados], [inventario.pk])
        self.assertEqual(inventario.status, StatusInventario.EXPIRADO)
        self.assertEqual(manual.status, StatusInventario.ABERTO)
        self.assertIsNotNone(inventario.encerrado_em)
        self.assertIsNone(inventario.encerrado_por)
        self.assertEqual(inventario.itens.get().escopos_validade.count(), 1)
        self.assertEqual(ContagemLoteInventarioValidade.objects.count(), 1)
        self.assertFalse(MovimentacaoEstoque.objects.exists())
        self.assertTrue(
            LogAuditoria.objects.filter(
                acao="EXPIRACAO_INVENTARIO_VALIDADE",
                objeto_id=str(inventario.pk),
            ).exists()
        )

    def test_comando_exige_confirmacao_e_materializa_expiracao(self):
        lote = self.criar_lote("EXPIRA-COMANDO", "10.000")
        self.conferir(lote, "9.000")
        inventario, _ = criar_inventario_divergencias_validade(
            filial=self.filial, lotes=[lote], usuario=self.usuario
        )
        InventarioEstoque.objects.filter(pk=inventario.pk).update(
            expira_em=timezone.now() - timedelta(minutes=1)
        )
        with self.assertRaises(CommandError):
            call_command("expirar_inventarios_validade")

        saida = StringIO()
        call_command(
            "expirar_inventarios_validade",
            confirmar_expiracao=True,
            stdout=saida,
        )
        inventario.refresh_from_db()
        self.assertEqual(inventario.status, StatusInventario.EXPIRADO)
        self.assertIn("Nenhum saldo foi alterado", saida.getvalue())
    def test_tela_registra_contagem_do_lote_e_fecha_adicao_manual(self):
        lote = self.criar_lote("TELA-CONTAGEM", "10.000")
        self.conferir(lote, "9.000")
        inventario, _ = criar_inventario_divergencias_validade(
            filial=self.filial, lotes=[lote], usuario=self.usuario
        )
        item = inventario.itens.get()
        escopo = item.escopos_validade.get()
        detalhe = self.client.get(reverse("estoque:inventario_detalhe", args=[inventario.pk]))
        self.assertContains(detalhe, "Contar lote")
        self.assertNotContains(detalhe, "Adicionar produto")

        resposta = self.client.post(
            reverse("estoque:inventario_lote_contar", args=[escopo.pk]),
            {
                "quantidade_contada": "9.000",
                "observacao": "Conferido na área de venda",
                "confirmar_dados": "on",
            },
        )
        self.assertRedirects(
            resposta,
            reverse("estoque:inventario_detalhe", args=[inventario.pk]),
        )
        self.assertEqual(ContagemLoteInventarioValidade.objects.count(), 1)
        detalhe = self.client.get(reverse("estoque:inventario_detalhe", args=[inventario.pk]))
        self.assertContains(detalhe, "contado:")
        self.assertContains(detalhe, "<strong>9</strong>", html=True)

        resposta = self.client.get(
            reverse("estoque:inventario_item_novo", args=[inventario.pk])
        )
        self.assertRedirects(
            resposta,
            reverse("estoque:inventario_detalhe", args=[inventario.pk]),
        )
    def test_lista_exibe_diagnostico_da_manutencao_automatica(self):
        call_command("expirar_inventarios_validade", confirmar_expiracao=True)

        resposta = self.client.get(reverse("estoque:inventarios"))

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Manutenção automática de validade")
        self.assertContains(resposta, "Sucesso")