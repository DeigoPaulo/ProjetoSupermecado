from django.urls import path

from . import views

app_name = "licenciamento"

urlpatterns = [
    path("", views.minha_licenca, name="minha_licenca"),
    path("central/", views.central_licencas, name="central"),
    path("central/diagnostico.json", views.central_diagnostico, name="central_diagnostico"),
    path("central/planos/novo/", views.plano_novo, name="plano_novo"),
    path("central/contratos/novo/", views.contrato_novo, name="contrato_novo"),
    path("central/instalacoes/nova/", views.instalacao_nova, name="instalacao_nova"),
    path("central/contratos/<int:pk>/gerar-fatura/", views.gerar_fatura, name="gerar_fatura"),
    path("central/liberacao-emergencial/", views.emitir_liberacao_emergencial, name="emitir_emergencial"),
    path("contingencia/gerar-desafio/", views.gerar_desafio_emergencial, name="gerar_desafio_emergencial"),
    path("contingencia/aplicar/", views.aplicar_liberacao_emergencial, name="aplicar_emergencial"),
    path("api/v1/renovar/", views.api_renovar_licenca, name="api_renovar"),
    path("webhooks/asaas/", views.webhook_asaas, name="webhook_asaas"),
]