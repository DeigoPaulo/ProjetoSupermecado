from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.auditoria.models import LogAuditoria

from .adapters import diagnosticar_adaptador_sefaz
from .models import AmbienteFiscal, DocumentoFiscal, StatusDocumentoFiscal, TipoDocumentoFiscal
from .services import (
    consultar_situacao_documento,
    salvar_xml_documento,
    transmitir_documento_sefaz,
    transmitir_documento_simulado,
)
STATUS_FILA = [StatusDocumentoFiscal.PRONTO, StatusDocumentoFiscal.CONTINGENCIA]


def configuracao_fila_fiscal():
    return {
        "contrato": "fiscal_transmission_queue_v1",
        "habilitada": bool(getattr(settings, "FISCAL_AUTO_TRANSMIT_ENABLED", False)),
        "max_tentativas": max(1, int(getattr(settings, "FISCAL_AUTO_TRANSMIT_MAX_ATTEMPTS", 8))),
        "max_consultas": max(1, int(getattr(settings, "FISCAL_AUTO_QUERY_MAX_ATTEMPTS", 12))),
        "confirmacoes_nao_localizado": max(
            2,
            int(getattr(settings, "FISCAL_CONTINGENCY_NOT_FOUND_CONFIRMATIONS", 2)),
        ),
        "espera_base_segundos": max(1, int(getattr(settings, "FISCAL_AUTO_TRANSMIT_RETRY_BASE_SECONDS", 60))),
        "espera_maxima_segundos": max(1, int(getattr(settings, "FISCAL_AUTO_TRANSMIT_RETRY_MAX_SECONDS", 3600))),
        "lease_segundos": max(30, int(getattr(settings, "FISCAL_AUTO_TRANSMIT_LEASE_SECONDS", 300))),
    }


def atraso_proxima_tentativa(tentativas, configuracao=None):
    configuracao = configuracao or configuracao_fila_fiscal()
    expoente = max(0, int(tentativas or 1) - 1)
    return min(configuracao["espera_base_segundos"] * (2 ** expoente), configuracao["espera_maxima_segundos"])


def documentos_elegiveis_fila(*, simular_homologacao=False, agora=None, queryset=None):
    agora = agora or timezone.now()
    configuracao = configuracao_fila_fiscal()
    ambientes = [AmbienteFiscal.PRODUCAO]
    adapter = diagnosticar_adaptador_sefaz()
    if simular_homologacao or adapter["carregavel"]:
        ambientes.append(AmbienteFiscal.HOMOLOGACAO)
    queryset = queryset if queryset is not None else DocumentoFiscal.objects.all()
    return (
        queryset.select_related("filial__empresa", "usuario")
        .filter(
            status__in=STATUS_FILA,
            ambiente__in=ambientes,
            filial__configuracao_fiscal__ativo=True,
        )
        .filter(
            Q(
                aguardando_consulta_sefaz=True,
                tentativas_consulta_sefaz__lt=configuracao["max_consultas"],
            )
            | Q(
                aguardando_consulta_sefaz=False,
                tentativas_transmissao__lt=configuracao["max_tentativas"],
            )
        )
        .filter(Q(proxima_tentativa_em__isnull=True) | Q(proxima_tentativa_em__lte=agora))
        .filter(
            Q(transmissao_reservada_em__isnull=True)
            | Q(transmissao_reservada_em__lt=agora - timedelta(seconds=configuracao["lease_segundos"]))
        )
        .order_by("status", "transmissao_limite_em", "criado_em")
    )


