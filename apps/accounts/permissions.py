from django.contrib.auth import authenticate
from django.contrib.auth.mixins import UserPassesTestMixin
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied, ValidationError

from .models import TipoPerfil


SUPERVISAO = {TipoPerfil.ADMINISTRADOR, TipoPerfil.GERENTE}
PDV = SUPERVISAO | {TipoPerfil.OPERADOR_CAIXA}
CADASTROS = SUPERVISAO | {TipoPerfil.ESTOQUISTA, TipoPerfil.COMPRAS}
CLIENTES = PDV | CADASTROS
ESTOQUE = SUPERVISAO | {TipoPerfil.ESTOQUISTA, TipoPerfil.COMPRAS}
COMPRAS = SUPERVISAO | {TipoPerfil.COMPRAS}
RELATORIOS = SUPERVISAO | {TipoPerfil.FINANCEIRO}
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


def supervisor_from_request(request):
    username = request.POST.get("supervisor_usuario", "").strip()
    password = request.POST.get("supervisor_senha", "")
    if not username or not password:
        raise ValidationError("Informe usuario e senha do supervisor.")
    usuario = authenticate(request, username=username, password=password)
    if not usuario or not usuario.is_active:
        raise ValidationError("Credenciais de supervisor invalidas.")
    if has_role(usuario, SUPERVISAO):
        return usuario
    raise ValidationError("Usuario informado nao tem permissao de supervisor.")


def access_flags(user):
    return {
        "supervisao": has_role(user, SUPERVISAO),
        "pdv": has_role(user, PDV),
        "cadastros": has_role(user, CADASTROS),
        "clientes": has_role(user, CLIENTES),
        "estoque": has_role(user, ESTOQUE),
        "compras": has_role(user, COMPRAS),
        "relatorios": has_role(user, RELATORIOS),
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
