import hmac
import json
import logging
import uuid
from calendar import monthrange
from datetime import date
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.accounts.models import TipoPerfil
from apps.auditoria.models import LogAuditoria

from .forms import (
    AplicarLiberacaoEmergencialForm,
    ContratoLicencaForm,
    EmitirLiberacaoEmergencialForm,
    InstalacaoLocalForm,
    PlanoComercialForm,
)
from .models import (
    AutorizacaoEmergencial,
    ContratoLicenca,
    EstadoLicencaLocal,
    EventoWebhookAsaas,
    FaturaLicenca,
    InstalacaoLocal,
    PlanoComercial,
    StatusEventoCobranca,
    StatusFatura,
)
from .services import (
    aplicar_autorizacao_emergencial,
    emitir_autorizacao_emergencial,
    emitir_concessao,
    gerar_cobranca_asaas,
    gerar_desafio_liberacao,
    processar_evento_asaas,
)


logger = logging.getLogger(__name__)


def _exigir_super_admin(user):
    if not user.is_authenticated or not user.is_superuser:
        raise PermissionDenied


def _licenciamento_readiness():
    privada_pem = bool(str(settings.LICENCIAMENTO_CHAVE_PRIVADA_PEM or "").strip())
    privada_arquivo = str(settings.LICENCIAMENTO_CHAVE_PRIVADA_ARQUIVO or "").strip()
    privada_disponivel = privada_pem or bool(privada_arquivo and Path(privada_arquivo).is_file())
    script = Path(settings.BASE_DIR) / "scripts" / "register_licensing_billing_task.ps1"
    alertas = []
    if not privada_disponivel:
        alertas.append("Configure a chave privada Ed25519 somente no servidor central.")
    if settings.LICENCIAMENTO_PERMITIR_ASSINATURA_COMPARTILHADA:
        alertas.append("O fallback de assinatura compartilhada está ativo; desative-o em produção.")
    if not settings.ASAAS_API_KEY:
        alertas.append("Configure a credencial do Asaas para publicar as cobranças.")
    if not settings.ASAAS_WEBHOOK_TOKEN:
        alertas.append("Configure o token do webhook do Asaas.")
    return {
        "contrato": "licensing_readiness_v1",
        "chave_privada_ed25519": privada_disponivel,
        "fallback_assinatura_compartilhada": settings.LICENCIAMENTO_PERMITIR_ASSINATURA_COMPARTILHADA,
        "asaas_configurado": bool(settings.ASAAS_API_KEY),
        "asaas_sandbox": "sandbox" in settings.ASAAS_API_URL.lower(),
        "webhook_configurado": bool(settings.ASAAS_WEBHOOK_TOKEN),
        "script_agendamento_disponivel": script.is_file(),
        "comando_agendamento": ".\\scripts\\register_licensing_billing_task.ps1 -Horario 06:00 -ExecutarSemLogin",
        "pronto_homologacao": bool(
            privada_disponivel
            and settings.ASAAS_API_KEY
            and settings.ASAAS_WEBHOOK_TOKEN
            and script.is_file()
        ),
        "alertas": alertas,
    }

def _empresa_do_usuario(user):
    perfil = getattr(user, "perfil_supermercado", None)
    return perfil.filial.empresa if perfil and perfil.is_active and perfil.filial_id else None

def _pagina_nomeada(request, queryset, parametro):
    pagina = Paginator(queryset, 50).get_page(request.GET.get(parametro))
    params = request.GET.copy()
    if pagina.has_previous():
        params[parametro] = pagina.previous_page_number()
        pagina.previous_url = f"?{params.urlencode()}"
    else:
        pagina.previous_url = ""
    if pagina.has_next():
        params[parametro] = pagina.next_page_number()
        pagina.next_url = f"?{params.urlencode()}"
    else:
        pagina.next_url = ""
    return pagina

@login_required
def minha_licenca(request):
    if request.user.is_superuser:
        return redirect("licenciamento:central")
    empresa = _empresa_do_usuario(request.user)
    if not empresa:
        raise PermissionDenied
    contrato = ContratoLicenca.objects.filter(empresa=empresa).select_related("plano").first()
    estado = EstadoLicencaLocal.objects.filter(empresa=empresa).first()
    faturas = contrato.faturas.all()[:24] if contrato else []
    perfil = getattr(request.user, "perfil_supermercado", None)
    return render(
        request,
        "licenciamento/minha_licenca.html",
        {
            "empresa": empresa,
            "contrato": contrato,
            "estado": estado,
            "faturas": faturas,
            "pode_contingencia": bool(perfil and perfil.tipo == TipoPerfil.ADMINISTRADOR),
            "form_liberacao": AplicarLiberacaoEmergencialForm(),
            "liberacoes": empresa.liberacoes_emergenciais.all()[:10],
        },
    )


