from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import close_old_connections, connection
from django.test import TransactionTestCase

from apps.empresas.models import Empresa, Filial
from apps.estoque.models import FechamentoEstoqueContabil

from .models import FechamentoMensalSnapshot
from .services_fechamento_mensal import calcular_hash_snapshot, fechar_competencia


@skipUnless(
    connection.vendor == "postgresql",
    "Este teste exige PostgreSQL real; SQLite não comprova select_for_update.",
)
class FechamentoMensalConcorrenciaPostgreSQLTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.usuario = get_user_model().objects.create_superuser(
            "fechamento-concorrencia",
            "fechamento-concorrencia@example.com",
            "123",
        )
        self.empresa = Empresa.objects.create(
            razao_social="Mercado Fechamento Concorrente Ltda",
            nome_fantasia="Mercado Fechamento Concorrente",
            cnpj="48.888.888/0001-48",
        )
        self.filial = Filial.objects.create(
            empresa=self.empresa,
            nome="Matriz concorrência fechamento",
            cnpj=self.empresa.cnpj,
        )
        data_fim = date(2026, 8, 31)
        conteudo = {
            "filial_id": self.filial.pk,
            "data_referencia": data_fim.isoformat(),
            "criterio_custo": "CUSTO_MEDIO_PONDERADO_MOVEL",
            "itens": [],
        }
        FechamentoEstoqueContabil.objects.create(
            filial=self.filial,
            data_referencia=data_fim,
            criterio_custo="CUSTO_MEDIO_PONDERADO_MOVEL",
            total_itens=0,
            valor_total_custo=0,
            conteudo_sha256=calcular_hash_snapshot(conteudo),
            capturado_por=self.usuario,
        )

    def test_duas_conexoes_criam_somente_uma_versao_um(self):
        inicio_simultaneo = Barrier(3)

        def tentar_fechar():
            close_old_connections()
            try:
                empresa = Empresa.objects.get(pk=self.empresa.pk)
                usuario = get_user_model().objects.get(pk=self.usuario.pk)
                inicio_simultaneo.wait(timeout=10)
                snapshot = fechar_competencia(
                    empresa=empresa,
                    competencia=date(2026, 8, 1),
                    usuario=usuario,
                    confirmacao="Confirmo o fechamento da competência 08/2026",
                )
                return f"fechada:{snapshot.versao}"
            except ValidationError as exc:
                return f"rejeitada:{' '.join(exc.messages)}"
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            tentativas = [executor.submit(tentar_fechar) for _ in range(2)]
            inicio_simultaneo.wait(timeout=10)
            resultados = [tentativa.result(timeout=30) for tentativa in tentativas]

        self.assertEqual(resultados.count("fechada:1"), 1)
        rejeicoes = [item for item in resultados if item.startswith("rejeitada:")]
        self.assertEqual(len(rejeicoes), 1)
        self.assertTrue(
            "já está fechada" in rejeicoes[0]
            or "Outra tentativa já criou" in rejeicoes[0]
        )
        self.assertEqual(FechamentoMensalSnapshot.objects.count(), 1)
        self.assertEqual(FechamentoMensalSnapshot.objects.get().versao, 1)
