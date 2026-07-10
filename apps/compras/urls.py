from django.urls import path

from . import views

app_name = "compras"

urlpatterns = [
    path("", views.EntradaCompraListView.as_view(), name="lista"),
    path("exportar.csv", views.entradas_csv, name="csv"),
    path("imprimir/", views.entradas_imprimir, name="imprimir"),
    path("nova/", views.EntradaCompraCreateView.as_view(), name="nova"),
    path("<int:pk>/", views.EntradaCompraDetailView.as_view(), name="detalhe"),
    path("<int:pk>/imprimir/", views.entrada_imprimir, name="detalhe_imprimir"),
    path("<int:pk>/editar/", views.EntradaCompraUpdateView.as_view(), name="editar"),
    path("<int:pk>/finalizar/", views.finalizar_entrada, name="finalizar"),
    path("<int:pk>/cancelar/", views.cancelar_entrada, name="cancelar"),
]
