import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from .models import DocumentoFiscal, StatusDocumentoFiscal
from .services import (
    consultar_situacao_documento,
    preparar_documento_venda,
    transmitir_documento_sefaz,
)
from .test_concorrencia_preparacao import FiscalOriginFixtureMixin


class AdaptadorFalhaAposInicio:
    assina_xml = True
    valida_schema = True

    def transmitir(self, **kwargs):
        raise TimeoutError("resultado da transmissão desconhecido")

    def consultar(self, **kwargs):
        return {
            "status": "NAO_LOCALIZADO",
            "mensagem": "Documento ainda não localizado.",
        }


class AdaptadorNaoLocalizado:
    assina_xml = True
    valida_schema = True

    def transmitir(self, **kwargs):
        return {"status": "PENDENTE", "mensagem": "Aguardando processamento."}

    def consultar(self, **kwargs):
        return {
            "status": "NAO_LOCALIZADO",
            "mensagem": "Documento não localizado.",
        }


class AdaptadorTransmissaoBloqueada:
    assina_xml = True
    valida_schema = True
    entrou = Event()
    liberar = Event()
    lock = Lock()
    chamadas = 0

    @classmethod
    def reiniciar(cls):
        cls.entrou = Event()
        cls.liberar = Event()
        cls.chamadas = 0

    def transmitir(self, **kwargs):
        with type(self).lock:
            type(self).chamadas += 1
        type(self).entrou.set()
        if not type(self).liberar.wait(timeout=15):
            raise TimeoutError("teste não liberou o adaptador")
        return {
            "status": "AUTORIZADO",
            "chave_acesso": kwargs["documento"].chave_acesso,
            "protocolo": "135260000000901",
            "mensagem": "Autorizado o uso da NF-e.",
        }


class ReservaTransmissaoTests(FiscalOriginFixtureMixin, TestCase):
    def test_banco_exige_data_e_token_de_reserva_em_conjunto(self):
        documento = preparar_documento_venda(self.venda, self.usuario)

        with self.assertRaises(IntegrityError), transaction.atomic():
            DocumentoFiscal.objects.filter(pk=documento.pk).update(
                transmissao_reservada_em=timezone.now()
            )

    @override_settings(
        FISCAL_SEFAZ_ADAPTER="apps.fiscal.test_reserva_transmissao.AdaptadorFalhaAposInicio"
    )
    def test_falha_apos_inicio_exige_consulta_e_nao_retransmite(self):
        documento = preparar_documento_venda(self.venda, self.usuario)

        with self.assertRaisesMessage(ValidationError, "Falha na comunicacao"):
            transmitir_documento_sefaz(documento, self.usuario)

        documento.refresh_from_db()
        self.assertTrue(documento.aguardando_consulta_sefaz)
        self.assertIsNone(documento.transmissao_reservada_em)
        self.assertIsNone(documento.transmissao_reserva_token)
        with self.assertRaisesMessage(ValidationError, "Consulte a situação"):
            transmitir_documento_sefaz(documento, self.usuario)
        documento.refresh_from_db()
        self.assertEqual(documento.tentativas_transmissao, 1)

    @override_settings(
        FISCAL_SEFAZ_ADAPTER="apps.fiscal.test_reserva_transmissao.AdaptadorNaoLocalizado",
        FISCAL_CONTINGENCY_NOT_FOUND_CONFIRMATIONS=2,
    )
    def test_resultado_incerto_exige_duas_ausencias_antes_de_liberar_reenvio(self):
        documento = preparar_documento_venda(self.venda, self.usuario)
        documento.aguardando_consulta_sefaz = True
        documento.tentativas_transmissao = 1
        documento.save(
            update_fields=["aguardando_consulta_sefaz", "tentativas_transmissao"]
        )

        primeira, _ = consultar_situacao_documento(documento, self.usuario)
        self.assertTrue(primeira.aguardando_consulta_sefaz)
        self.assertEqual(primeira.confirmacoes_nao_localizado, 1)

        segunda, _ = consultar_situacao_documento(primeira, self.usuario)
        self.assertFalse(segunda.aguardando_consulta_sefaz)
        self.assertEqual(segunda.confirmacoes_nao_localizado, 2)
        self.assertEqual(segunda.tentativas_transmissao, 0)

    @override_settings(
        FISCAL_SEFAZ_ADAPTER="apps.fiscal.test_reserva_transmissao.AdaptadorTransmissaoBloqueada"
    )
    def test_chamada_manual_recusa_reserva_ativa_de_outro_processo(self):
        documento = preparar_documento_venda(self.venda, self.usuario)
        documento.transmissao_reservada_em = timezone.now()
        documento.transmissao_reserva_token = uuid.uuid4()
        documento.save(
            update_fields=["transmissao_reservada_em", "transmissao_reserva_token"]
        )

        with self.assertRaisesMessage(ValidationError, "reservado por outro processo"):
            transmitir_documento_sefaz(documento, self.usuario)


@skipUnless(connection.vendor == "postgresql", "Concorrência real exige PostgreSQL.")
class ReservaTransmissaoConcurrencyTests(FiscalOriginFixtureMixin, TransactionTestCase):
    reset_sequences = True

    @override_settings(
        FISCAL_SEFAZ_ADAPTER="apps.fiscal.test_reserva_transmissao.AdaptadorTransmissaoBloqueada"
    )
    def test_duas_transmissoes_simultaneas_fazem_um_unico_envio_externo(self):
        documento = preparar_documento_venda(self.venda, self.usuario)
        AdaptadorTransmissaoBloqueada.reiniciar()

        def transmitir():
            close_old_connections()
            try:
                doc = DocumentoFiscal.objects.get(pk=documento.pk)
                usuario = get_user_model().objects.get(pk=self.usuario.pk)
                resultado = transmitir_documento_sefaz(doc, usuario)
                return "autorizado", resultado.pk
            except ValidationError as exc:
                return "bloqueado", " ".join(exc.messages)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            primeira = executor.submit(transmitir)
            self.assertTrue(AdaptadorTransmissaoBloqueada.entrou.wait(timeout=15))
            segunda = executor.submit(transmitir)
            resultado_segunda = segunda.result(timeout=15)
            AdaptadorTransmissaoBloqueada.liberar.set()
            resultado_primeira = primeira.result(timeout=15)

        resultados = [resultado_primeira, resultado_segunda]
        self.assertEqual([r[0] for r in resultados].count("autorizado"), 1, resultados)
        self.assertEqual([r[0] for r in resultados].count("bloqueado"), 1, resultados)
        mensagem_bloqueio = next(r[1] for r in resultados if r[0] == "bloqueado")
        self.assertTrue(
            "reservado por outro processo" in mensagem_bloqueio
            or "Consulte a situação" in mensagem_bloqueio,
            mensagem_bloqueio,
        )
        documento.refresh_from_db()
        self.assertEqual(AdaptadorTransmissaoBloqueada.chamadas, 1)
        self.assertEqual(documento.status, StatusDocumentoFiscal.EMITIDO)
        self.assertEqual(documento.tentativas_transmissao, 1)
        self.assertIsNone(documento.transmissao_reserva_token)
        self.assertIsNone(documento.transmissao_reservada_em)
