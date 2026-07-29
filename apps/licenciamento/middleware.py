from django.shortcuts import redirect, render
from django.urls import reverse

from apps.accounts.models import TipoPerfil

from .models import EstadoLicencaLocal


class ControleLicencaMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated or user.is_superuser:
            return self.get_response(request)
        perfil = getattr(user, "perfil_supermercado", None)
        if not perfil or not perfil.is_active or not perfil.filial_id:
            return self.get_response(request)
        estado = EstadoLicencaLocal.objects.filter(empresa_id=perfil.filial.empresa_id).first()
        if not estado or not estado.bloqueado:
            return self.get_response(request)

        rotas_livres = {
            reverse("logout"),
            reverse("licenciamento:minha_licenca"),
            reverse("licenciamento:gerar_desafio_emergencial"),
            reverse("licenciamento:aplicar_emergencial"),
            reverse("password_change") if _rota_existe("password_change") else "",
        }
        if request.path in rotas_livres or request.path.startswith("/static/") or request.path.startswith("/media/"):
            return self.get_response(request)
        if perfil.tipo == TipoPerfil.ADMINISTRADOR:
            return redirect("licenciamento:minha_licenca")
        return render(request, "licenciamento/bloqueado.html", {"estado_licenca": estado}, status=402)


def _rota_existe(nome):
    try:
        reverse(nome)
        return True
    except Exception:
        return False