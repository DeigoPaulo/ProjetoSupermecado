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
    path("receitas-desmembramento/", views.ReceitaDesmembramentoListView.as_view(), name="receitas_desmembramento"),
    path("receitas-desmembramento/nova/", views.ReceitaDesmembramentoCreateView.as_view(), name="receita_desmembramento_nova"),
    path("receitas-desmembramento/<int:pk>.json", views.receita_desmembramento_json, name="receita_desmembramento_json"),
    path("receitas-desmembramento/<int:pk>/editar/", views.ReceitaDesmembramentoUpdateView.as_view(), name="receita_desmembramento_editar"),
    path("produtos/busca.json", views.produtos_busca, name="produtos_busca"),
    path("composicoes/", views.ComposicaoProdutoListView.as_view(), name="composicoes"),
    path("composicoes/nova/", views.composicao_nova, name="composicao_nova"),
    path("composicoes/<int:pk>/", views.composicao_detalhe, name="composicao_detalhe"),
    path("composicoes/<int:pk>/editar/", views.composicao_editar, name="composicao_editar"),
    path("composicoes/<int:pk>/produzir/", views.composicao_produzir, name="composicao_produzir"),
    path("composicoes/producoes/<int:pk>/cancelar/", views.composicao_cancelar_producao, name="composicao_cancelar_producao"),
    path("desmembramentos/", views.DesmembramentoProdutoListView.as_view(), name="desmembramentos"),
    path("desmembramentos/exportar.csv", views.desmembramentos_csv, name="desmembramentos_csv"),
    path("desmembramentos/relatorio/", views.desmembramento_relatorio, name="desmembramento_relatorio"),
    path("desmembramentos/relatorio/exportar.csv", views.desmembramento_relatorio_csv, name="desmembramento_relatorio_csv"),
    path("desmembramentos/novo/", views.desmembramento_novo, name="desmembramento_novo"),
    path("desmembramentos/<int:pk>/", views.desmembramento_detalhe, name="desmembramento_detalhe"),
    path("desmembramentos/<int:pk>/cancelar/", views.desmembramento_cancelar, name="desmembramento_cancelar"),
]
