from django.urls import path

from . import views

app_name = "compras"

urlpatterns = [
    path("", views.EntradaCompraListView.as_view(), name="lista"),
    path("cotacoes/", views.cotacoes_compra_lista, name="cotacoes"),
    path("cotacoes/nova/", views.cotacao_compra_form, name="cotacao_nova"),
    path("cotacoes/<int:pk>/", views.cotacao_compra_detalhe, name="cotacao_detalhe"),
    path("cotacoes/<int:pk>/editar/", views.cotacao_compra_form, name="cotacao_editar"),
    path("cotacoes/<int:pk>/abrir/", views.cotacao_compra_abrir, name="cotacao_abrir"),
    path("cotacoes/<int:pk>/proposta/", views.cotacao_resposta_form, name="cotacao_resposta"),
    path("cotacoes/<int:pk>/propostas/<int:resposta_pk>/selecionar/", views.cotacao_selecionar_resposta, name="cotacao_selecionar"),
    path("pedidos/", views.pedidos_compra_lista, name="pedidos"),
    path("pedidos/novo/", views.pedido_compra_form, name="pedido_novo"),
    path("pedidos/<int:pk>/", views.pedido_compra_detalhe, name="pedido_detalhe"),
    path("pedidos/<int:pk>/editar/", views.pedido_compra_form, name="pedido_editar"),
    path("pedidos/<int:pk>/enviar/", views.pedido_compra_enviar, name="pedido_enviar"),
    path("pedidos/<int:pk>/gerar-entrada/", views.pedido_compra_gerar_entrada, name="pedido_gerar_entrada"),
    path("pedidos/<int:pk>/cancelar/", views.pedido_compra_cancelar, name="pedido_cancelar"),
    path("exportar.csv", views.entradas_csv, name="csv"),
    path("imprimir/", views.entradas_imprimir, name="imprimir"),
    path("importar-xml/", views.importar_xml, name="importar_xml"),
    path("nova/", views.EntradaCompraCreateView.as_view(), name="nova"),
    path("<int:pk>/", views.EntradaCompraDetailView.as_view(), name="detalhe"),
    path("<int:pk>/imprimir/", views.entrada_imprimir, name="detalhe_imprimir"),
    path("<int:pk>/editar/", views.EntradaCompraUpdateView.as_view(), name="editar"),
    path("<int:pk>/finalizar/", views.finalizar_entrada, name="finalizar"),
    path("<int:pk>/vincular-pedido-xml/", views.vincular_xml_pedido_manual, name="vincular_xml_pedido_manual"),
    path("<int:pk>/confirmar-conferencia-fisica/", views.confirmar_conferencia_fisica_entrada, name="confirmar_conferencia_fisica"),
    path("<int:pk>/cancelar/", views.cancelar_entrada, name="cancelar"),
    path("<int:pk>/excluir-rascunho/", views.excluir_rascunho, name="excluir_rascunho"),
]
