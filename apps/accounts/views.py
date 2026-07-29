from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import ListView

from apps.empresas.models import Filial

from .forms import UsuarioPerfilForm
from .models import TipoPerfil
from .permissions import SISTEMA, RoleRequiredMixin, role_required


def _empresa_id_do_usuario(user):
    if user.is_superuser:
        return None
    perfil = getattr(user, "perfil_supermercado", None)
    return perfil.filial.empresa_id if perfil and perfil.is_active and perfil.filial_id else 0


def _usuarios_visiveis(user):
    queryset = User.objects.all()
    if user.is_superuser:
        return queryset
    return queryset.filter(
        is_superuser=False,
        perfil_supermercado__is_active=True,
        perfil_supermercado__filial__empresa_id=_empresa_id_do_usuario(user),
    )


def _filiais_permitidas(user):
    queryset = Filial.objects.filter(is_active=True)
    if user.is_superuser:
        return queryset
    return queryset.filter(empresa_id=_empresa_id_do_usuario(user))


class UsuarioListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    required_roles = {TipoPerfil.ADMINISTRADOR}
    model = User
    template_name = "accounts/usuario_list.html"
    context_object_name = "usuarios"
    paginate_by = 50

    def get_queryset(self):
        queryset = _usuarios_visiveis(self.request.user).select_related(
            "perfil_supermercado", "perfil_supermercado__filial", "perfil_supermercado__filial__empresa"
        ).order_by("username")
        termo = (self.request.GET.get("q") or "").strip()
        if termo:
            queryset = queryset.filter(
                Q(username__icontains=termo) | Q(first_name__icontains=termo) | Q(email__icontains=termo)
            )
        return queryset


@login_required
@role_required(TipoPerfil.ADMINISTRADOR)
def usuario_form(request, pk=None):
    usuario = get_object_or_404(_usuarios_visiveis(request.user), pk=pk) if pk else None
    parametros_form = {
        "instance": usuario,
        "filiais_queryset": _filiais_permitidas(request.user).order_by("empresa__nome_fantasia", "nome"),
        "permite_staff": request.user.is_superuser,
        "exige_filial": not request.user.is_superuser,
    }
    if request.method == "POST":
        form = UsuarioPerfilForm(request.POST, **parametros_form)
        if form.is_valid():
            user = form.save()
            messages.success(request, "Usuario salvo com sucesso.")
            return redirect("accounts:usuario_editar", pk=user.pk)
    else:
        form = UsuarioPerfilForm(**parametros_form)

    return render(request, "accounts/usuario_form.html", {"form": form, "usuario_obj": usuario})

@login_required
@role_required(TipoPerfil.ADMINISTRADOR)
def recuperacao_senha_diagnostico(request):
    backend = getattr(settings, "EMAIL_BACKEND", "")
    smtp_backend = backend.endswith("smtp.EmailBackend")
    console_backend = backend.endswith("console.EmailBackend")
    locmem_backend = backend.endswith("locmem.EmailBackend")
    host_configurado = bool(getattr(settings, "EMAIL_HOST", ""))
    usuario_configurado = bool(getattr(settings, "EMAIL_HOST_USER", ""))
    senha_configurada = bool(getattr(settings, "EMAIL_HOST_PASSWORD", ""))
    remetente = getattr(settings, "DEFAULT_FROM_EMAIL", "")
    remetente_configurado = bool(remetente and "@" in remetente)
    tls = bool(getattr(settings, "EMAIL_USE_TLS", False))
    ssl = bool(getattr(settings, "EMAIL_USE_SSL", False))
    timeout = getattr(settings, "EMAIL_TIMEOUT", None)
    porta = getattr(settings, "EMAIL_PORT", None)
    alertas = []

    if console_backend or locmem_backend:
        alertas.append("Backend de desenvolvimento ativo; os e-mails nao saem para usuarios reais.")
    if smtp_backend and not host_configurado:
        alertas.append("SMTP sem host configurado.")
    if smtp_backend and not remetente_configurado:
        alertas.append("Remetente padrao invalido ou ausente.")
    if smtp_backend and not usuario_configurado:
        alertas.append("Usuario SMTP nao configurado; confirme se o provedor aceita envio sem autenticacao.")
    if smtp_backend and usuario_configurado and not senha_configurada:
        alertas.append("Senha SMTP ausente para o usuario configurado.")
    if tls and ssl:
        alertas.append("TLS e SSL estao ativos ao mesmo tempo; escolha apenas uma opcao conforme o provedor.")

    pronto_producao = smtp_backend and host_configurado and remetente_configurado and not (tls and ssl)
    if usuario_configurado:
        pronto_producao = pronto_producao and senha_configurada

    if console_backend or locmem_backend:
        prontidao_status = "development_only"
        prontidao_percentual = 55
        bloqueios = ["Ative um backend SMTP para enviar mensagens a usuarios reais."]
    elif not smtp_backend:
        prontidao_status = "unsupported_backend"
        prontidao_percentual = 35
        bloqueios = ["Configure um backend SMTP suportado para a recuperacao de senha."]
    elif not pronto_producao:
        prontidao_status = "configuration_required"
        prontidao_percentual = 70
        bloqueios = list(alertas)
    else:
        prontidao_status = "ready_for_homologation"
        prontidao_percentual = 90
        bloqueios = []

    recomendacoes = []
    if pronto_producao:
        recomendacoes.extend(
            [
                "Executar envio real de recuperacao para uma caixa de teste.",
                "Validar SPF, DKIM, DMARC, remetente e entrega sem cair em spam.",
            ]
        )
    payload = {
        "contrato": "password_reset_email_v1",
        "status": "ready_for_production" if pronto_producao else "needs_configuration",
        "prontidao": {
            "contrato": "password_reset_readiness_v1",
            "status": prontidao_status,
            "percentual": prontidao_percentual,
            "configuracao_smtp_completa": pronto_producao,
            "homologacao_real_pendente": pronto_producao,
            "bloqueios": bloqueios,
            "recomendacoes": recomendacoes,
        },
        "backend": {
            "smtp": smtp_backend,
            "console": console_backend,
            "memoria_teste": locmem_backend,
        },
        "smtp": {
            "host_configurado": host_configurado,
            "porta": porta,
            "usuario_configurado": usuario_configurado,
            "senha_configurada": senha_configurada,
            "tls": tls,
            "ssl": ssl,
            "timeout_segundos": timeout,
        },
        "remetente_configurado": remetente_configurado,
        "seguranca": {
            "resposta_publica_neutra": True,
            "token_temporario_uso_unico": True,
            "nao_expoe_credenciais": True,
        },
        "alertas": alertas,
    }
    return JsonResponse(payload)

