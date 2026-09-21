from datetime import date

from django.core.exceptions import ValidationError
from django.test import RequestFactory, SimpleTestCase, override_settings

from .views import _contrato_temporal_inventario, _periodo_competencia


class ContratoTemporalInventarioTests(SimpleTestCase):
    def test_competencia_em_andamento_nunca_e_fechamento_completo(self):
        contrato = _contrato_temporal_inventario(
            data_inicio=date(2026, 9, 1),
            data_fim=date(2026, 9, 30),
            hoje=date(2026, 9, 21),
            cobertura_completa=True,
        )

        self.assertEqual(contrato["estado_competencia"], "EM_ANDAMENTO")
        self.assertFalse(contrato["snapshot_completo"])
        self.assertEqual(
            contrato["qualidade_temporal"],
            "SNAPSHOT_IMUTAVEL_PARCIAL_COMPETENCIA",
        )

    def test_competencia_encerrada_exige_cobertura_completa_no_ultimo_dia(self):
        completo = _contrato_temporal_inventario(
            data_inicio=date(2026, 8, 1),
            data_fim=date(2026, 8, 31),
            hoje=date(2026, 9, 21),
            cobertura_completa=True,
        )
        incompleto = _contrato_temporal_inventario(
            data_inicio=date(2026, 8, 1),
            data_fim=date(2026, 8, 31),
            hoje=date(2026, 9, 21),
            cobertura_completa=False,
        )

        self.assertTrue(completo["snapshot_completo"])
        self.assertEqual(completo["qualidade_temporal"], "SNAPSHOT_IMUTAVEL_FECHAMENTO")
        self.assertFalse(incompleto["snapshot_completo"])
        self.assertEqual(incompleto["qualidade_temporal"], "POSICAO_ATUAL_NAO_RETROATIVA")

    @override_settings(USE_TZ=True)
    def test_competencia_futura_e_rejeitada(self):
        request = RequestFactory().get("/", {"competencia": "2999-01"})

        with self.assertRaisesMessage(ValidationError, "competência futura"):
            _periodo_competencia(request)
