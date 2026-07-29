from .models import Cliente


def empresa_id_do_usuario(user):
    if not getattr(user, "is_authenticated", False) or user.is_superuser:
        return None
    perfil = getattr(user, "perfil_supermercado", None)
    if perfil and perfil.is_active and perfil.filial_id:
        return perfil.filial.empresa_id
    return 0


def clientes_para_usuario(user, queryset=None):
    queryset = queryset if queryset is not None else Cliente.objects.all()
    empresa_id = empresa_id_do_usuario(user)
    if empresa_id is None:
        return queryset
    return queryset.filter(empresa_id=empresa_id)