from django.urls import path

from . import views

app_name = "relatorios"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("vendas/", views.vendas, name="vendas"),
    path("estoque-baixo/", views.estoque_baixo, name="estoque_baixo"),
    path("movimentacoes-estoque/", views.movimentacoes_estoque, name="movimentacoes_estoque"),
    path("perdas/", views.perdas, name="perdas"),
    path("compras/", views.compras, name="compras"),
    path("caixas/", views.caixas, name="caixas"),
]
