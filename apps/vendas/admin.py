from django.contrib import admin

from .models import DevolucaoVenda, FormaPagamento, ItemDevolucaoVenda, ItemPreVenda, ItemVenda, PagamentoVenda, PreVenda, Venda


class ItemVendaInline(admin.TabularInline):
    model = ItemVenda
    extra = 0


class PagamentoVendaInline(admin.TabularInline):
    model = PagamentoVenda
    extra = 0


class ItemPreVendaInline(admin.TabularInline):
    model = ItemPreVenda
    extra = 0


class ItemDevolucaoVendaInline(admin.TabularInline):
    model = ItemDevolucaoVenda
    extra = 0


@admin.register(Venda)
class VendaAdmin(admin.ModelAdmin):
    list_display = ("id", "filial", "caixa", "usuario", "total_liquido", "status", "data")
    list_filter = ("status", "filial", "data")
    inlines = [ItemVendaInline, PagamentoVendaInline]


@admin.register(FormaPagamento)
class FormaPagamentoAdmin(admin.ModelAdmin):
    list_display = ("nome", "tipo", "ativo", "permite_troco", "exige_autorizacao")
    list_filter = ("ativo", "tipo")


@admin.register(PreVenda)
class PreVendaAdmin(admin.ModelAdmin):
    list_display = ("id", "filial", "cliente", "usuario", "total_liquido", "status", "criada_em")
    list_filter = ("status", "filial", "criada_em")
    search_fields = ("id", "cliente__nome")
    inlines = [ItemPreVendaInline]


@admin.register(DevolucaoVenda)
class DevolucaoVendaAdmin(admin.ModelAdmin):
    list_display = ("id", "venda", "usuario", "valor_total", "data")
    list_filter = ("data",)
    search_fields = ("id", "venda__id", "motivo")
    inlines = [ItemDevolucaoVendaInline]

# Register your models here.
