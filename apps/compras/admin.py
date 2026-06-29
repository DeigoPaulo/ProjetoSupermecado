from django.contrib import admin

from .models import EntradaCompra, ItemEntradaCompra


class ItemEntradaCompraInline(admin.TabularInline):
    model = ItemEntradaCompra
    extra = 0


@admin.register(EntradaCompra)
class EntradaCompraAdmin(admin.ModelAdmin):
    list_display = ("id", "fornecedor", "filial", "status", "total_produtos", "data_recebimento")
    list_filter = ("status", "filial", "data_recebimento")
    search_fields = ("fornecedor__razao_social", "fornecedor__nome_fantasia", "numero_documento")
    inlines = [ItemEntradaCompraInline]

# Register your models here.
