import base64
import hashlib
import json
import logging
import secrets
import uuid
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.core import signing
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from .models import (
    AutorizacaoEmergencial,
    ConcessaoLicenca,
    ContratoLicenca,
    DesafioLiberacaoLocal,
    EstadoLicencaLocal,
    EventoWebhookAsaas,
    FaturaLicenca,
    InstalacaoLocal,
    LiberacaoEmergencialLocal,
    StatusContrato,
    StatusEventoCobranca,
    StatusFatura,
)

logger = logging.getLogger(__name__)
SALT_CONCESSAO = "deigo-tecnologia.licenca.v1"


def diagnostico_prontidao_licenciamento():
    privada_pem = bool(str(settings.LICENCIAMENTO_CHAVE_PRIVADA_PEM or "").strip())
    privada_arquivo = str(settings.LICENCIAMENTO_CHAVE_PRIVADA_ARQUIVO or "").strip()
    privada_disponivel = privada_pem or bool(privada_arquivo and Path(privada_arquivo).is_file())
    script = Path(settings.BASE_DIR) / "scripts" / "register_licensing_billing_task.ps1"
    asaas_url = str(settings.ASAAS_API_URL or "").strip()
    asaas_https = asaas_url.lower().startswith("https://")
    asaas_sandbox = "sandbox" in asaas_url.lower()
    asaas_api_key = str(settings.ASAAS_API_KEY or "").strip()
    webhook_token = str(settings.ASAAS_WEBHOOK_TOKEN or "")
    webhook_configurado = bool(webhook_token)
    webhook_token_valido = bool(
        32 <= len(webhook_token) <= 255
        and not any(caractere.isspace() for caractere in webhook_token)
        and webhook_token != asaas_api_key
    )
    fallback_ativo = bool(settings.LICENCIAMENTO_PERMITIR_ASSINATURA_COMPARTILHADA)
    alertas = []

    if not privada_disponivel:
        alertas.append("Configure a chave privada Ed25519 somente no servidor central.")
    if fallback_ativo:
        alertas.append("O fallback de assinatura compartilhada está ativo; desative-o em produção.")
    if not asaas_https:
        alertas.append("Configure a URL HTTPS da API do Asaas.")
    if not asaas_api_key:
        alertas.append("Configure a credencial do Asaas para publicar as cobranças.")
    if not webhook_configurado:
        alertas.append("Configure o token do webhook do Asaas.")
    elif not webhook_token_valido:
        alertas.append(
            "O token do webhook do Asaas deve ter entre 32 e 255 caracteres, "
            "não pode conter espaços nem ser igual à chave da API."
        )
    if not script.is_file():
        alertas.append("O script de agendamento diário do licenciamento não foi encontrado.")

    pronto_homologacao = bool(
        privada_disponivel
        and not fallback_ativo
        and asaas_https
        and asaas_api_key
        and webhook_token_valido
        and script.is_file()
    )
    return {
        "contrato": "licensing_readiness_v1",
        "chave_privada_ed25519": privada_disponivel,
        "fallback_assinatura_compartilhada": fallback_ativo,
        "asaas_configurado": bool(asaas_api_key),
        "asaas_url_https": asaas_https,
        "asaas_sandbox": asaas_sandbox,
        "webhook_configurado": webhook_configurado,
        "webhook_token_valido": webhook_token_valido,
        "script_agendamento_disponivel": script.is_file(),
        "comando_agendamento": r".\scripts\register_licensing_billing_task.ps1 -Horario 06:00 -ExecutarSemLogin",
        "pronto_homologacao": pronto_homologacao,
        "pronto_producao": bool(pronto_homologacao and not asaas_sandbox),
        "alertas": alertas,
    }


def _chave_assinatura():
    return settings.LICENCIAMENTO_CHAVE_ASSINATURA


