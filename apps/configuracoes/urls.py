from django.urls import path

from . import views

app_name = "configuracoes"

urlpatterns = [
    path("checklist/", views.checklist_projeto, name="checklist"),
    path("backup/", views.backup_operacional, name="backup"),
    path("backup/download/", views.backup_download, name="backup_download"),
    path("impressoes/", views.impressoes, name="impressoes"),
    path("impressoes/padroes/", views.impressoes_padroes, name="impressoes_padroes"),
    path("impressoes/nova/", views.impressao_form, name="impressao_nova"),
    path("impressoes/<int:pk>/editar/", views.impressao_form, name="impressao_editar"),
]
