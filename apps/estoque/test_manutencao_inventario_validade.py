from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from .models import (
    ExecucaoManutencaoInventarioValidade,
    StatusExecucaoManutencaoInventarioValidade,
)
from .services import (
    diagnostico_manutencao_inventarios_validade,
    executar_manutencao_inventarios_validade,
)


class ManutencaoInventarioValidadeTests(TestCase):
    def test_comando_registra_sucesso_mesmo_sem_inventario_e_pode_repetir(self):
        primeira_saida = StringIO()
        segunda_saida = StringIO()

        call_command(
            "expirar_inventarios_validade",
            confirmar_expiracao=True,
            stdout=primeira_saida,
        )
        call_command(
            "expirar_inventarios_validade",
            confirmar_expiracao=True,
            stdout=segunda_saida,
        )

        execucoes = ExecucaoManutencaoInventarioValidade.objects.order_by("iniciada_em")
        self.assertEqual(execucoes.count(), 2)
        self.assertTrue(
            all(
                item.status == StatusExecucaoManutencaoInventarioValidade.SUCESSO
                and item.expirados_total == 0
                for item in execucoes
            )
        )
        self.assertIn("Nenhum saldo foi alterado", primeira_saida.getvalue())
        self.assertIn("Nenhum saldo foi alterado", segunda_saida.getvalue())

    def test_falha_e_registrada_sem_expor_detalhes_da_excecao(self):
        segredo = "caminho-rede-e-segredo-nao-pode-vazar"
        with patch(
            "apps.estoque.services.expirar_inventarios_validade_vencidos",
            side_effect=RuntimeError(segredo),
        ):
            with self.assertRaises(RuntimeError):
                executar_manutencao_inventarios_validade()

        registro = ExecucaoManutencaoInventarioValidade.objects.get()
        self.assertEqual(registro.status, StatusExecucaoManutencaoInventarioValidade.FALHA)
        self.assertEqual(registro.erro_codigo, "RuntimeError")
        self.assertNotIn(segredo, registro.erro_resumo)
        self.assertEqual(registro.expirados_total, 0)

    def test_diagnostico_distingue_sem_execucao_falha_em_dia_e_atraso(self):
        self.assertEqual(
            diagnostico_manutencao_inventarios_validade()["estado"],
            "NAO_EXECUTADA",
        )
        momento = timezone.now()
        executar_manutencao_inventarios_validade(momento=momento)
        self.assertEqual(
            diagnostico_manutencao_inventarios_validade(momento=momento)["estado"],
            "EM_DIA",
        )
        self.assertEqual(
            diagnostico_manutencao_inventarios_validade(
                momento=momento + timedelta(hours=27)
            )["estado"],
            "ATRASADA",
        )

        ExecucaoManutencaoInventarioValidade.objects.create(
            status=StatusExecucaoManutencaoInventarioValidade.FALHA,
            iniciada_em=momento + timedelta(hours=28),
            finalizada_em=momento + timedelta(hours=28),
            erro_codigo="RuntimeError",
            erro_resumo="Falha sanitizada.",
            conteudo_sha256="f" * 64,
        )
        diagnostico = diagnostico_manutencao_inventarios_validade(
            momento=momento + timedelta(hours=28, minutes=1)
        )
        self.assertEqual(diagnostico["estado"], "FALHA")
        self.assertTrue(diagnostico["sem_dados_sensiveis"])

    def test_historico_nao_pode_ser_alterado_nem_excluido(self):
        _, registro = executar_manutencao_inventarios_validade()
        registro.erro_resumo = "Tentativa de mudança"
        with self.assertRaises(ValidationError):
            registro.save()
        with self.assertRaises(ValidationError):
            registro.delete()