def _chave_assimetrica_configurada(*, privada=False):
    prefixo = "LICENCIAMENTO_CHAVE_PRIVADA" if privada else "LICENCIAMENTO_CHAVE_PUBLICA"
    return bool(
        str(getattr(settings, f"{prefixo}_PEM", "") or "").strip()
        or str(getattr(settings, f"{prefixo}_ARQUIVO", "") or "").strip()
    )


def assinar_concessao(payload):
    if _chave_assimetrica_configurada(privada=True):
        assinatura = _chave_privada_emergencial().sign(_json_canonico(payload))
        envelope = {"payload": payload, "assinatura": _base64_url_encode(assinatura)}
        return "ed25519." + _base64_url_encode(_json_canonico(envelope))
    if not settings.LICENCIAMENTO_PERMITIR_ASSINATURA_COMPARTILHADA:
        raise RuntimeError("A chave privada Ed25519 da central não está configurada.")
    return signing.dumps(payload, key=_chave_assinatura(), salt=SALT_CONCESSAO, compress=True)


def verificar_concessao(assinatura):
    if assinatura.startswith("ed25519."):
        try:
            envelope = json.loads(_base64_url_decode(assinatura.removeprefix("ed25519.")).decode("utf-8"))
            payload = envelope["payload"]
            assinatura_bytes = _base64_url_decode(envelope["assinatura"])
            _chave_publica_emergencial().verify(assinatura_bytes, _json_canonico(payload))
            return payload
        except (InvalidSignature, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise signing.BadSignature("Concessão Ed25519 inválida.") from exc
    if not settings.LICENCIAMENTO_PERMITIR_ASSINATURA_COMPARTILHADA:
        raise signing.BadSignature("Concessões legadas com segredo compartilhado estão desativadas.")
    return signing.loads(assinatura, key=_chave_assinatura(), salt=SALT_CONCESSAO)


def atualizar_status_contrato(contrato, agora=None):
    agora = agora or timezone.now()
    hoje = agora.date()
    if contrato.status == StatusContrato.CANCELADO:
        return contrato.status

    pendentes = contrato.faturas.filter(status__in=[StatusFatura.PENDENTE, StatusFatura.VENCIDA])
    vencida = pendentes.filter(vencimento__lt=hoje).order_by("vencimento").first()
    proxima = pendentes.order_by("vencimento").first()
    novo_status = StatusContrato.ATIVO
    tolerancia_ate = None

    if vencida:
        tolerancia_ate = timezone.make_aware(
            timezone.datetime.combine(
                vencida.vencimento + timedelta(days=contrato.plano.dias_tolerancia),
                timezone.datetime.max.time(),
            )
        )
        novo_status = StatusContrato.TOLERANCIA if agora <= tolerancia_ate else StatusContrato.SUSPENSO
        pendentes.filter(vencimento__lt=hoje, status=StatusFatura.PENDENTE).update(status=StatusFatura.VENCIDA)
    elif proxima and (proxima.vencimento - hoje).days <= contrato.plano.dias_aviso:
        novo_status = StatusContrato.AVISO

    if contrato.status != novo_status or contrato.tolerancia_ate != tolerancia_ate:
        contrato.status = novo_status
        contrato.tolerancia_ate = tolerancia_ate
        contrato.save(update_fields=["status", "tolerancia_ate", "atualizado_em"])
    return novo_status


def emitir_concessao(instalacao, agora=None):
    agora = agora or timezone.now()
    contrato = ContratoLicenca.objects.select_related("empresa", "plano").get(empresa=instalacao.empresa)
    status = atualizar_status_contrato(contrato, agora)
    pendentes = contrato.faturas.filter(status__in=[StatusFatura.PENDENTE, StatusFatura.VENCIDA]).order_by("vencimento")
    proxima = pendentes.first()
    valor_pendente = pendentes.aggregate(total=Sum("valor"))["total"] or Decimal("0")
    valida_ate = agora + timedelta(hours=settings.LICENCIAMENTO_CONCESSAO_HORAS)
    offline_ate = valida_ate + timedelta(days=settings.LICENCIAMENTO_OFFLINE_DIAS)
    payload = {
        "contrato": "license_lease_v2",
        "assinatura_algoritmo": "ed25519" if _chave_assimetrica_configurada(privada=True) else "django-signing-hmac",
        "empresa_id": contrato.empresa_id,
        "empresa_cnpj": contrato.empresa.cnpj,
        "empresa": contrato.empresa.nome_fantasia,
        "instalacao_id": str(instalacao.identificador),
        "status": status,
        "emitida_em": agora.isoformat(),
        "valida_ate": valida_ate.isoformat(),
        "offline_ate": offline_ate.isoformat(),
        "tolerancia_ate": contrato.tolerancia_ate.isoformat() if contrato.tolerancia_ate else None,
        "proxima_fatura_vencimento": proxima.vencimento.isoformat() if proxima else None,
        "valor_pendente": str(valor_pendente),
        "url_pagamento": proxima.invoice_url if proxima else "",
        "mensagem": _mensagem_licenca(status, proxima, contrato),
        "limites": {
            "filiais": contrato.empresa.filiais.filter(is_active=True).count(),
            "terminais": sum(filial.terminais_pdv.filter(ativo=True).count() for filial in contrato.empresa.filiais.all()),
        },
    }
    assinatura = assinar_concessao(payload)
    ConcessaoLicenca.objects.update_or_create(
        instalacao=instalacao,
        defaults={
            "status": status,
            "emitida_em": agora,
            "valida_ate": valida_ate,
            "tolerancia_ate": contrato.tolerancia_ate,
            "assinatura": assinatura,
            "payload": payload,
        },
    )
    return payload, assinatura


def _mensagem_licenca(status, fatura, contrato):
    if status == StatusContrato.AVISO and fatura:
        return f"A mensalidade vence em {fatura.vencimento:%d/%m/%Y}. Regularize pelo link da fatura."
    if status == StatusContrato.TOLERANCIA and fatura:
        return f"Mensalidade vencida. O sistema está em tolerância até {contrato.tolerancia_ate:%d/%m/%Y %H:%M}."
    if status == StatusContrato.SUSPENSO:
        return contrato.motivo_bloqueio or "Licença suspensa por pendência financeira."
    if status == StatusContrato.CANCELADO:
        return contrato.motivo_bloqueio or "Contrato de licença cancelado."
    return "Licença regular."


def sincronizar_licenca_local(empresa):
    if not settings.LICENCIAMENTO_CENTRAL_URL or not settings.LICENCIAMENTO_API_TOKEN:
        return {"status": "nao_configurado", "empresa": empresa.pk}
    url = settings.LICENCIAMENTO_CENTRAL_URL.rstrip("/") + "/licenciamento/api/v1/renovar/"
    liberacoes_pendentes = list(
        LiberacaoEmergencialLocal.objects.filter(empresa=empresa, sincronizada_em__isnull=True)
        .values_list("autorizacao_id", flat=True)[:20]
    )
    corpo = json.dumps(
        {
            "empresa_cnpj": empresa.cnpj,
            "instalacao_id": settings.LICENCIAMENTO_INSTALACAO_ID,
            "versao": settings.PDV_DESKTOP_VERSION,
            "liberacoes_emergenciais": [str(item) for item in liberacoes_pendentes],
        }
    ).encode("utf-8")
    request = Request(
        url,
        data=corpo,
        headers={
            "Authorization": f"Bearer {settings.LICENCIAMENTO_API_TOKEN}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        response = urlopen(request, timeout=settings.LICENCIAMENTO_TIMEOUT_SEGUNDOS)
        dados = json.loads(response.read().decode("utf-8"))
        payload = verificar_concessao(dados["assinatura"])
        cnpj_payload = "".join(ch for ch in payload.get("empresa_cnpj", "") if ch.isdigit())
        cnpj_local = "".join(ch for ch in empresa.cnpj if ch.isdigit())
        if payload != dados["licenca"] or cnpj_payload != cnpj_local:
            raise signing.BadSignature("Concessão não pertence à empresa local.")
        estado, _ = EstadoLicencaLocal.objects.update_or_create(empresa=empresa)
        estado.status = payload["status"]
        estado.valida_ate = timezone.datetime.fromisoformat(payload["valida_ate"])
        estado.tolerancia_ate = timezone.datetime.fromisoformat(payload["tolerancia_ate"]) if payload["tolerancia_ate"] else None
        estado.offline_ate = timezone.datetime.fromisoformat(payload["offline_ate"])
        estado.ultima_sincronizacao_em = timezone.now()
        estado.proxima_fatura_vencimento = payload["proxima_fatura_vencimento"] or None
        estado.valor_pendente = Decimal(payload["valor_pendente"])
        estado.url_pagamento = payload["url_pagamento"]
        estado.mensagem = payload["mensagem"]
        estado.ultimo_erro = ""
        estado.assinatura = dados["assinatura"]
        estado.save()
        reconciliadas = dados.get("liberacoes_reconciliadas") or []
        if reconciliadas:
            LiberacaoEmergencialLocal.objects.filter(
                empresa=empresa, autorizacao_id__in=reconciliadas, sincronizada_em__isnull=True
            ).update(sincronizada_em=timezone.now())
        return {"status": "sincronizado", "licenca": payload, "liberacoes_reconciliadas": reconciliadas}
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, KeyError, json.JSONDecodeError, signing.BadSignature, RuntimeError) as exc:
        estado, _ = EstadoLicencaLocal.objects.get_or_create(empresa=empresa)
        estado.ultimo_erro = str(exc)[:500]
        estado.save(update_fields=["ultimo_erro", "atualizado_em"])
        logger.warning("Falha ao renovar licença da empresa %s: %s", empresa.pk, exc)
        return {"status": "erro", "erro": str(exc)}



def _base64_url_encode(valor):
    return base64.urlsafe_b64encode(valor).decode("ascii").rstrip("=")


def _base64_url_decode(valor):
    padding = "=" * (-len(valor) % 4)
    return base64.urlsafe_b64decode((valor + padding).encode("ascii"))


def _json_canonico(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _conteudo_chave(nome_pem, nome_arquivo):
    conteudo = str(getattr(settings, nome_pem, "") or "").replace("\\n", "\n").strip()
    arquivo = str(getattr(settings, nome_arquivo, "") or "").strip()
    if not conteudo and arquivo:
        conteudo = Path(arquivo).read_text(encoding="utf-8").strip()
    if not conteudo:
        raise RuntimeError(f"Configure {nome_pem} ou {nome_arquivo}.")
    return conteudo.encode("utf-8")


def _chave_privada_emergencial():
    try:
        chave = serialization.load_pem_private_key(
            _conteudo_chave("LICENCIAMENTO_CHAVE_PRIVADA_PEM", "LICENCIAMENTO_CHAVE_PRIVADA_ARQUIVO"),
            password=None,
        )
    except (OSError, TypeError, ValueError) as exc:
        raise RuntimeError("A chave privada Ed25519 da central é inválida ou não pode ser lida.") from exc
    if not isinstance(chave, Ed25519PrivateKey):
        raise RuntimeError("A chave privada de licenciamento deve ser Ed25519.")
    return chave


def _chave_publica_emergencial():
    try:
        chave = serialization.load_pem_public_key(
            _conteudo_chave("LICENCIAMENTO_CHAVE_PUBLICA_PEM", "LICENCIAMENTO_CHAVE_PUBLICA_ARQUIVO")
        )
    except (OSError, TypeError, ValueError) as exc:
        raise RuntimeError("A chave pública Ed25519 local é inválida ou não pode ser lida.") from exc
    if not isinstance(chave, Ed25519PublicKey):
        raise RuntimeError("A chave pública de licenciamento deve ser Ed25519.")
    return chave


def gerar_desafio_liberacao(empresa, agora=None):
    agora = agora or timezone.now()
    try:
        instalacao_id = str(settings.LICENCIAMENTO_INSTALACAO_ID).strip()
        instalacao_uuid = str(uuid.UUID(instalacao_id))
    except (ValueError, AttributeError):
        raise RuntimeError("LICENCIAMENTO_INSTALACAO_ID não identifica está instalação local.")
    nonce = secrets.token_urlsafe(32)
    desafio = DesafioLiberacaoLocal.objects.create(
        empresa=empresa,
        nonce_hash=hashlib.sha256(nonce.encode("utf-8")).hexdigest(),
        expira_em=agora + timedelta(minutes=30),
    )
    payload = {
        "contrato": "license_offline_challenge_v1",
        "desafio_id": str(desafio.identificador),
        "empresa_cnpj": empresa.cnpj,
        "instalacao_id": instalacao_uuid,
        "nonce": nonce,
        "criado_em": agora.isoformat(),
        "expira_em": desafio.expira_em.isoformat(),
    }
    return desafio, _base64_url_encode(_json_canonico(payload))


def ler_desafio_liberacao(codigo, agora=None):
    agora = agora or timezone.now()
    try:
        payload = json.loads(_base64_url_decode(codigo.strip()).decode("utf-8"))
        if payload.get("contrato") != "license_offline_challenge_v1":
            raise ValueError
        if timezone.datetime.fromisoformat(payload["expira_em"]) < agora:
            raise RuntimeError("O desafio expirou. Gere um novo código no servidor local.")
        uuid.UUID(payload["desafio_id"])
        uuid.UUID(payload["instalacao_id"])
    except RuntimeError:
        raise
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Código de desafio inválido.") from exc
    return payload


def emitir_autorizacao_emergencial(*, codigo_desafio, motivo, horas, usuario, ip=None, agora=None):
    agora = agora or timezone.now()
    horas = int(horas)
    if horas not in {24, 72, 168}:
        raise RuntimeError("Escolha uma validade de 24 horas, 3 dias ou 7 dias.")
    desafio = ler_desafio_liberacao(codigo_desafio, agora)
    instalacao = InstalacaoLocal.objects.select_related("empresa").filter(
        identificador=desafio["instalacao_id"], ativa=True
    ).first()
    if not instalacao:
        raise RuntimeError("A instalação não está credenciada ou está bloqueada na central.")
    cnpj_desafio = "".join(ch for ch in desafio["empresa_cnpj"] if ch.isdigit())
    cnpj_instalacao = "".join(ch for ch in instalacao.empresa.cnpj if ch.isdigit())
    if not hmac_compare(cnpj_desafio, cnpj_instalacao):
        raise RuntimeError("O desafio não pertence à empresa credenciada.")
    autorizacao_id = uuid.uuid4()
    valida_ate = agora + timedelta(hours=horas)
    payload = {
        "contrato": "license_offline_release_v1",
        "autorizacao_id": str(autorizacao_id),
        "desafio_id": desafio["desafio_id"],
        "empresa_cnpj": instalacao.empresa.cnpj,
        "instalacao_id": str(instalacao.identificador),
        "nonce": desafio["nonce"],
        "motivo": motivo.strip(),
        "emitida_em": agora.isoformat(),
        "valida_ate": valida_ate.isoformat(),
    }
    if len(payload["motivo"]) < 10:
        raise RuntimeError("Informe um motivo com pelo menos 10 caracteres.")
    assinatura_bytes = _chave_privada_emergencial().sign(_json_canonico(payload))
    envelope = {"payload": payload, "assinatura": _base64_url_encode(assinatura_bytes)}
    codigo = _base64_url_encode(_json_canonico(envelope))
    autorizacao = AutorizacaoEmergencial.objects.create(
        identificador=autorizacao_id,
        instalacao=instalacao,
        desafio_id=desafio["desafio_id"],
        nonce_hash=hashlib.sha256(desafio["nonce"].encode("utf-8")).hexdigest(),
        motivo=payload["motivo"],
        emitida_por=usuario,
        emitida_em=agora,
        valida_ate=valida_ate,
        assinatura=codigo,
        ip_emissao=ip,
    )
    return autorizacao, codigo


def aplicar_autorizacao_emergencial(*, empresa, codigo, agora=None):
    agora = agora or timezone.now()
    try:
        envelope = json.loads(_base64_url_decode(codigo.strip()).decode("utf-8"))
        payload = envelope["payload"]
        assinatura = _base64_url_decode(envelope["assinatura"])
        _chave_publica_emergencial().verify(assinatura, _json_canonico(payload))
        if payload.get("contrato") != "license_offline_release_v1":
            raise ValueError
    except (InvalidSignature, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Código de liberação inválido ou assinatura não reconhecida.") from exc
    cnpj_payload = "".join(ch for ch in payload["empresa_cnpj"] if ch.isdigit())
    cnpj_local = "".join(ch for ch in empresa.cnpj if ch.isdigit())
    if not hmac_compare(cnpj_payload, cnpj_local):
        raise RuntimeError("A liberação pertence a outra empresa.")
    if str(payload["instalacao_id"]) != str(settings.LICENCIAMENTO_INSTALACAO_ID):
        raise RuntimeError("A liberação pertence a outra instalação.")
    emitida_em = timezone.datetime.fromisoformat(payload["emitida_em"])
    valida_ate = timezone.datetime.fromisoformat(payload["valida_ate"])
    if valida_ate <= agora or valida_ate > emitida_em + timedelta(days=7):
        raise RuntimeError("A liberação está expirada ou excede o prazo máximo permitido.")
    nonce_hash = hashlib.sha256(payload["nonce"].encode("utf-8")).hexdigest()
    autorizacao_id = uuid.UUID(payload["autorizacao_id"])
    instalacao_id = uuid.UUID(payload["instalacao_id"])
    with transaction.atomic():
        desafio = DesafioLiberacaoLocal.objects.select_for_update().filter(
            identificador=payload["desafio_id"], empresa=empresa, nonce_hash=nonce_hash, usado_em__isnull=True
        ).first()
        if not desafio or desafio.expira_em < emitida_em:
            raise RuntimeError("O desafio local não existe, expirou ou já foi utilizado.")
        liberacao = LiberacaoEmergencialLocal.objects.create(
            autorizacao_id=autorizacao_id,
            empresa=empresa,
            desafio=desafio,
            instalacao_id=instalacao_id,
            motivo=payload["motivo"],
            emitida_em=emitida_em,
            valida_ate=valida_ate,
            assinatura=codigo,
        )
        desafio.usado_em = agora
        desafio.save(update_fields=["usado_em"])
        estado, _ = EstadoLicencaLocal.objects.get_or_create(empresa=empresa)
        estado.liberacao_emergencial_ate = valida_ate
        estado.liberacao_emergencial_motivo = payload["motivo"]
        estado.save(update_fields=["liberacao_emergencial_ate", "liberacao_emergencial_motivo", "atualizado_em"])
    return liberacao


def hmac_compare(valor_a, valor_b):
    import hmac
    return hmac.compare_digest(str(valor_a), str(valor_b))

def _asaas_request(method, endpoint, payload=None):
    if not settings.ASAAS_API_KEY:
        raise RuntimeError("ASAAS_API_KEY não configurada.")
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(
        settings.ASAAS_API_URL.rstrip("/") + endpoint,
        data=data,
        headers={"access_token": settings.ASAAS_API_KEY, "Content-Type": "application/json", "Accept": "application/json"},
        method=method,
    )
    try:
        response = urlopen(request, timeout=settings.ASAAS_TIMEOUT_SEGUNDOS)
        return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detalhe = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Asaas respondeu HTTP {exc.code}: {detalhe[:300]}") from exc
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Falha de comunicação com o Asaas: {exc}") from exc


def garantir_cliente_asaas(contrato):
    if contrato.asaas_customer_id:
        return contrato.asaas_customer_id
    empresa = contrato.empresa
    dados = _asaas_request(
        "POST",
        "/customers",
        {
            "name": empresa.razao_social or empresa.nome_fantasia,
            "cpfCnpj": "".join(ch for ch in empresa.cnpj if ch.isdigit()),
            "email": empresa.email,
            "mobilePhone": "".join(ch for ch in empresa.telefone if ch.isdigit()),
            "externalReference": f"empresa:{empresa.pk}",
        },
    )
    contrato.asaas_customer_id = dados["id"]
    contrato.save(update_fields=["asaas_customer_id", "atualizado_em"])
    return contrato.asaas_customer_id


def gerar_cobranca_asaas(fatura):
    if fatura.asaas_payment_id:
        return fatura
    customer_id = garantir_cliente_asaas(fatura.contrato)
    dados = _asaas_request(
        "POST",
        "/payments",
        {
            "customer": customer_id,
            "billingType": "UNDEFINED",
            "value": float(fatura.valor),
            "dueDate": fatura.vencimento.isoformat(),
            "description": f"Licença Deigo Tecnologia - {fatura.competencia:%m/%Y}",
            "externalReference": fatura.referencia_externa,
        },
    )
    fatura.asaas_payment_id = dados["id"]
    fatura.invoice_url = dados.get("invoiceUrl", "")
    fatura.bank_slip_url = dados.get("bankSlipUrl", "")
    fatura.save(update_fields=["asaas_payment_id", "invoice_url", "bank_slip_url", "atualizado_em"])
    return fatura


@transaction.atomic
def processar_evento_asaas(evento):
    evento = EventoWebhookAsaas.objects.select_for_update().get(pk=evento.pk)
    if evento.status == StatusEventoCobranca.PROCESSADO:
        return evento
    pagamento = evento.payload.get("payment") or {}
    payment_id = pagamento.get("id")
    fatura = FaturaLicenca.objects.select_for_update().filter(asaas_payment_id=payment_id).first()
    if not fatura:
        evento.status = StatusEventoCobranca.IGNORADO
    elif evento.tipo in {"PAYMENT_RECEIVED", "PAYMENT_CONFIRMED"}:
        fatura.status = StatusFatura.RECEBIDA
        fatura.pago_em = timezone.now()
        fatura.save(update_fields=["status", "pago_em", "atualizado_em"])
        contrato = fatura.contrato
        contrato.status = StatusContrato.ATIVO
        contrato.tolerancia_ate = None
        contrato.motivo_bloqueio = ""
        contrato.save(update_fields=["status", "tolerancia_ate", "motivo_bloqueio", "atualizado_em"])
        evento.status = StatusEventoCobranca.PROCESSADO
    elif evento.tipo in {"PAYMENT_OVERDUE"}:
        fatura.status = StatusFatura.VENCIDA
        fatura.save(update_fields=["status", "atualizado_em"])
        atualizar_status_contrato(fatura.contrato)
        evento.status = StatusEventoCobranca.PROCESSADO
    elif evento.tipo in {"PAYMENT_DELETED", "PAYMENT_REFUNDED", "PAYMENT_REFUND_IN_PROGRESS"}:
        fatura.status = StatusFatura.ESTORNADA if "REFUND" in evento.tipo else StatusFatura.CANCELADA
        fatura.save(update_fields=["status", "atualizado_em"])
        evento.status = StatusEventoCobranca.PROCESSADO
    else:
        evento.status = StatusEventoCobranca.IGNORADO
    evento.processado_em = timezone.now()
    evento.save(update_fields=["status", "processado_em"])
    return evento
