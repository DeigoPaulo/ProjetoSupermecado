from .models import EstadoLicencaLocal, StatusContrato


def alerta_licenciamento(request):
    if not request.user.is_authenticated or request.user.is_superuser:
        return {"alerta_licenca": None}
    perfil = getattr(request.user, "perfil_supermercado", None)
    if not perfil or not perfil.is_active or not perfil.filial_id:
        return {"alerta_licenca": None}
    estado = EstadoLicencaLocal.objects.filter(empresa_id=perfil.filial.empresa_id).first()
    if not estado or (estado.status == StatusContrato.ATIVO and not estado.bloqueado):
        return {"alerta_licenca": None}
    return {
        "alerta_licenca": {
            "status": estado.status,
            "mensagem": estado.mensagem_operacional,
            "valor": estado.valor_pendente,
            "vencimento": estado.proxima_fatura_vencimento,
            "url_pagamento": estado.url_pagamento,
            "bloqueado": estado.bloqueado,
        }
    }