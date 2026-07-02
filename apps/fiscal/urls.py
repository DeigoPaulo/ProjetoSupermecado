from django.urls import path

from . import views

app_name = "fiscal"

urlpatterns = [
    path("", views.documentos, name="documentos"),
    path("produtos/", views.produtos_fiscais, name="produtos_fiscais"),
    path("configuracoes/nova/", views.configuracao_form, name="configuracao_nova"),
    path("configuracoes/<int:pk>/editar/", views.configuracao_form, name="configuracao_editar"),
    path("series/nova/", views.serie_form, name="serie_nova"),
    path("series/<int:pk>/editar/", views.serie_form, name="serie_editar"),
    path("naturezas/nova/", views.natureza_form, name="natureza_nova"),
    path("naturezas/<int:pk>/editar/", views.natureza_form, name="natureza_editar"),
    path("vendas/<int:venda_id>/preparar/", views.preparar_venda, name="preparar_venda"),
    path("documentos/<int:pk>/", views.detalhe, name="detalhe"),
    path("documentos/<int:pk>/imprimir/", views.imprimir, name="imprimir"),
    path("documentos/<int:pk>/xml/", views.baixar_xml, name="baixar_xml"),
    path("documentos/<int:pk>/cancelar/", views.cancelar, name="cancelar"),
]
