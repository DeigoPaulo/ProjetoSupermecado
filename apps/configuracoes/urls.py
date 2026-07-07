from django.urls import path

from . import views

app_name = "configuracoes"

urlpatterns = [
    path("", views.painel_sistema, name="painel"),
    path("checklist/", views.checklist_projeto, name="checklist"),
    path("backup/", views.backup_operacional, name="backup"),
    path("backup/download/", views.backup_download, name="backup_download"),
    path("pdv-desktop/", views.pdv_desktop, name="pdv_desktop"),
    path("pdv-desktop/manifest.json", views.pdv_desktop_manifest, name="pdv_desktop_manifest"),
    path("pdv-desktop/terminais/<int:pk>/pacote.json", views.pdv_desktop_terminal_pacote, name="pdv_desktop_terminal_pacote"),
    path("formas-pagamento/", views.formas_pagamento, name="formas_pagamento"),
    path("formas-pagamento/nova/", views.forma_pagamento_form, name="forma_pagamento_nova"),
    path("formas-pagamento/<int:pk>/editar/", views.forma_pagamento_form, name="forma_pagamento_editar"),
    path("terminais-pdv/", views.terminais_pdv, name="terminais_pdv"),
    path("terminais-pdv/novo/", views.terminal_pdv_form, name="terminal_pdv_novo"),
    path("terminais-pdv/<int:pk>/editar/", views.terminal_pdv_form, name="terminal_pdv_editar"),
    path("terminais-pdv/<int:pk>/regenerar-chave/", views.terminal_pdv_regenerar_chave, name="terminal_pdv_regenerar_chave"),
    path("impressoes/", views.impressoes, name="impressoes"),
    path("impressoes/impressoras-locais.json", views.impressoras_locais, name="impressoras_locais"),
    path("impressoes/desktop.json", views.impressoes_desktop, name="impressoes_desktop"),
    path("impressoes/padroes/", views.impressoes_padroes, name="impressoes_padroes"),
    path("impressoes/nova/", views.impressao_form, name="impressao_nova"),
    path("impressoes/<int:pk>/editar/", views.impressao_form, name="impressao_editar"),
]
