from django.contrib import admin

from .models import FormaPagamento, ItemVenda, PagamentoVenda, Venda


class ItemVendaInline(admin.TabularInline):
    model = ItemVenda
    extra = 0


class PagamentoVendaInline(admin.TabularInline):
    model = PagamentoVenda
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

# Register your models here.
