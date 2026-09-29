import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from threading import Barrier, Event, Lock
from unittest import mock, skipUnless

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from apps.empresas.models import Filial
from apps.pdv.models import Caixa
from apps.vendas.models import FormaPagamento, ItemVenda, PagamentoVenda, Venda

from .fila import processar_fila_fiscal
from .models import (
    AmbienteFiscal,
    ConfiguracaoFiscal,
    DocumentoFiscal,
    EvidenciaFiscal,
    SerieFiscal,
    StatusDocumentoFiscal,
    TipoDocumentoFiscal,
    TipoEvidenciaFiscal,
)
from .services import (
    consultar_situacao_documento,
    preparar_documento_pedido_online,
    preparar_documento_venda,
    transmitir_documento_sefaz,
)
from .test_concorrencia_preparacao import FiscalOriginFixtureMixin
from .test_support_identidades_fiscais import obter_identidade_fiscal_teste


class AdaptadorMultiPdv:
    assina_xml = True
    valida_schema = True
    lock = Lock()
    dois_envios = Event()
    chamadas = {}
    chaves_idempotencia = {}

    @classmethod
    def reiniciar(cls):
        cls.dois_envios = Event()
        cls.chamadas = {}
        cls.chaves_idempotencia = {}

    def transmitir(self, **kwargs):
        documento_id = kwargs["documento"].pk
        with type(self).lock:
            type(self).chamadas[documento_id] = type(self).chamadas.get(documento_id, 0) + 1
            type(self).chaves_idempotencia.setdefault(documento_id, []).append(
                kwargs["idempotency_key"]
            )
            if len(type(self).chamadas) >= 2:
                type(self).dois_envios.set()
        if len(type(self).chamadas) < 2 and not type(self).dois_envios.wait(timeout=15):
            raise TimeoutError("o segundo worker não iniciou outro documento")
        return {
            "status": "AUTORIZADO",
            "chave_acesso": kwargs["documento"].chave_acesso,
            "protocolo": f"1352600{documento_id:08d}",
            "mensagem": "Autorizado no adaptador offline concorrente.",
            "xml_autorizado": kwargs["xml"],
        }


class AdaptadorManualFila:
    assina_xml = True
    valida_schema = True
    entrou = Event()
    liberar = Event()
    chamadas = 0

    @classmethod
    def reiniciar(cls):
        cls.entrou = Event()
        cls.liberar = Event()
        cls.chamadas = 0

    def transmitir(self, **kwargs):
        type(self).chamadas += 1
        type(self).entrou.set()
        if not type(self).liberar.wait(timeout=15):
            raise TimeoutError("o teste não liberou o envio")
        return {
            "status": "AUTORIZADO",
            "chave_acesso": kwargs["documento"].chave_acesso,
            "protocolo": "135260000001900",
            "mensagem": "Autorizado no adaptador offline.",
        }


class AdaptadorResultadoIncerto:
    assina_xml = True
    valida_schema = True
    transmissoes = 0
    consultas = 0
    chaves = []

    @classmethod
    def reiniciar(cls):
        cls.transmissoes = 0
        cls.consultas = 0
        cls.chaves = []

    def transmitir(self, **kwargs):
        type(self).transmissoes += 1
        type(self).chaves.append(kwargs["idempotency_key"])
        raise TimeoutError("resultado externo incerto")

    def consultar(self, **kwargs):
        type(self).consultas += 1
        return {"status": "NAO_LOCALIZADO", "mensagem": "Não localizado."}


