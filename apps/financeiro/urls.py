from django.urls import path

from . import views

app_name = "financeiro"

urlpatterns = [
    path("", views.contas, name="contas"),
    path("exportar.csv", views.contas_csv, name="contas_csv"),
    path("imprimir/", views.contas_imprimir, name="contas_imprimir"),
    path("fluxo-caixa/", views.fluxo_caixa, name="fluxo_caixa"),
    path("fluxo-caixa/exportar.csv", views.fluxo_caixa_csv, name="fluxo_caixa_csv"),
    path("conciliacao/", views.conciliacao, name="conciliacao"),
    path("conciliacao/exportar.csv", views.conciliacao_csv, name="conciliacao_csv"),
    path("resultado/", views.resultado_financeiro, name="resultado"),
    path("resultado/exportar.csv", views.resultado_financeiro_csv, name="resultado_csv"),
    path("contas-movimento/", views.contas_movimento, name="contas_movimento"),
    path("contas-movimento/nova/", views.conta_movimento_form, name="conta_movimento_nova"),
    path("contas-movimento/<int:pk>/editar/", views.conta_movimento_form, name="conta_movimento_editar"),
    path("transferencias/nova/", views.transferencia_form, name="transferencia_nova"),
    path("livro/", views.livro_financeiro, name="livro"),
    path("livro/exportar.csv", views.livro_financeiro_csv, name="livro_csv"),
    path("livro/<int:pk>/estornar/", views.estornar_livro, name="estornar_livro"),
    path("nova/", views.conta_form, name="conta_nova"),
    path("<int:pk>/editar/", views.conta_form, name="conta_editar"),
    path("<int:pk>/baixar/", views.baixar, name="baixar"),
    path("<int:pk>/cancelar/", views.cancelar, name="cancelar"),
    path("categorias/", views.categorias, name="categorias"),
    path("categorias/nova/", views.categoria_form, name="categoria_nova"),
    path("categorias/<int:pk>/editar/", views.categoria_form, name="categoria_editar"),
]