def _reservar_documento(documento_id, agora, configuracao):
    return bool(
        DocumentoFiscal.objects.filter(
            pk=documento_id,
            status__in=STATUS_FILA,
        )
        .filter(
            Q(
                aguardando_consulta_sefaz=True,
                tentativas_consulta_sefaz__lt=configuracao["max_consultas"],
            )
            | Q(
                aguardando_consulta_sefaz=False,
                tentativas_transmissao__lt=configuracao["max_tentativas"],
            )
        )
        .filter(Q(proxima_tentativa_em__isnull=True) | Q(proxima_tentativa_em__lte=agora))
        .filter(
            Q(transmissao_reservada_em__isnull=True)
            | Q(transmissao_reservada_em__lt=agora - timedelta(seconds=configuracao["lease_segundos"]))
        )
        .update(transmissao_reservada_em=agora)
    )


def diagnostico_fila_fiscal(queryset=None):
    configuracao = configuracao_fila_fiscal()
    agora = timezone.now()
    queryset = queryset if queryset is not None else DocumentoFiscal.objects.all()
    base = queryset.filter(status__in=STATUS_FILA)
    elegiveis_producao = documentos_elegiveis_fila(
        agora=agora,
        queryset=queryset.filter(ambiente=AmbienteFiscal.PRODUCAO),
    ).count()
    reservados = base.filter(
        transmissao_reservada_em__gte=agora - timedelta(seconds=configuracao["lease_segundos"])
    ).count()
    esgotados = base.filter(
        aguardando_consulta_sefaz=False,
        tentativas_transmissao__gte=configuracao["max_tentativas"],
    ).count()
    aguardando_consulta = base.filter(aguardando_consulta_sefaz=True).count()
    consultas_esgotadas = base.filter(
        aguardando_consulta_sefaz=True,
        tentativas_consulta_sefaz__gte=configuracao["max_consultas"],
    ).count()
    contingencias_offline_vencidas = base.filter(
        tipo_documento=TipoDocumentoFiscal.NFCE,
        contingencia_iniciada_em__isnull=False,
        transmissao_limite_em__lt=agora,
    ).count()
    adapter = diagnosticar_adaptador_sefaz()
    return {
        **configuracao,
        "pendentes": base.count(),
        "elegiveis_producao": elegiveis_producao,
        "reservados": reservados,
        "tentativas_esgotadas": esgotados,
        "aguardando_consulta_sefaz": aguardando_consulta,
        "consultas_esgotadas": consultas_esgotadas,
        "contingencias_offline_vencidas": contingencias_offline_vencidas,
        "adaptador_configurado": adapter["configurado"],
        "adaptador_carregavel": adapter["carregavel"],
        "pronta": bool(configuracao["habilitada"] and adapter["carregavel"]),
    }


@transaction.atomic
def reagendar_documento_fiscal(documento, usuario, motivo, ip=None):
    documento = DocumentoFiscal.objects.select_for_update().get(pk=documento.pk)
    status_anterior = documento.status
    tentativas_anteriores = documento.tentativas_transmissao
    mensagem_anterior = documento.mensagem_retorno
    if documento.aguardando_consulta_sefaz:
        raise ValidationError(
            "Consulte a situação da chave na SEFAZ antes de reprocessar este documento."
        )
    if status_anterior not in {
        StatusDocumentoFiscal.PRONTO,
        StatusDocumentoFiscal.REJEITADO,
        StatusDocumentoFiscal.CONTINGENCIA,
    }:
        raise ValidationError("Somente documentos pendentes, rejeitados ou em contingência podem ser reprocessados.")
    motivo = (motivo or "").strip()
    if not 10 <= len(motivo) <= 255:
        raise ValidationError("Informe um motivo entre 10 e 255 caracteres para o reprocessamento.")

    if status_anterior == StatusDocumentoFiscal.REJEITADO:
        documento.status = StatusDocumentoFiscal.PRONTO
    documento.tentativas_transmissao = 0
    documento.tentativas_consulta_sefaz = 0
    documento.confirmacoes_nao_localizado = 0
    documento.proxima_tentativa_em = timezone.now()
    documento.transmissao_reservada_em = None
    documento.xml_assinado_em = None
    documento.certificado_serial_assinatura = ""
    documento.save(
        update_fields=[
            "status",
            "tentativas_transmissao",
            "tentativas_consulta_sefaz",
            "confirmacoes_nao_localizado",
            "proxima_tentativa_em",
            "transmissao_reservada_em",
            "xml_assinado_em",
            "certificado_serial_assinatura",
            "atualizado_em",
        ]
    )
    salvar_xml_documento(documento)
    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="fiscal",
        acao="REAGENDA_TRANSMISSAO_FISCAL",
        descricao=(
            f"Documento fiscal {documento.id} recolocado na fila. "
            f"Status anterior: {status_anterior}; tentativas anteriores: {tentativas_anteriores}; "
            f"motivo: {motivo}; retorno anterior: {mensagem_anterior[:500] or '-'}"
        ),
        objeto_tipo="DocumentoFiscal",
        objeto_id=str(documento.id),
        ip=ip,
    )
    return documento