class MultiPdvFixtureMixin(FiscalOriginFixtureMixin):
    def _criar_venda(self, *, filial=None, indice=1):
        filial = filial or self.filial
        caixa = Caixa.objects.create(
            filial=filial,
            usuario_abertura=self.usuario,
            valor_inicial=Decimal("50.00") + indice,
        )
        venda = Venda.objects.create(
            filial=filial,
            caixa=caixa,
            usuario=self.usuario,
            total_bruto=Decimal("30.00"),
            total_liquido=Decimal("30.00"),
            status="FINALIZADA",
        )
        ItemVenda.objects.create(
            venda=venda,
            produto=self.produto,
            quantidade=Decimal("1.000"),
            preco_unitario_venda=Decimal("30.00"),
            total=Decimal("30.00"),
            custo_unitario_no_momento=Decimal("10.00"),
        )
        forma = FormaPagamento.objects.filter(tipo="DINHEIRO").order_by("pk").first()
        PagamentoVenda.objects.create(venda=venda, forma_pagamento=forma, valor=Decimal("30.00"))
        return venda

    def _criar_segunda_filial(self):
        filial = Filial.objects.create(
            empresa=self.empresa,
            nome="Filial concorrente",
            cnpj=obter_identidade_fiscal_teste(
                "FILIAL", finalidade="TESTE_INTEGRACAO_LOCAL"
            ),
            logradouro="Rua Fiscal Dois",
            numero="200",
            bairro="Centro",
            cep="74000000",
            municipio="Goiania",
            uf="GO",
            codigo_municipio_ibge="5208707",
        )
        origem = ConfiguracaoFiscal.objects.get(filial=self.filial)
        ConfiguracaoFiscal.objects.create(
            filial=filial,
            ambiente=origem.ambiente,
            inscricao_estadual="987654321",
            regime_tributario=origem.regime_tributario,
            crt=origem.crt,
            csc_id=origem.csc_id,
            csc_token_criptografado=origem.csc_token_criptografado,
            url_qrcode_nfce=origem.url_qrcode_nfce,
            url_consulta_nfce=origem.url_consulta_nfce,
            certificado_a1_criptografado=origem.certificado_a1_criptografado,
            certificado_senha_criptografada=origem.certificado_senha_criptografada,
        )
        SerieFiscal.objects.create(
            filial=filial,
            tipo_documento=TipoDocumentoFiscal.NFCE,
            serie=1,
            proximo_numero=100,
        )
        return filial


class MultiPdvAtomicityTests(MultiPdvFixtureMixin, TestCase):
    def test_falha_na_geracao_reverte_documento_e_numero(self):
        with mock.patch(
            "apps.fiscal.services.salvar_xml_documento",
            side_effect=RuntimeError("falha controlada no XML"),
        ):
            with self.assertRaisesRegex(RuntimeError, "falha controlada"):
                preparar_documento_venda(self.venda, self.usuario)

        self.assertFalse(DocumentoFiscal.objects.filter(venda=self.venda).exists())
        serie = SerieFiscal.objects.get(
            filial=self.filial, tipo_documento=TipoDocumentoFiscal.NFCE
        )
        self.assertEqual(serie.proximo_numero, 100)

    def test_banco_impede_numero_duplicado(self):
        primeiro = preparar_documento_venda(self.venda, self.usuario)
        outra_venda = self._criar_venda(indice=2)

        with self.assertRaises(IntegrityError), transaction.atomic():
            DocumentoFiscal.objects.create(
                filial=self.filial,
                venda=outra_venda,
                tipo_documento=TipoDocumentoFiscal.NFCE,
                ambiente=AmbienteFiscal.HOMOLOGACAO,
                serie=primeiro.serie,
                numero=primeiro.numero,
                status=StatusDocumentoFiscal.PRONTO,
                valor_total=outra_venda.total_liquido,
                usuario=self.usuario,
            )

    def test_cancelamento_nao_reutiliza_numero(self):
        primeiro = preparar_documento_venda(self.venda, self.usuario)
        primeiro.status = StatusDocumentoFiscal.CANCELADO
        primeiro.save(update_fields=["status"])

        segundo = preparar_documento_venda(self._criar_venda(indice=2), self.usuario)

        self.assertEqual((primeiro.numero, segundo.numero), (100, 101))
        self.assertEqual(
            SerieFiscal.objects.get(
                filial=self.filial, tipo_documento=TipoDocumentoFiscal.NFCE
            ).proximo_numero,
            102,
        )

    @override_settings(
        FISCAL_SEFAZ_ADAPTER="apps.fiscal.test_concorrencia_multi_pdv.AdaptadorResultadoIncerto",
        FISCAL_CONTINGENCY_NOT_FOUND_CONFIRMATIONS=2,
    )
    def test_mesmo_xml_reutiliza_chave_idempotente_apos_reconciliacao(self):
        documento = preparar_documento_venda(self.venda, self.usuario)
        AdaptadorResultadoIncerto.reiniciar()

        with self.assertRaises(ValidationError):
            transmitir_documento_sefaz(documento, self.usuario)
        documento.refresh_from_db()
        consultar_situacao_documento(documento, self.usuario)
        documento.refresh_from_db()
        consultar_situacao_documento(documento, self.usuario)
        documento.refresh_from_db()
        with self.assertRaises(ValidationError):
            transmitir_documento_sefaz(documento, self.usuario)

        self.assertEqual(AdaptadorResultadoIncerto.transmissoes, 2)
        self.assertEqual(len(set(AdaptadorResultadoIncerto.chaves)), 1)
        self.assertEqual(
            EvidenciaFiscal.objects.filter(
                documento=documento, tipo=TipoEvidenciaFiscal.XML_ENVIO
            ).count(),
            1,
        )