@login_required
def central_licencas(request):
    _exigir_super_admin(request.user)
    contratos_qs = ContratoLicenca.objects.select_related("empresa", "plano")
    instalacoes_qs = InstalacaoLocal.objects.select_related("empresa")
    autorizacoes_qs = AutorizacaoEmergencial.objects.select_related(
        "instalacao", "instalacao__empresa", "emitida_por"
    )
    return render(
        request,
        "licenciamento/central.html",
        {
            "contratos": _pagina_nomeada(request, contratos_qs, "contratos_page"),
            "instalacoes": _pagina_nomeada(request, instalacoes_qs, "instalacoes_page"),
            "contratos_total": contratos_qs.count(),
            "instalacoes_total": instalacoes_qs.count(),
            "planos_total": PlanoComercial.objects.count(),
            "faturas_pendentes": FaturaLicenca.objects.filter(status__in=[StatusFatura.PENDENTE, StatusFatura.VENCIDA]).count(),
            "autorizacoes_emergenciais": _pagina_nomeada(
                request, autorizacoes_qs, "autorizacoes_page"
            ),
            "readiness": _licenciamento_readiness(),
        },
    )


@login_required
def central_diagnostico(request):
    _exigir_super_admin(request.user)
    return JsonResponse(_licenciamento_readiness())

def _form_super_admin(request, form_class, titulo, sucesso, redirect_name="licenciamento:central"):
    _exigir_super_admin(request.user)
    form = form_class(request.POST or None)
    if request.method == "POST" and form.is_valid():
        objeto = form.save()
        LogAuditoria.objects.create(
            usuario=request.user,
            modulo="licenciamento",
            acao=sucesso,
            descricao=f"{objeto} salvo pelo super admin.",
            objeto_tipo=objeto._meta.label,
            objeto_id=str(objeto.pk),
            ip=request.META.get("REMOTE_ADDR"),
        )
        messages.success(request, titulo + " salvo com sucesso.")
        return redirect(redirect_name)
    return render(request, "licenciamento/form.html", {"form": form, "titulo": titulo})


@login_required
def plano_novo(request):
    return _form_super_admin(request, PlanoComercialForm, "Plano comercial", "plano_comercial_criado")


@login_required
def contrato_novo(request):
    return _form_super_admin(request, ContratoLicencaForm, "Contrato de licença", "contrato_licenca_criado")


@login_required
def instalacao_nova(request):
    _exigir_super_admin(request.user)
    form = InstalacaoLocalForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        instalacao = form.save(commit=False)
        token = instalacao.emitir_token()
        instalacao.save()
        LogAuditoria.objects.create(
            usuario=request.user,
            modulo="licenciamento",
            acao="instalacao_local_credenciada",
            descricao=f"Instalação {instalacao} credenciada. O token foi exibido uma única vez.",
            objeto_tipo=instalacao._meta.label,
            objeto_id=str(instalacao.pk),
            ip=request.META.get("REMOTE_ADDR"),
        )
        return render(request, "licenciamento/token_instalacao.html", {"instalacao": instalacao, "token": token})
    return render(request, "licenciamento/form.html", {"form": form, "titulo": "Instalação local"})


@login_required
@require_POST
def gerar_fatura(request, pk):
    _exigir_super_admin(request.user)
    contrato = get_object_or_404(ContratoLicenca.objects.select_related("empresa"), pk=pk)
    hoje = timezone.localdate()
    competencia = hoje.replace(day=1)
    vencimento = date(hoje.year, hoje.month, min(contrato.dia_vencimento, monthrange(hoje.year, hoje.month)[1]))
    referencia = f"licenca:{contrato.pk}:{competencia:%Y-%m}"
    fatura, criada = FaturaLicenca.objects.get_or_create(
        contrato=contrato,
        competencia=competencia,
        defaults={
            "vencimento": vencimento,
            "valor": contrato.valor_mensal,
            "referencia_externa": referencia,
        },
    )
    try:
        gerar_cobranca_asaas(fatura)
        messages.success(request, "Fatura gerada no Asaas e disponibilizada ao cliente.")
    except RuntimeError as exc:
        messages.warning(request, f"Fatura interna criada, mas o Asaas não foi acionado: {exc}")
    LogAuditoria.objects.create(
        usuario=request.user,
        modulo="licenciamento",
        acao="fatura_licenca_gerada" if criada else "fatura_licenca_consultada",
        descricao=f"Fatura {fatura.referencia_externa}: R$ {fatura.valor}.",
        objeto_tipo=fatura._meta.label,
        objeto_id=str(fatura.pk),
        ip=request.META.get("REMOTE_ADDR"),
    )
    return redirect("licenciamento:central")


