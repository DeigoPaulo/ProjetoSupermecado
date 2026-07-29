from .permissions import access_flags


def supermarket_access(request):
    access = access_flags(request.user)
    pdv_nuvem_pendentes = 0
    pdv_cash_drawer_action = None
    if getattr(request, "session", None):
        pdv_cash_drawer_action = request.session.pop("pdv_cash_drawer_action", None)
    if access.get("administracao"):
        try:
            from apps.pdv.models import AcessoPdvNuvem, StatusAcessoPdvNuvem

            acessos = AcessoPdvNuvem.objects.filter(status=StatusAcessoPdvNuvem.PENDENTE)
            if not request.user.is_superuser:
                perfil = getattr(request.user, "perfil_supermercado", None)
                empresa_id = perfil.filial.empresa_id if perfil and perfil.is_active and perfil.filial_id else 0
                acessos = acessos.filter(filial__empresa_id=empresa_id) if empresa_id else acessos.none()
            pdv_nuvem_pendentes = acessos.count()
        except Exception:
            pdv_nuvem_pendentes = 0
    return {
        "access": access,
        "pdv_nuvem_pendentes": pdv_nuvem_pendentes,
        "pdv_cash_drawer_action": pdv_cash_drawer_action,
    }