@skipUnless(connection.vendor == "postgresql", "Concorrência real exige PostgreSQL.")
class MultiPdvPreparationConcurrencyTests(MultiPdvFixtureMixin, TransactionTestCase):
    reset_sequences = True

    def _preparar_vendas(self, vendas):
        barreira = Barrier(len(vendas))

        def preparar(venda_id):
            close_old_connections()
            try:
                venda = Venda.objects.get(pk=venda_id)
                usuario = get_user_model().objects.get(pk=self.usuario.pk)
                barreira.wait(timeout=15)
                return preparar_documento_venda(venda, usuario).pk
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=len(vendas)) as executor:
            return list(executor.map(preparar, [v.pk for v in vendas]))

    def test_cinco_pdvs_compartilham_serie_sem_duplicar_ou_perder_numero(self):
        vendas = [self.venda] + [self._criar_venda(indice=i) for i in range(2, 6)]

        documentos = self._preparar_vendas(vendas)

        queryset = DocumentoFiscal.objects.filter(pk__in=documentos)
        self.assertEqual(queryset.count(), 5)
        self.assertEqual(sorted(queryset.values_list("numero", flat=True)), [100, 101, 102, 103, 104])
        self.assertEqual(queryset.values("venda_id").distinct().count(), 5)
        self.assertEqual(queryset.values("venda__caixa_id").distinct().count(), 5)
        self.assertEqual(
            SerieFiscal.objects.get(
                filial=self.filial, tipo_documento=TipoDocumentoFiscal.NFCE
            ).proximo_numero,
            105,
        )

    def test_filiais_usam_series_independentes(self):
        outra_filial = self._criar_segunda_filial()
        outra_venda = self._criar_venda(filial=outra_filial, indice=2)

        documentos = self._preparar_vendas([self.venda, outra_venda])

        emitidos = DocumentoFiscal.objects.filter(pk__in=documentos).order_by("filial_id")
        self.assertEqual(list(emitidos.values_list("numero", flat=True)), [100, 100])
        self.assertEqual(set(emitidos.values_list("filial_id", flat=True)), {self.filial.pk, outra_filial.pk})
        self.assertEqual(
            list(
                SerieFiscal.objects.filter(
                    filial__in=[self.filial, outra_filial],
                    tipo_documento=TipoDocumentoFiscal.NFCE,
                ).values_list("proximo_numero", flat=True)
            ),
            [101, 101],
        )

    def test_nfe_e_nfce_usam_series_independentes(self):
        barreira = Barrier(2)

        def preparar_venda():
            close_old_connections()
            try:
                barreira.wait(timeout=15)
                return preparar_documento_venda(
                    Venda.objects.get(pk=self.venda.pk),
                    get_user_model().objects.get(pk=self.usuario.pk),
                ).pk
            finally:
                close_old_connections()

        def preparar_pedido():
            from apps.marketplace.models import PedidoOnline

            close_old_connections()
            try:
                barreira.wait(timeout=15)
                return preparar_documento_pedido_online(
                    PedidoOnline.objects.get(pk=self.pedido.pk),
                    get_user_model().objects.get(pk=self.usuario.pk),
                ).pk
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            ids = [executor.submit(preparar_venda), executor.submit(preparar_pedido)]
            documentos = [future.result(timeout=30) for future in ids]

        valores = set(
            DocumentoFiscal.objects.filter(pk__in=documentos).values_list(
                "tipo_documento", "numero"
            )
        )
        self.assertEqual(valores, {(TipoDocumentoFiscal.NFCE, 100), (TipoDocumentoFiscal.NFE, 200)})
        self.assertEqual(
            SerieFiscal.objects.get(tipo_documento=TipoDocumentoFiscal.NFCE).proximo_numero,
            101,
        )
        self.assertEqual(
            SerieFiscal.objects.get(tipo_documento=TipoDocumentoFiscal.NFE).proximo_numero,
            201,
        )


