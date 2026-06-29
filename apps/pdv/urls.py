from django.urls import path

from . import views

app_name = "pdv"

urlpatterns = [
    path("", views.pdv, name="pdv"),
    path("item/remover/<int:produto_id>/", views.remover_item, name="remover_item"),
    path("carrinho/limpar/", views.limpar_carrinho, name="limpar_carrinho"),
    path("vendas/<int:venda_id>/", views.venda_detalhe, name="venda_detalhe"),
    path("vendas/<int:venda_id>/recibo/", views.recibo_venda, name="recibo_venda"),
    path("vendas/<int:venda_id>/cancelar/", views.cancelar_venda_view, name="cancelar_venda"),
    path("caixas/", views.CaixaListView.as_view(), name="caixas"),
    path("caixas/abrir/", views.AbrirCaixaView.as_view(), name="abrir_caixa"),
    path("caixas/<int:caixa_id>/", views.caixa_detalhe, name="caixa_detalhe"),
    path("caixas/<int:caixa_id>/sangria/", views.registrar_sangria, name="registrar_sangria"),
    path("caixas/<int:caixa_id>/suprimento/", views.registrar_suprimento, name="registrar_suprimento"),
    path("caixas/<int:caixa_id>/fechar/", views.fechar_caixa, name="fechar_caixa"),
]
