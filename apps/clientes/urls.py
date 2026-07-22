from django.urls import path

from . import views

app_name = "clientes"

urlpatterns = [
    path("", views.ClienteListView.as_view(), name="lista"),
    path("busca.json", views.clientes_busca, name="clientes_busca"),
    path("novo/", views.ClienteCreateView.as_view(), name="novo"),
    path("<int:pk>/editar/", views.ClienteUpdateView.as_view(), name="editar"),
]