@login_required
@require_POST
def gerar_desafio_emergencial(request):
    empresa = _empresa_do_usuario(request.user)
    perfil = getattr(request.user, "perfil_supermercado", None)
    if not empresa or not perfil or perfil.tipo != TipoPerfil.ADMINISTRADOR:
        raise PermissionDenied
    try:
        desafio, codigo = gerar_desafio_liberacao(empresa)
    except RuntimeError as exc:
        messages.error(request, str(exc))
        return redirect("licenciamento:minha_licenca")
    LogAuditoria.objects.create(
        usuario=request.user,
        modulo="licenciamento",
        acao="desafio_liberacao_offline_gerado",
        descricao=f"Desafio {desafio.identificador} gerado e válido por 30 minutos.",
        objeto_tipo=desafio._meta.label,
        objeto_id=str(desafio.pk),
        ip=request.META.get("REMOTE_ADDR"),
    )
    return render(
        request,
        "licenciamento/desafio_emergencial.html",
        {"empresa": empresa, "desafio": desafio, "codigo_desafio": codigo},
    )


@login_required
@require_POST
def aplicar_liberacao_emergencial(request):
    empresa = _empresa_do_usuario(request.user)
    perfil = getattr(request.user, "perfil_supermercado", None)
    if not empresa or not perfil or perfil.tipo != TipoPerfil.ADMINISTRADOR:
        raise PermissionDenied
    form = AplicarLiberacaoEmergencialForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Informe o código de liberação completo.")
        return redirect("licenciamento:minha_licenca")
    try:
        liberacao = aplicar_autorizacao_emergencial(
            empresa=empresa,
            codigo=form.cleaned_data["codigo_liberacao"],
        )
    except (RuntimeError, IntegrityError) as exc:
        messages.error(request, str(exc))
        return redirect("licenciamento:minha_licenca")
    LogAuditoria.objects.create(
        usuario=request.user,
        modulo="licenciamento",
        acao="liberacao_emergencial_offline_aplicada",
        descricao=(
            f"Autorização {liberacao.autorizacao_id} aplicada até "
            f"{timezone.localtime(liberacao.valida_ate):%d/%m/%Y %H:%M}. Motivo: {liberacao.motivo}"
        ),
        objeto_tipo=liberacao._meta.label,
        objeto_id=str(liberacao.pk),
        ip=request.META.get("REMOTE_ADDR"),
    )
    messages.success(request, "Liberação emergencial aplicada e registrada para sincronização com a central.")
    return redirect("licenciamento:minha_licenca")


@login_required
def emitir_liberacao_emergencial(request):
    _exigir_super_admin(request.user)
    form = EmitirLiberacaoEmergencialForm(request.POST or None)
    codigo_liberacao = None
    autorizacao = None
    if request.method == "POST" and form.is_valid():
        try:
            autorizacao, codigo_liberacao = emitir_autorizacao_emergencial(
                codigo_desafio=form.cleaned_data["codigo_desafio"],
                motivo=form.cleaned_data["motivo"],
                horas=form.cleaned_data["validade_horas"],
                usuario=request.user,
                ip=request.META.get("REMOTE_ADDR"),
            )
        except (RuntimeError, IntegrityError) as exc:
            form.add_error("codigo_desafio", str(exc))
        else:
            LogAuditoria.objects.create(
                usuario=request.user,
                modulo="licenciamento",
                acao="liberacao_emergencial_offline_emitida",
                descricao=(
                    f"Autorização {autorizacao.identificador} emitida para {autorizacao.instalacao} "
                    f"até {timezone.localtime(autorizacao.valida_ate):%d/%m/%Y %H:%M}."
                ),
                objeto_tipo=autorizacao._meta.label,
                objeto_id=str(autorizacao.pk),
                ip=request.META.get("REMOTE_ADDR"),
            )
    return render(
        request,
        "licenciamento/emitir_emergencial.html",
        {"form": form, "codigo_liberacao": codigo_liberacao, "autorizacao": autorizacao},
    )

