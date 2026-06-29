from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("", views.UsuarioListView.as_view(), name="usuarios"),
    path("novo/", views.usuario_form, name="usuario_novo"),
    path("<int:pk>/editar/", views.usuario_form, name="usuario_editar"),
]
