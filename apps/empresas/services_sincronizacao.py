import json
from datetime import timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import EventoSincronizacao, ModoImplantacao, StatusSincronizacao


class ErroSincronizacao(Exception):
    pass


@transaction.atomic
def enfileirar_evento(*, empresa, tipo, objeto_tipo, objeto_id, payload, chave_idempotencia, filial=None):
    if empresa.modo_implantacao == ModoImplantacao.LOCAL or not empresa.sincronizacao_automatica:
        return None, False
    evento, criado = EventoSincronizacao.objects.get_or_create(
        chave_idempotencia=chave_idempotencia,
        defaults={
            "empresa": empresa,
            "filial": filial,
            "tipo": tipo,
            "objeto_tipo": objeto_tipo,
            "objeto_id": str(objeto_id),
            "payload": payload,
        },
    )
    return evento, criado


def enviar_evento_http(evento):
    token = settings.SINCRONIZACAO_API_TOKEN
    if not token:
        raise ErroSincronizacao("Credencial SINCRONIZACAO_API_TOKEN nao configurada no servidor local.")
    url = urljoin(evento.empresa.url_sincronizacao.rstrip("/") + "/", "eventos/")
    corpo = json.dumps(
        {
            "id": str(evento.identificador),
            "tipo": evento.tipo,
            "objeto": {"tipo": evento.objeto_tipo, "id": evento.objeto_id},
            "empresa_id": evento.empresa_id,
            "empresa_cnpj": evento.empresa.cnpj,
            "filial_id": evento.filial_id,
            "filial_cnpj": evento.filial.cnpj if evento.filial else None,
            "payload": evento.payload,
            "criado_em": evento.criado_em.isoformat(),
        }
    ).encode("utf-8")
    requisicao = Request(
        url,
        data=corpo,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Idempotency-Key": evento.chave_idempotencia,
            "X-Event-ID": str(evento.identificador),
        },
    )
    try:
        with urlopen(requisicao, timeout=settings.SINCRONIZACAO_TIMEOUT_SEGUNDOS) as resposta:
            if not 200 <= resposta.status < 300:
                raise ErroSincronizacao(f"Servidor remoto respondeu HTTP {resposta.status}.")
    except HTTPError as exc:
        raise ErroSincronizacao(f"Servidor remoto respondeu HTTP {exc.code}.") from exc
    except (URLError, TimeoutError) as exc:
        raise ErroSincronizacao(f"Falha de comunicacao com a nuvem: {exc.reason if hasattr(exc, 'reason') else exc}.") from exc


def _registrar_falha(evento, erro):
    base = settings.SINCRONIZACAO_RETRY_BASE_SEGUNDOS
    limite = settings.SINCRONIZACAO_RETRY_MAX_SEGUNDOS
    esgotado = evento.tentativas >= settings.SINCRONIZACAO_MAX_TENTATIVAS
    espera = min(base * (2 ** max(evento.tentativas - 1, 0)), limite)
    evento.status = StatusSincronizacao.ERRO
    evento.ultimo_erro = str(erro)[:2000]
    evento.proxima_tentativa_em = None if esgotado else timezone.now() + timedelta(seconds=espera)
    evento.save(update_fields=["status", "ultimo_erro", "proxima_tentativa_em", "atualizado_em"])


def processar_fila(*, limite=50, enviar=enviar_evento_http):
    agora = timezone.now()
    candidatos = list(
        EventoSincronizacao.objects.filter(
            status__in=[StatusSincronizacao.PENDENTE, StatusSincronizacao.ERRO],
            tentativas__lt=settings.SINCRONIZACAO_MAX_TENTATIVAS,
            empresa__sincronizacao_automatica=True,
        )
        .filter(Q(proxima_tentativa_em__isnull=True) | Q(proxima_tentativa_em__lte=agora))
        .order_by("criado_em")
        .values_list("pk", flat=True)[:limite]
    )
    resultado = {"enviados": 0, "erros": 0}
    for pk in candidatos:
        with transaction.atomic():
            evento = EventoSincronizacao.objects.select_for_update().select_related("empresa", "filial").get(pk=pk)
            if evento.status not in {StatusSincronizacao.PENDENTE, StatusSincronizacao.ERRO}:
                continue
            evento.status = StatusSincronizacao.PROCESSANDO
            evento.tentativas += 1
            evento.save(update_fields=["status", "tentativas", "atualizado_em"])
        try:
            enviar(evento)
        except Exception as exc:
            _registrar_falha(evento, exc)
            resultado["erros"] += 1
        else:
            evento.status = StatusSincronizacao.ENVIADO
            evento.processado_em = timezone.now()
            evento.proxima_tentativa_em = None
            evento.ultimo_erro = ""
            evento.save(update_fields=["status", "processado_em", "proxima_tentativa_em", "ultimo_erro", "atualizado_em"])
            resultado["enviados"] += 1
    return resultado
