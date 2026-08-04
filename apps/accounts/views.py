from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.db.models import Count, Q
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.views.generic import ListView

from apps.auditoria.models import LogAuditoria
from apps.empresas.models import Filial

from .forms import CredencialAutorizacaoForm, PoliticaPinSupervisorForm, UsuarioPerfilForm
from .models import CredencialAutorizacao, TipoPerfil
from .permissions import SISTEMA, RoleRequiredMixin, role_required
from .services import diagnostico_prontidao_recuperacao_senha


def _empresa_do_usuario(user):
    if user.is_superuser:
        return None
    perfil = getattr(user, "perfil_supermercado", None)
    return perfil.filial.empresa if perfil and perfil.is_active and perfil.filial_id else None


def _empresa_id_do_usuario(user):
    empresa = _empresa_do_usuario(user)
    return empresa.pk if empresa else (None if user.is_superuser else 0)


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


def _credenciais_visiveis(user):
    queryset = CredencialAutorizacao.objects.select_related(
        "usuario", "usuario__perfil_supermercado", "usuario__perfil_supermercado__filial"
    )
    if user.is_superuser:
        return queryset
    return queryset.filter(
        usuario__is_superuser=False,
        usuario__perfil_supermercado__is_active=True,
        usuario__perfil_supermercado__filial__empresa_id=_empresa_id_do_usuario(user),
    )


def _supervisores_permitidos(user):
    queryset = _usuarios_visiveis(user).filter(is_active=True)
    if user.is_superuser:
        return queryset.filter(
            Q(is_superuser=True)
            | Q(perfil_supermercado__is_active=True, perfil_supermercado__tipo__in=[TipoPerfil.ADMINISTRADOR, TipoPerfil.GERENTE])
        ).distinct().order_by("username")
    return queryset.filter(
        perfil_supermercado__tipo__in=[TipoPerfil.ADMINISTRADOR, TipoPerfil.GERENTE]
    ).order_by("username")


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
            messages.success(request, "Usuário salvo com sucesso.")
            return redirect("accounts:usuario_editar", pk=user.pk)
    else:
        form = UsuarioPerfilForm(**parametros_form)

    return render(request, "accounts/usuario_form.html", {"form": form, "usuario_obj": usuario})


@login_required
@role_required(TipoPerfil.ADMINISTRADOR)
def credenciais_autorizacao(request):
    supervisores = _supervisores_permitidos(request.user)
    empresa = _empresa_do_usuario(request.user)
    acao_form = request.POST.get("acao_form", "") if request.method == "POST" else ""
    politica_form = PoliticaPinSupervisorForm(instance=empresa) if empresa else None

    if request.method == "POST" and acao_form == "politica_pin":
        if not empresa:
            messages.error(request, "Selecione a empresa antes de alterar a política de PIN.")
            return redirect("accounts:credenciais_autorizacao")
        politica_form = PoliticaPinSupervisorForm(request.POST, instance=empresa)
        if politica_form.is_valid():
            politica_form.save()
            LogAuditoria.objects.create(
                usuario=request.user,
                modulo="accounts",
                acao="ALTERA_POLITICA_PIN_SUPERVISOR",
                descricao="Política de cartão e PIN das operações protegidas atualizada.",
                objeto_tipo="Empresa",
                objeto_id=str(empresa.pk),
                ip=request.META.get("REMOTE_ADDR") or None,
            )
            messages.success(request, "Política de cartão e PIN atualizada.")
            return redirect("accounts:credenciais_autorizacao")
        form = CredencialAutorizacaoForm(usuarios_queryset=supervisores)
    elif request.method == "POST":
        form = CredencialAutorizacaoForm(request.POST, usuarios_queryset=supervisores)
        if form.is_valid():
            credencial = form.save(criada_por=request.user)
            LogAuditoria.objects.create(
                usuario=request.user,
                modulo="accounts",
                acao="CRIA_CREDENCIAL_AUTORIZACAO",
                descricao=f"Credencial {credencial.nome} vinculada a {credencial.usuario.username}.",
                objeto_tipo="CredencialAutorizacao",
                objeto_id=str(credencial.pk),
                ip=request.META.get("REMOTE_ADDR") or None,
            )
            messages.success(request, "Credencial cadastrada. O identificador original não foi armazenado.")
            return redirect("accounts:credenciais_autorizacao")
    else:
        form = CredencialAutorizacaoForm(usuarios_queryset=supervisores)

    queryset = _credenciais_visiveis(request.user).annotate(total_usos=Count("usos")).order_by(
        "-ativa", "usuario__username", "nome"
    )
    pagina = Paginator(queryset, 50).get_page(request.GET.get("page"))
    return render(
        request,
        "accounts/credenciais_autorizacao.html",
        {
            "form": form,
            "politica_form": politica_form,
            "page_obj": pagina,
            "credenciais": pagina.object_list,
        },
    )


@login_required
@role_required(TipoPerfil.ADMINISTRADOR)
@require_POST
def credencial_autorizacao_revogar(request, pk):
    credencial = get_object_or_404(_credenciais_visiveis(request.user), pk=pk)
    if credencial.ativa:
        credencial.revogar()
        LogAuditoria.objects.create(
            usuario=request.user,
            modulo="accounts",
            acao="REVOGA_CREDENCIAL_AUTORIZACAO",
            descricao=f"Credencial {credencial.nome} de {credencial.usuario.username} revogada.",
            objeto_tipo="CredencialAutorizacao",
            objeto_id=str(credencial.pk),
            ip=request.META.get("REMOTE_ADDR") or None,
        )
        messages.success(request, "Credencial revogada com sucesso.")
    return redirect("accounts:credenciais_autorizacao")

@login_required
@role_required(TipoPerfil.ADMINISTRADOR)
def recuperacao_senha_diagnostico(request):
    return JsonResponse(diagnostico_prontidao_recuperacao_senha())