@skipUnless(connection.vendor == "postgresql", "Concorrência real exige PostgreSQL.")
class MultiPdvQueueConcurrencyTests(MultiPdvFixtureMixin, TransactionTestCase):
    reset_sequences = True

    @override_settings(
        FISCAL_SEFAZ_ADAPTER="apps.fiscal.test_concorrencia_multi_pdv.AdaptadorMultiPdv"
    )
    def test_dois_workers_processam_documentos_diferentes_uma_unica_vez(self):
        vendas = [self.venda] + [self._criar_venda(indice=i) for i in range(2, 5)]
        documentos = [preparar_documento_venda(venda, self.usuario) for venda in vendas]
        AdaptadorMultiPdv.reiniciar()

        def processar():
            close_old_connections()
            try:
                return processar_fila_fiscal(limite=4, forcar=True)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            resumos = list(executor.map(lambda _: processar(), range(2)))

        ids = [documento.pk for documento in documentos]
        atualizados = DocumentoFiscal.objects.filter(pk__in=ids)
        self.assertTrue(AdaptadorMultiPdv.dois_envios.is_set())
        self.assertEqual(sum(r["emitidos"] for r in resumos), 4)
        self.assertEqual(AdaptadorMultiPdv.chamadas, {documento_id: 1 for documento_id in ids})
        self.assertEqual(atualizados.filter(status=StatusDocumentoFiscal.EMITIDO).count(), 4)
        self.assertEqual(atualizados.filter(tentativas_transmissao=1).count(), 4)
        self.assertFalse(atualizados.filter(transmissao_reserva_token__isnull=False).exists())
        for documento_id in ids:
            tipos = list(
                EvidenciaFiscal.objects.filter(documento_id=documento_id).values_list(
                    "tipo", flat=True
                )
            )
            self.assertEqual(tipos.count(TipoEvidenciaFiscal.XML_ENVIO), 1)
            self.assertEqual(tipos.count(TipoEvidenciaFiscal.RETORNO_TRANSMISSAO), 1)
            self.assertEqual(tipos.count(TipoEvidenciaFiscal.XML_AUTORIZADO), 1)

    @override_settings(
        FISCAL_SEFAZ_ADAPTER="apps.fiscal.test_concorrencia_multi_pdv.AdaptadorManualFila"
    )
    def test_transmissao_manual_nao_ultrapassa_reserva_da_fila(self):
        documento = preparar_documento_venda(self.venda, self.usuario)
        AdaptadorManualFila.reiniciar()

        def worker():
            close_old_connections()
            try:
                return processar_fila_fiscal(limite=1, forcar=True)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=1) as executor:
            futuro = executor.submit(worker)
            self.assertTrue(AdaptadorManualFila.entrou.wait(timeout=15))
            documento.refresh_from_db()
            with self.assertRaises(ValidationError) as bloqueio:
                transmitir_documento_sefaz(documento, self.usuario)
            mensagem = " ".join(bloqueio.exception.messages)
            self.assertTrue(
                "reservado por outro processo" in mensagem
                or "Consulte a situação" in mensagem,
                mensagem,
            )
            AdaptadorManualFila.liberar.set()
            resumo = futuro.result(timeout=30)

        documento.refresh_from_db()
        self.assertEqual(resumo["emitidos"], 1)
        self.assertEqual(AdaptadorManualFila.chamadas, 1)
        self.assertEqual(documento.tentativas_transmissao, 1)
        self.assertIsNone(documento.transmissao_reserva_token)

    @override_settings(
        FISCAL_SEFAZ_ADAPTER="apps.fiscal.test_concorrencia_multi_pdv.AdaptadorResultadoIncerto",
        FISCAL_CONTINGENCY_NOT_FOUND_CONFIRMATIONS=2,
    )
    def test_worker_consulta_resultado_incerto_antes_de_novo_envio(self):
        documento = preparar_documento_venda(self.venda, self.usuario)
        AdaptadorResultadoIncerto.reiniciar()

        primeiro = processar_fila_fiscal(limite=1, forcar=True)
        documento.refresh_from_db()
        documento.proxima_tentativa_em = timezone.now() - timedelta(seconds=1)
        documento.save(update_fields=["proxima_tentativa_em"])
        segundo = processar_fila_fiscal(limite=1, forcar=True)

        documento.refresh_from_db()
        self.assertEqual(primeiro["processados"], 1)
        self.assertEqual(segundo["consultados"], 1)
        self.assertEqual(AdaptadorResultadoIncerto.transmissoes, 1)
        self.assertEqual(AdaptadorResultadoIncerto.consultas, 1)
        self.assertTrue(documento.aguardando_consulta_sefaz)

    @override_settings(
        FISCAL_SEFAZ_ADAPTER="apps.fiscal.test_concorrencia_multi_pdv.AdaptadorMultiPdv",
        FISCAL_AUTO_TRANSMIT_LEASE_SECONDS=30,
    )
    def test_lease_expirado_sem_envio_pode_ser_assumido(self):
        documento = preparar_documento_venda(self.venda, self.usuario)
        documento.transmissao_reserva_token = uuid.uuid4()
        documento.transmissao_reservada_em = timezone.now() - timedelta(seconds=31)
        documento.save(update_fields=["transmissao_reserva_token", "transmissao_reservada_em"])
        AdaptadorMultiPdv.reiniciar()
        AdaptadorMultiPdv.dois_envios.set()

        resumo = processar_fila_fiscal(limite=1, forcar=True)

        documento.refresh_from_db()
        self.assertEqual(resumo["emitidos"], 1)
        self.assertEqual(AdaptadorMultiPdv.chamadas, {documento.pk: 1})
        self.assertIsNone(documento.transmissao_reserva_token)

    @override_settings(
        FISCAL_SEFAZ_ADAPTER="apps.fiscal.test_concorrencia_multi_pdv.AdaptadorResultadoIncerto",
        FISCAL_AUTO_TRANSMIT_LEASE_SECONDS=30,
    )
    def test_lease_expirado_aguardando_resultado_executa_somente_consulta(self):
        documento = preparar_documento_venda(self.venda, self.usuario)
        documento.aguardando_consulta_sefaz = True
        documento.transmissao_reserva_token = uuid.uuid4()
        documento.transmissao_reservada_em = timezone.now() - timedelta(seconds=31)
        documento.save(
            update_fields=[
                "aguardando_consulta_sefaz",
                "transmissao_reserva_token",
                "transmissao_reservada_em",
            ]
        )
        AdaptadorResultadoIncerto.reiniciar()

        resumo = processar_fila_fiscal(limite=1, forcar=True)

        self.assertEqual(resumo["consultados"], 1)
        self.assertEqual(AdaptadorResultadoIncerto.transmissoes, 0)
        self.assertEqual(AdaptadorResultadoIncerto.consultas, 1)
