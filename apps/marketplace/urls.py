from django.urls import path

from . import views

app_name = "marketplace"

urlpatterns = [
    path("", views.pedidos, name="pedidos"),
    path("novo/", views.novo_pedido, name="novo"),
    path("integracoes/", views.integracoes, name="integracoes"),
    path("integracoes/diagnostico.json", views.integracoes_diagnostico, name="integracoes_diagnostico"),
    path("integracoes/nova/", views.nova_integracao, name="nova_integracao"),
    path("integracoes/<int:pk>/renovar/", views.renovar_token, name="renovar_token"),
    path("politicas-entrega/", views.politicas_entrega, name="politicas_entrega"),
    path("politicas-entrega/diagnostico.json", views.politicas_entrega_diagnostico, name="politicas_entrega_diagnostico"),
    path("politicas-entrega/nova/", views.politica_entrega_form, name="nova_politica_entrega"),
    path("politicas-entrega/<int:pk>/editar/", views.politica_entrega_form, name="editar_politica_entrega"),
    path("api/status/", views.api_status_integracao, name="api_status_integracao"),
    path("api/pedidos/", views.api_receber_pedido, name="api_receber_pedido"),
    path("<int:pk>/", views.detalhe, name="detalhe"),
    path("<int:pk>/separacao/imprimir/", views.imprimir_separacao, name="imprimir_separacao"),
    path("<int:pk>/separacao/impressao-desktop.json", views.impressao_separacao_desktop, name="impressao_separacao_desktop"),
    path("<int:pk>/acao/", views.acao_pedido, name="acao"),
    path("<int:pk>/itens/<int:item_id>/remover/", views.remover_item, name="remover_item"),
]
