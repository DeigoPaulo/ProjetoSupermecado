from django.urls import path

from . import views

app_name = "marketplace"

urlpatterns = [
    path("", views.pedidos, name="pedidos"),
    path("novo/", views.novo_pedido, name="novo"),
    path("integracoes/", views.integracoes, name="integracoes"),
    path("integracoes/nova/", views.nova_integracao, name="nova_integracao"),
    path("integracoes/<int:pk>/renovar/", views.renovar_token, name="renovar_token"),
    path("politicas-entrega/", views.politicas_entrega, name="politicas_entrega"),
    path("politicas-entrega/nova/", views.politica_entrega_form, name="nova_politica_entrega"),
    path("politicas-entrega/<int:pk>/editar/", views.politica_entrega_form, name="editar_politica_entrega"),
    path("api/pedidos/", views.api_receber_pedido, name="api_receber_pedido"),
    path("<int:pk>/", views.detalhe, name="detalhe"),
    path("<int:pk>/separacao/imprimir/", views.imprimir_separacao, name="imprimir_separacao"),
    path("<int:pk>/acao/", views.acao_pedido, name="acao"),
    path("<int:pk>/itens/<int:item_id>/remover/", views.remover_item, name="remover_item"),
]