@transaction.atomic
def retomar_consultas_documento_fiscal(documento, usuario, motivo, ip=None):
    documento = DocumentoFiscal.objects.select_for_update().get(pk=documento.pk)
    configuracao = configuracao_fila_fiscal()
    tentativas_anteriores = documento.tentativas_consulta_sefaz
    mensagem_anterior = documento.mensagem_consulta_sefaz
    if not documento.aguardando_consulta_sefaz:
        raise ValidationError("Este documento não está aguardando reconciliação com a SEFAZ.")
    if tentativas_anteriores < configuracao["max_consultas"]:
        raise ValidationError("O limite de consultas automáticas ainda não foi atingido.")
    if not diagnosticar_adaptador_sefaz()["consulta_documento"]:
        raise ValidationError("O adaptador SEFAZ configurado não oferece consulta de protocolo.")
    motivo = (motivo or "").strip()
    if not 10 <= len(motivo) <= 255:
        raise ValidationError("Informe um motivo entre 10 e 255 caracteres para retomar as consultas.")

    documento.tentativas_consulta_sefaz = 0
    documento.confirmacoes_nao_localizado = 0
    documento.proxima_tentativa_em = timezone.now()
    documento.transmissao_reservada_em = None
    documento.save(update_fields=["tentativas_consulta_sefaz", "confirmacoes_nao_localizado", "proxima_tentativa_em", "transmissao_reservada_em", "atualizado_em"])
    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="fiscal",
        acao="RETOMA_CONSULTAS_SEFAZ",
        descricao=(
            f"Consultas automáticas do documento fiscal {documento.id} retomadas. "
            f"Consultas anteriores: {tentativas_anteriores}; motivo: {motivo}; "
            f"último retorno: {mensagem_anterior[:500] or '-'}"
        ),
        objeto_tipo="DocumentoFiscal",
        objeto_id=str(documento.id),
        ip=ip,
    )
    return documento


