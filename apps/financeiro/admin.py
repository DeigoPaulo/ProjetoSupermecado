from django.contrib import admin

from .models import CategoriaFinanceira, ContaFinanceira, ContaMovimentoFinanceiro, LancamentoFinanceiro, TransferenciaFinanceira


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


@admin.register(ContaMovimentoFinanceiro)
class ContaMovimentoFinanceiroAdmin(admin.ModelAdmin):
    list_display = ("nome", "filial", "tipo", "saldo_inicial", "ativa")
    list_filter = ("tipo", "ativa", "filial")
    search_fields = ("nome",)


@admin.register(LancamentoFinanceiro)
class LancamentoFinanceiroAdmin(admin.ModelAdmin):
    list_display = ("data", "conta", "tipo", "descricao", "valor", "origem", "usuario")
    list_filter = ("tipo", "origem", "data", "conta")
    search_fields = ("descricao",)
    readonly_fields = ("conta", "tipo", "origem", "descricao", "valor", "data", "conta_financeira", "transferencia", "usuario", "criado_em")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(TransferenciaFinanceira)
class TransferenciaFinanceiraAdmin(admin.ModelAdmin):
    list_display = ("data", "conta_origem", "conta_destino", "valor", "usuario")
    list_filter = ("data", "conta_origem__filial")
    search_fields = ("descricao", "conta_origem__nome", "conta_destino__nome")
    readonly_fields = ("conta_origem", "conta_destino", "valor", "data", "descricao", "usuario", "criado_em")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
