from django.urls import path

from . import views

app_name = "fiscal"

urlpatterns = [
    path("", views.documentos, name="documentos"),
    path("inutilizacoes/", views.inutilizacoes, name="inutilizacoes"),
    path("diagnostico.json", views.diagnostico_json, name="diagnostico_json"),
    path("contingencia.json", views.contingencia_json, name="contingencia_json"),
    path("produtos/", views.produtos_fiscais, name="produtos_fiscais"),
    path(
        "produtos/exportar.csv",
        views.produtos_fiscais_exportar_csv,
        name="produtos_fiscais_exportar_csv",
    ),
    path("configuracoes/nova/", views.configuracao_form, name="configuracao_nova"),
    path("configuracoes/<int:pk>/editar/", views.configuracao_form, name="configuracao_editar"),
    path("series/nova/", views.serie_form, name="serie_nova"),
    path("series/<int:pk>/editar/", views.serie_form, name="serie_editar"),
    path("naturezas/nova/", views.natureza_form, name="natureza_nova"),
    path("naturezas/<int:pk>/editar/", views.natureza_form, name="natureza_editar"),
    path("naturezas/<int:pk>/definir-padrao/", views.definir_natureza_padrao, name="natureza_definir_padrao"),
    path("vendas/<int:venda_id>/preparar/", views.preparar_venda, name="preparar_venda"),
    path("documentos/<int:pk>/", views.detalhe, name="detalhe"),
    path("documentos/<int:pk>/imprimir/", views.imprimir, name="imprimir"),
    path("documentos/<int:pk>/xml/", views.baixar_xml, name="baixar_xml"),
    path("documentos/<int:pk>/reagendar/", views.reagendar_transmissao, name="reagendar_transmissao"),
    path("documentos/<int:pk>/retomar-consultas-sefaz/", views.retomar_consultas_sefaz, name="retomar_consultas_sefaz"),
    path("documentos/<int:pk>/transmitir-simulado/", views.transmitir_simulado, name="transmitir_simulado"),
    path("documentos/<int:pk>/transmitir-sefaz/", views.transmitir_sefaz, name="transmitir_sefaz"),
    path("documentos/<int:pk>/consultar-sefaz/", views.consultar_sefaz, name="consultar_sefaz"),
    path("documentos/<int:pk>/contingencia/", views.ativar_contingencia, name="ativar_contingencia"),
    path("documentos/<int:pk>/cancelar/", views.cancelar, name="cancelar"),
]
