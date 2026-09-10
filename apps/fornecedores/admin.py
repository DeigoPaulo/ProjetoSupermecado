from django.contrib import admin

from .models import Fornecedor


@admin.register(Fornecedor)
class FornecedorAdmin(admin.ModelAdmin):
    list_display = (
        "empresa", "razao_social", "nome_fantasia", "cnpj", "inscricao_estadual", "telefone", "is_active"
    )
    search_fields = ("razao_social", "nome_fantasia", "cnpj", "inscricao_estadual")
    list_filter = ("empresa", "indicador_ie", "uf", "is_active")

# Register your models here.
