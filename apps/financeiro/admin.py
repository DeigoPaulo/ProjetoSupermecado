from django.contrib import admin

from .models import CategoriaFinanceira, ContaFinanceira


@admin.register(CategoriaFinanceira)
class CategoriaFinanceiraAdmin(admin.ModelAdmin):
    list_display = ("nome", "tipo", "is_active")
    list_filter = ("tipo", "is_active")
    search_fields = ("nome",)


@admin.register(ContaFinanceira)
class ContaFinanceiraAdmin(admin.ModelAdmin):
    list_display = ("descricao", "tipo", "status", "filial", "valor", "vencimento", "data_pagamento")
    list_filter = ("tipo", "status", "filial", "vencimento")
    search_fields = ("descricao", "observacoes")
    readonly_fields = ("criado_em", "atualizado_em")
