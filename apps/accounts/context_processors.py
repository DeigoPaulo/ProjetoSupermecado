from .permissions import access_flags


def supermarket_access(request):
    access = access_flags(request.user)
    pdv_nuvem_pendentes = 0
    pdv_cash_drawer_action = None
    if getattr(request, "session", None):
        pdv_cash_drawer_action = request.session.pop("pdv_cash_drawer_action", None)
    if access.get("sistema"):
        try:
            from apps.pdv.models import AcessoPdvNuvem, StatusAcessoPdvNuvem

            pdv_nuvem_pendentes = AcessoPdvNuvem.objects.filter(status=StatusAcessoPdvNuvem.PENDENTE).count()
        except Exception:
            pdv_nuvem_pendentes = 0
    return {
        "access": access,
        "pdv_nuvem_pendentes": pdv_nuvem_pendentes,
        "pdv_cash_drawer_action": pdv_cash_drawer_action,
    }