def processar_fila_fiscal(*, limite=50, simular_homologacao=False, forcar=False):
    configuracao = configuracao_fila_fiscal()
    limite = min(200, max(1, int(limite)))
    resumo = {
        "contrato": configuracao["contrato"],
        "habilitada": configuracao["habilitada"],
        "processados": 0,
        "emitidos": 0,
        "rejeitados": 0,
        "reagendados": 0,
        "consultados": 0,
        "reconciliados": 0,
        "consultas_esgotadas": 0,
        "ignorados": 0,
        "erros": [],
    }
    if not configuracao["habilitada"] and not forcar:
        resumo["motivo"] = "Transmissao fiscal automática desabilitada."
        return resumo

    elegiveis = documentos_elegiveis_fila(simular_homologacao=simular_homologacao)
    if elegiveis.filter(ambiente=AmbienteFiscal.PRODUCAO).exists():
        adapter = diagnosticar_adaptador_sefaz()
        if not adapter["carregavel"]:
            raise ValidationError(adapter["erro"] or "Adaptador SEFAZ de produção indisponivel.")

    for documento_id in list(elegiveis.values_list("id", flat=True)[:limite]):
        agora = timezone.now()
        if not _reservar_documento(documento_id, agora, configuracao):
            resumo["ignorados"] += 1
            continue
        documento = DocumentoFiscal.objects.select_related("usuario").get(pk=documento_id)
        try:
            if documento.aguardando_consulta_sefaz:
                resultado, _ = consultar_situacao_documento(
                    documento, documento.usuario
                )
                resumo["processados"] += 1
                resumo["consultados"] += 1
                if resultado.status not in STATUS_FILA:
                    resumo["reconciliados"] += 1
                    if resultado.status == StatusDocumentoFiscal.EMITIDO:
                        resumo["emitidos"] += 1
                    DocumentoFiscal.objects.filter(pk=documento_id).update(
                        proxima_tentativa_em=None,
                        transmissao_reservada_em=None,
                    )
                elif (
                    resultado.tentativas_consulta_sefaz
                    >= configuracao["max_consultas"]
                ):
                    DocumentoFiscal.objects.filter(pk=documento_id).update(
                        proxima_tentativa_em=None,
                        transmissao_reservada_em=None,
                    )
                    resumo["consultas_esgotadas"] += 1
                else:
                    atraso = atraso_proxima_tentativa(
                        resultado.tentativas_consulta_sefaz, configuracao
                    )
                    DocumentoFiscal.objects.filter(pk=documento_id).update(
                        proxima_tentativa_em=timezone.now() + timedelta(seconds=atraso),
                        transmissao_reservada_em=None,
                    )
                    resumo["reagendados"] += 1
                continue
            if (
                documento.ambiente == AmbienteFiscal.HOMOLOGACAO
                and simular_homologacao
            ):
                resultado = transmitir_documento_simulado(
                    documento, documento.usuario
                )
            else:
                resultado = transmitir_documento_sefaz(
                    documento, documento.usuario
                )
            resumo["processados"] += 1
            if resultado.status == StatusDocumentoFiscal.EMITIDO:
                resumo["emitidos"] += 1
                DocumentoFiscal.objects.filter(pk=documento_id).update(
                    proxima_tentativa_em=None,
                    transmissao_reservada_em=None,
                )
            elif resultado.status == StatusDocumentoFiscal.REJEITADO:
                resumo["rejeitados"] += 1
                DocumentoFiscal.objects.filter(pk=documento_id).update(
                    proxima_tentativa_em=None,
                    transmissao_reservada_em=None,
                )
            else:
                resultado.refresh_from_db(fields=["tentativas_transmissao"])
                atraso = atraso_proxima_tentativa(resultado.tentativas_transmissao, configuracao)
                DocumentoFiscal.objects.filter(pk=documento_id).update(
                    proxima_tentativa_em=timezone.now() + timedelta(seconds=atraso),
                    transmissao_reservada_em=None,
                )
                resumo["reagendados"] += 1
        except Exception as exc:
            documento.refresh_from_db(
                fields=[
                    "aguardando_consulta_sefaz",
                    "tentativas_transmissao",
                    "tentativas_consulta_sefaz",
                ]
            )
            tentativas = (
                documento.tentativas_consulta_sefaz
                if documento.aguardando_consulta_sefaz
                else documento.tentativas_transmissao
            )
            consulta_esgotada = (
                documento.aguardando_consulta_sefaz
                and documento.tentativas_consulta_sefaz >= configuracao["max_consultas"]
            )
            atraso = atraso_proxima_tentativa(tentativas, configuracao)
            DocumentoFiscal.objects.filter(pk=documento_id).update(
                proxima_tentativa_em=(
                    None
                    if consulta_esgotada
                    else timezone.now() + timedelta(seconds=atraso)
                ),
                transmissao_reservada_em=None,
            )
            resumo["processados"] += 1
            if consulta_esgotada:
                resumo["consultas_esgotadas"] += 1
            else:
                resumo["reagendados"] += 1
            resumo["erros"].append({"documento_id": documento_id, "mensagem": str(exc)[:500]})
    return resumo