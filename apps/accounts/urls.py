from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("", views.UsuarioListView.as_view(), name="usuarios"),
    path("novo/", views.usuario_form, name="usuario_novo"),
    path("recuperacao-senha/diagnostico.json", views.recuperacao_senha_diagnostico, name="recuperacao_senha_diagnostico"),
    path("<int:pk>/editar/", views.usuario_form, name="usuario_editar"),
]
