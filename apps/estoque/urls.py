from django.urls import path

from . import views

app_name = "estoque"

urlpatterns = [
    path("", views.EstoqueListView.as_view(), name="lista"),
    path("movimentar/", views.movimentar, name="movimentar"),
    path("inventarios/", views.InventarioListView.as_view(), name="inventarios"),
    path("inventarios/novo/", views.CriarInventarioView.as_view(), name="inventario_novo"),
    path("inventarios/<int:pk>/", views.inventario_detalhe, name="inventario_detalhe"),
    path("inventarios/<int:pk>/itens/novo/", views.adicionar_item_inventario, name="inventario_item_novo"),
    path("inventarios/<int:pk>/aplicar/", views.aplicar_inventario_view, name="inventario_aplicar"),
    path("perdas/", views.PerdaEstoqueListView.as_view(), name="perdas"),
    path("perdas/nova/", views.registrar_perda, name="perda_nova"),
]
