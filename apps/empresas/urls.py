from django.urls import path

from . import views

app_name = "empresas"

urlpatterns = [
    path("api/sincronizacao/eventos/", views.receber_evento_sincronizacao, name="receber_evento_sincronizacao"),
    path("", views.empresas, name="lista"),
    path("filiais/busca.json", views.filiais_busca, name="filiais_busca"),
    path("consulta-cadastro.json", views.consulta_cadastro_placeholder, name="consulta_cadastro"),
    path("sincronizacao/", views.sincronizacao, name="sincronizacao"),
    path("sincronizacao/diagnostico.json", views.sincronizacao_diagnostico, name="sincronizacao_diagnostico"),
    path("sincronizacao/vendas.csv", views.vendas_sincronizadas_csv, name="vendas_sincronizadas_csv"),
    path("sincronizacao/documentos-fiscais.csv", views.documentos_fiscais_sincronizados_csv, name="documentos_fiscais_sincronizados_csv"),
    path("sincronizacao/eventos.csv", views.eventos_sincronizacao_csv, name="eventos_sincronizacao_csv"),
    path("sincronizacao/entrada.csv", views.eventos_entrada_sincronizacao_csv, name="eventos_entrada_sincronizacao_csv"),
    path("sincronizacao/vendas/<int:pk>/", views.venda_sincronizada_detalhe, name="venda_sincronizada_detalhe"),
    path("sincronizacao/documentos-fiscais/<int:pk>/", views.documento_fiscal_sincronizado_detalhe, name="documento_fiscal_sincronizado_detalhe"),
    path("sincronizacao/eventos/<int:pk>/", views.evento_sincronizacao_detalhe, name="evento_sincronizacao_detalhe"),
    path("sincronizacao/entrada/<int:pk>/", views.evento_entrada_sincronizacao_detalhe, name="evento_entrada_sincronizacao_detalhe"),
    path("sincronizacao/entrada/<int:pk>/resolver-conflito/", views.sincronizacao_entrada_resolver_conflito, name="sincronizacao_entrada_resolver_conflito"),
    path("sincronizacao/<int:pk>/reprocessar/", views.sincronizacao_reprocessar, name="sincronizacao_reprocessar"),
    path("sincronizacao/entrada/<int:pk>/reprocessar/", views.sincronizacao_entrada_reprocessar, name="sincronizacao_entrada_reprocessar"),
    path("nova/", views.empresa_form, name="empresa_nova"),
    path("<int:pk>/editar/", views.empresa_form, name="empresa_editar"),
    path("filiais/nova/", views.filial_form, name="filial_nova"),
    path("filiais/<int:pk>/editar/", views.filial_form, name="filial_editar"),
]
