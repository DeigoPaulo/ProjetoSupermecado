from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.auditoria.models import LogAuditoria

from .adapters import diagnosticar_adaptador_sefaz
from .models import AmbienteFiscal, DocumentoFiscal, StatusDocumentoFiscal
from .services import salvar_xml_documento, transmitir_documento_sefaz, transmitir_documento_simulado
STATUS_FILA = [StatusDocumentoFiscal.PRONTO, StatusDocumentoFiscal.CONTINGENCIA]


def configuracao_fila_fiscal():
    return {
        "contrato": "fiscal_transmission_queue_v1",
        "habilitada": bool(getattr(settings, "FISCAL_AUTO_TRANSMIT_ENABLED", False)),
        "max_tentativas": max(1, int(getattr(settings, "FISCAL_AUTO_TRANSMIT_MAX_ATTEMPTS", 8))),
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
    if simular_homologacao:
        ambientes.append(AmbienteFiscal.HOMOLOGACAO)
    queryset = queryset if queryset is not None else DocumentoFiscal.objects.all()
    return (
        queryset.select_related("filial__empresa", "usuario")
        .filter(
            status__in=STATUS_FILA,
            ambiente__in=ambientes,
            tentativas_transmissao__lt=configuracao["max_tentativas"],
            filial__configuracao_fiscal__ativo=True,
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
            tentativas_transmissao__lt=configuracao["max_tentativas"],
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
    elegiveis_producao = documentos_elegiveis_fila(agora=agora, queryset=queryset).count()
    reservados = base.filter(
        transmissao_reservada_em__gte=agora - timedelta(seconds=configuracao["lease_segundos"])
    ).count()
    esgotados = base.filter(tentativas_transmissao__gte=configuracao["max_tentativas"]).count()
    adapter = diagnosticar_adaptador_sefaz()
    return {
        **configuracao,
        "pendentes": base.count(),
        "elegiveis_producao": elegiveis_producao,
        "reservados": reservados,
        "tentativas_esgotadas": esgotados,
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
    if status_anterior not in {
        StatusDocumentoFiscal.PRONTO,
        StatusDocumentoFiscal.REJEITADO,
        StatusDocumentoFiscal.CONTINGENCIA,
    }:
        raise ValidationError("Somente documentos pendentes, rejeitados ou em contingencia podem ser reprocessados.")
    motivo = (motivo or "").strip()
    if not 10 <= len(motivo) <= 255:
        raise ValidationError("Informe um motivo entre 10 e 255 caracteres para o reprocessamento.")

    if status_anterior == StatusDocumentoFiscal.REJEITADO:
        documento.status = StatusDocumentoFiscal.PRONTO
    documento.tentativas_transmissao = 0
    documento.proxima_tentativa_em = timezone.now()
    documento.transmissao_reservada_em = None
    documento.xml_assinado_em = None
    documento.certificado_serial_assinatura = ""
    documento.save(
        update_fields=[
            "status",
            "tentativas_transmissao",
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
        "ignorados": 0,
        "erros": [],
    }
    if not configuracao["habilitada"] and not forcar:
        resumo["motivo"] = "Transmissao fiscal automatica desabilitada."
        return resumo

    elegiveis = documentos_elegiveis_fila(simular_homologacao=simular_homologacao)
    if elegiveis.filter(ambiente=AmbienteFiscal.PRODUCAO).exists():
        adapter = diagnosticar_adaptador_sefaz()
        if not adapter["carregavel"]:
            raise ValidationError(adapter["erro"] or "Adaptador SEFAZ de producao indisponivel.")

    for documento_id in list(elegiveis.values_list("id", flat=True)[:limite]):
        agora = timezone.now()
        if not _reservar_documento(documento_id, agora, configuracao):
            resumo["ignorados"] += 1
            continue
        documento = DocumentoFiscal.objects.select_related("usuario").get(pk=documento_id)
        try:
            if documento.ambiente == AmbienteFiscal.HOMOLOGACAO:
                resultado = transmitir_documento_simulado(documento, documento.usuario)
            else:
                resultado = transmitir_documento_sefaz(documento, documento.usuario)
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
            documento.refresh_from_db(fields=["tentativas_transmissao"])
            atraso = atraso_proxima_tentativa(documento.tentativas_transmissao, configuracao)
            DocumentoFiscal.objects.filter(pk=documento_id).update(
                proxima_tentativa_em=timezone.now() + timedelta(seconds=atraso),
                transmissao_reservada_em=None,
            )
            resumo["processados"] += 1
            resumo["reagendados"] += 1
            resumo["erros"].append({"documento_id": documento_id, "mensagem": str(exc)[:500]})
    return resumo