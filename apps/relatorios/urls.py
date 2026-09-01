from django.urls import path

from . import views

app_name = "relatorios"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("vendas/", views.vendas, name="vendas"),
    path("vendas/exportar.csv", views.vendas_csv, name="vendas_csv"),
    path("vendas/imprimir/", views.vendas_imprimir, name="vendas_imprimir"),
    path("curva-abc/", views.curva_abc, name="curva_abc"),
    path("curva-abc/exportar.csv", views.curva_abc_csv, name="curva_abc_csv"),
    path("curva-abc/imprimir/", views.curva_abc_imprimir, name="curva_abc_imprimir"),
    path("estoque-baixo/", views.estoque_baixo, name="estoque_baixo"),
    path("estoque-baixo/exportar.csv", views.estoque_baixo_csv, name="estoque_baixo_csv"),
    path("estoque-baixo/imprimir/", views.estoque_baixo_imprimir, name="estoque_baixo_imprimir"),
    path("sugestao-reposicao/", views.sugestao_reposicao, name="sugestao_reposicao"),
    path("sugestao-reposicao/criar-cotacao/", views.criar_cotacao_sugestao_reposicao, name="criar_cotacao_sugestao_reposicao"),
    path("sugestao-reposicao/exportar.csv", views.sugestao_reposicao_csv, name="sugestao_reposicao_csv"),
    path("sugestao-reposicao/imprimir/", views.sugestao_reposicao_imprimir, name="sugestao_reposicao_imprimir"),
    path("movimentacoes-estoque/", views.movimentacoes_estoque, name="movimentacoes_estoque"),
    path("movimentacoes-estoque/exportar.csv", views.movimentacoes_estoque_csv, name="movimentacoes_estoque_csv"),
    path("movimentacoes-estoque/imprimir/", views.movimentacoes_estoque_imprimir, name="movimentacoes_estoque_imprimir"),
    path("perdas/", views.perdas, name="perdas"),
    path("perdas/exportar.csv", views.perdas_csv, name="perdas_csv"),
    path("perdas/imprimir/", views.perdas_imprimir, name="perdas_imprimir"),
    path("devolucoes/", views.devolucoes, name="devolucoes"),
    path("devolucoes/exportar.csv", views.devolucoes_csv, name="devolucoes_csv"),
    path("devolucoes/imprimir/", views.devolucoes_imprimir, name="devolucoes_imprimir"),
    path("relatorios/compras/", views.compras, name="compras"),
    path("relatorios/compras/exportar.csv", views.compras_csv, name="compras_csv"),
    path("relatorios/compras/imprimir/", views.compras_imprimir, name="compras_imprimir"),
    path("caixas/", views.caixas, name="caixas"),
    path("caixas/exportar.csv", views.caixas_csv, name="caixas_csv"),
    path("caixas/imprimir/", views.caixas_imprimir, name="caixas_imprimir"),
]
