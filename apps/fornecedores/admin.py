from django.contrib import admin

from .models import Fornecedor


@admin.register(Fornecedor)
class FornecedorAdmin(admin.ModelAdmin):
    list_display = ("razao_social", "nome_fantasia", "cnpj", "telefone", "is_active")
    search_fields = ("razao_social", "nome_fantasia", "cnpj")
    list_filter = ("is_active",)

# Register your models here.
