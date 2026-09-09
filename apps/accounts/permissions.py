from django.contrib.auth import authenticate
from django.contrib.auth.mixins import UserPassesTestMixin
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from apps.empresas.models import AcaoPinSupervisor, acoes_pin_supervisor_padrao

from .models import CredencialAutorizacao, TipoPerfil, UsoCredencialAutorizacao


ADMINISTRACAO = {TipoPerfil.ADMINISTRADOR}
SUPERVISAO = ADMINISTRACAO | {TipoPerfil.GERENTE}
PDV = SUPERVISAO | {TipoPerfil.OPERADOR_CAIXA}
CADASTROS = SUPERVISAO | {TipoPerfil.ESTOQUISTA, TipoPerfil.COMPRAS}
CLIENTES = PDV | CADASTROS
ESTOQUE = SUPERVISAO | {TipoPerfil.ESTOQUISTA, TipoPerfil.COMPRAS}
COMPRAS = SUPERVISAO | {TipoPerfil.COMPRAS}
RELATORIOS = SUPERVISAO | {TipoPerfil.FINANCEIRO}
CONTABILIDADE = ADMINISTRACAO | {TipoPerfil.FINANCEIRO, TipoPerfil.CONTABILIDADE}
REVISAO_FISCAL = ADMINISTRACAO | {TipoPerfil.CONTABILIDADE}
SISTEMA = SUPERVISAO


def _tipo_perfil(user):
    if not user.is_authenticated:
        return None
    if user.is_superuser:
        return TipoPerfil.ADMINISTRADOR
    perfil = getattr(user, "perfil_supermercado", None)
    if perfil and perfil.is_active:
        return perfil.tipo
    return None


def has_role(user, roles):
    tipo = _tipo_perfil(user)
    return bool(tipo and tipo in roles)


def _validar_empresa_supervisor(request, usuario):
    if request.user.is_superuser or usuario.is_superuser:
        return
    perfil_operador = getattr(request.user, "perfil_supermercado", None)
    perfil_supervisor = getattr(usuario, "perfil_supermercado", None)
    empresa_operador_id = (
        perfil_operador.filial.empresa_id
        if perfil_operador and perfil_operador.is_active and perfil_operador.filial_id
        else None
    )
    empresa_supervisor_id = (
        perfil_supervisor.filial.empresa_id
        if perfil_supervisor and perfil_supervisor.is_active and perfil_supervisor.filial_id
        else None
    )
    if not empresa_operador_id or empresa_operador_id != empresa_supervisor_id:
        raise ValidationError("O supervisor deve pertencer à mesma empresa do operador.")


def _acao_exige_pin(request, acao):
    if not acao:
        return False
    perfil = getattr(request.user, "perfil_supermercado", None)
    empresa = perfil.filial.empresa if perfil and perfil.is_active and perfil.filial_id else None
    if empresa:
        return empresa.exige_pin_supervisor(acao)
    return acao in acoes_pin_supervisor_padrao()


def supervisor_from_request(request, *, acao=""):
    if acao and acao not in AcaoPinSupervisor.values:
        raise ValidationError("Ação de autorização inválida.")
    identificador = request.POST.get("supervisor_credencial", "").strip()
    credencial = None
    if identificador:
        identificador_hash = CredencialAutorizacao.calcular_hash(identificador)
        credencial = CredencialAutorizacao.objects.select_related(
            "usuario", "usuario__perfil_supermercado", "usuario__perfil_supermercado__filial"
        ).filter(identificador_hash=identificador_hash).first()
        if not credencial or not credencial.vigente:
            raise ValidationError("Credencial de supervisor inválida, expirada ou revogada.")
        pin = request.POST.get("supervisor_pin", "")
        if _acao_exige_pin(request, acao) and not credencial.pin_hash:
            raise ValidationError("Esta operação exige uma credencial cadastrada com PIN.")
        if not credencial.validar_pin(pin):
            raise ValidationError("PIN da credencial de supervisor inválido.")
        usuario = credencial.usuario
    else:
        username = request.POST.get("supervisor_usuario", "").strip()
        password = request.POST.get("supervisor_senha", "")
        if not username or not password:
            raise ValidationError("Informe usuário e senha ou leia a credencial do supervisor.")
        usuario = authenticate(request, username=username, password=password)
        if not usuario or not usuario.is_active:
            raise ValidationError("Credenciais de supervisor inválidas.")

    if not usuario.is_active:
        raise ValidationError("Credenciais de supervisor inválidas.")
    if not has_role(usuario, SUPERVISAO):
        raise ValidationError("Usuário informado não tem permissão de supervisor.")
    _validar_empresa_supervisor(request, usuario)

    if credencial:
        agora = timezone.now()
        CredencialAutorizacao.objects.filter(pk=credencial.pk).update(ultimo_uso_em=agora)
        UsoCredencialAutorizacao.objects.create(
            credencial=credencial,
            acao=acao,
            supervisor=usuario,
            operador=request.user if request.user.is_authenticated else None,
            caminho=request.path[:255],
            ip=request.META.get("REMOTE_ADDR") or None,
        )
    return usuario


def access_flags(user):
    return {
        "administracao": has_role(user, ADMINISTRACAO),
        "supervisao": has_role(user, SUPERVISAO),
        "pdv": has_role(user, PDV),
        "cadastros": has_role(user, CADASTROS),
        "clientes": has_role(user, CLIENTES),
        "estoque": has_role(user, ESTOQUE),
        "compras": has_role(user, COMPRAS),
        "relatorios": has_role(user, RELATORIOS),
        "contabilidade": has_role(user, CONTABILIDADE),
        "revisao_fiscal": has_role(user, REVISAO_FISCAL),
        "sistema": has_role(user, SISTEMA),
    }


def role_required(*roles):
    allowed = set(roles)

    def decorator(view_func):
        def wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if not has_role(request.user, allowed):
                raise PermissionDenied
            return view_func(request, *args, **kwargs)

        return wrapped

    return decorator


class RoleRequiredMixin(UserPassesTestMixin):
    required_roles = set()
    raise_exception = True

    def test_func(self):
        return has_role(self.request.user, self.required_roles)