@csrf_exempt
@require_POST
def api_renovar_licenca(request):
    token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not token:
        return JsonResponse({"status": "não autorizado"}, status=401)
    token_hash = InstalacaoLocal.hash_token(token)
    instalacao = InstalacaoLocal.objects.select_related("empresa").filter(token_hash=token_hash, ativa=True).first()
    if not instalacao:
        return JsonResponse({"status": "não autorizado"}, status=401)
    try:
        dados = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return JsonResponse({"status": "JSON inválido"}, status=400)
    cnpj = "".join(ch for ch in str(dados.get("empresa_cnpj", "")) if ch.isdigit())
    cnpj_instalacao = "".join(ch for ch in instalacao.empresa.cnpj if ch.isdigit())
    if not hmac.compare_digest(cnpj, cnpj_instalacao):
        return JsonResponse({"status": "empresa divergente"}, status=403)
    agora = timezone.now()
    reconciliadas = []
    for valor in (dados.get("liberacoes_emergenciais") or [])[:20]:
        try:
            autorizacao_id = uuid.UUID(str(valor))
        except (ValueError, TypeError, AttributeError):
            continue
        autorizacao = AutorizacaoEmergencial.objects.filter(
            identificador=autorizacao_id, instalacao=instalacao
        ).first()
        if autorizacao:
            campos = []
            if not autorizacao.usada_em:
                autorizacao.usada_em = agora
                campos.append("usada_em")
            reconciliacao_nova = not autorizacao.reconciliada_em
            if reconciliacao_nova:
                autorizacao.reconciliada_em = agora
                campos.append("reconciliada_em")
            if campos:
                autorizacao.save(update_fields=campos)
            if reconciliacao_nova:
                LogAuditoria.objects.create(
                    modulo="licenciamento",
                    acao="liberacao_emergencial_offline_reconciliada",
                    descricao=f"Autorização {autorizacao.identificador} confirmada pela instalação {instalacao}.",
                    objeto_tipo=autorizacao._meta.label,
                    objeto_id=str(autorizacao.pk),
                    ip=request.META.get("REMOTE_ADDR"),
                )
            reconciliadas.append(str(autorizacao.identificador))
    instalacao.ultima_consulta_em = agora
    instalacao.versao_sistema = str(dados.get("versao", ""))[:40]
    instalacao.ip_ultimo_acesso = request.META.get("REMOTE_ADDR")
    instalacao.save(update_fields=["ultima_consulta_em", "versao_sistema", "ip_ultimo_acesso"])
    try:
        payload, assinatura = emitir_concessao(instalacao)
    except ContratoLicenca.DoesNotExist:
        return JsonResponse({"status": "contrato não configurado"}, status=409)
    except RuntimeError as exc:
        logger.error("Central de licenciamento sem assinatura operacional: %s", exc)
        return JsonResponse({
            "status": "licenciamento temporariamente indisponível",
            "codigo": "central_signature_not_ready",
        }, status=503)
    return JsonResponse({
        "status": "ok",
        "licenca": payload,
        "assinatura": assinatura,
        "liberacoes_reconciliadas": reconciliadas,
    })


@csrf_exempt
@require_POST
def webhook_asaas(request):
    token_configurado = settings.ASAAS_WEBHOOK_TOKEN
    token_recebido = request.headers.get("asaas-access-token", "")
    if not token_configurado or not hmac.compare_digest(token_configurado, token_recebido):
        return JsonResponse({"status": "não autorizado"}, status=401)
    try:
        payload = json.loads(request.body.decode("utf-8"))
        evento_id = str(payload["id"])
        tipo = str(payload["event"])
    except (json.JSONDecodeError, KeyError, TypeError):
        return JsonResponse({"status": "evento inválido"}, status=400)
    try:
        evento, criado = EventoWebhookAsaas.objects.get_or_create(
            evento_id=evento_id,
            defaults={"tipo": tipo, "payload": payload},
        )
    except IntegrityError:
        evento = EventoWebhookAsaas.objects.get(evento_id=evento_id)
        criado = False
    if criado or evento.status in {StatusEventoCobranca.PENDENTE, StatusEventoCobranca.ERRO}:
        try:
            processar_evento_asaas(evento)
        except Exception as exc:
            evento.status = StatusEventoCobranca.ERRO
            evento.erro = str(exc)[:1000]
            evento.save(update_fields=["status", "erro"])
            return JsonResponse({"status": "recebido para reprocessamento"}, status=200)
    return JsonResponse({"status": "recebido", "duplicado": not criado}, status=200)