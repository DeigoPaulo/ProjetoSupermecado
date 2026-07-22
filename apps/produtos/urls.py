from django.urls import path

from . import views

app_name = "produtos"

urlpatterns = [
    path("", views.ProdutoListView.as_view(), name="lista"),
    path("novo/", views.ProdutoCreateView.as_view(), name="novo"),
    path("importar-csv/", views.importar_csv, name="importar_csv"),
    path("reajustar-precos/", views.reajustar_precos, name="reajustar_precos"),
    path("etiquetas/", views.etiquetas, name="etiquetas"),
    path("categorias/busca.json", views.categorias_busca, name="categorias_busca"),
    path("marcas/busca.json", views.marcas_busca, name="marcas_busca"),
    path("<int:pk>/kardex/", views.kardex, name="kardex"),
    path("<int:pk>/editar/", views.ProdutoUpdateView.as_view(), name="editar"),
    path("categorias/nova/", views.CategoriaCreateView.as_view(), name="categoria_nova"),
    path("marcas/nova/", views.MarcaCreateView.as_view(), name="marca_nova"),
]
