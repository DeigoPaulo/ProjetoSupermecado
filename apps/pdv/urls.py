from django.urls import path

from . import views

app_name = "pdv"

urlpatterns = [
    path("api/terminal/bootstrap/", views.terminal_bootstrap, name="terminal_bootstrap"),
    path("", views.pdv, name="pdv"),
    path("consulta-preco/", views.consulta_preco, name="consulta_preco"),
    path("acessos-nuvem/", views.acessos_pdv_nuvem, name="acessos_pdv_nuvem"),
    path("acessos-nuvem/<int:acesso_id>/decidir/", views.decidir_acesso_pdv_nuvem_view, name="decidir_acesso_pdv_nuvem"),
    path("item/remover/<int:produto_id>/", views.remover_item, name="remover_item"),
    path("carrinho/limpar/", views.limpar_carrinho, name="limpar_carrinho"),
    path("pre-vendas/", views.PreVendaListView.as_view(), name="pre_vendas"),
    path("pre-vendas/<int:pre_venda_id>/", views.pre_venda_detalhe, name="pre_venda_detalhe"),
    path("pre-vendas/<int:pre_venda_id>/recibo/", views.recibo_pre_venda, name="recibo_pre_venda"),
    path("pre-vendas/<int:pre_venda_id>/carregar/", views.carregar_pre_venda, name="carregar_pre_venda"),
    path("pre-vendas/<int:pre_venda_id>/cancelar/", views.cancelar_pre_venda_view, name="cancelar_pre_venda"),
    path("vendas/<int:venda_id>/", views.venda_detalhe, name="venda_detalhe"),
    path("vendas/<int:venda_id>/devolver/", views.devolver_venda, name="devolver_venda"),
    path("vendas/<int:venda_id>/recibo/", views.recibo_venda, name="recibo_venda"),
    path("vendas/<int:venda_id>/impressao-desktop.json", views.venda_impressao_desktop, name="venda_impressao_desktop"),
    path("vendas/<int:venda_id>/cancelar/", views.cancelar_venda_view, name="cancelar_venda"),
    path("caixas/", views.CaixaListView.as_view(), name="caixas"),
    path("caixas/abrir/", views.AbrirCaixaView.as_view(), name="abrir_caixa"),
    path("caixas/<int:caixa_id>/", views.caixa_detalhe, name="caixa_detalhe"),
    path("caixas/<int:caixa_id>/sangria/", views.registrar_sangria, name="registrar_sangria"),
    path("caixas/<int:caixa_id>/suprimento/", views.registrar_suprimento, name="registrar_suprimento"),
    path("caixas/<int:caixa_id>/fechar/", views.fechar_caixa, name="fechar_caixa"),
    path("caixas/<int:caixa_id>/conferir/", views.conferir_caixa, name="conferir_caixa"),
]
