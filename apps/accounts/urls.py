from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("", views.UsuarioListView.as_view(), name="usuarios"),
    path("novo/", views.usuario_form, name="usuario_novo"),
    path("credenciais-autorizacao/", views.credenciais_autorizacao, name="credenciais_autorizacao"),
    path("credenciais-autorizacao/<int:pk>/revogar/", views.credencial_autorizacao_revogar, name="credencial_autorizacao_revogar"),
    path("recuperacao-senha/diagnostico.json", views.recuperacao_senha_diagnostico, name="recuperacao_senha_diagnostico"),
    path("<int:pk>/editar/", views.usuario_form, name="usuario_editar"),
]
