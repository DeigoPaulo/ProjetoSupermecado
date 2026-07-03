from django.urls import path

from . import views

app_name = "empresas"

urlpatterns = [
    path("api/sincronizacao/eventos/", views.receber_evento_sincronizacao, name="receber_evento_sincronizacao"),
    path("", views.empresas, name="lista"),
    path("consulta-cadastro.json", views.consulta_cadastro_placeholder, name="consulta_cadastro"),
    path("sincronizacao/", views.sincronizacao, name="sincronizacao"),
    path("sincronizacao/<int:pk>/reprocessar/", views.sincronizacao_reprocessar, name="sincronizacao_reprocessar"),
    path("sincronizacao/entrada/<int:pk>/reprocessar/", views.sincronizacao_entrada_reprocessar, name="sincronizacao_entrada_reprocessar"),
    path("nova/", views.empresa_form, name="empresa_nova"),
    path("<int:pk>/editar/", views.empresa_form, name="empresa_editar"),
    path("filiais/nova/", views.filial_form, name="filial_nova"),
    path("filiais/<int:pk>/editar/", views.filial_form, name="filial_editar"),
]
