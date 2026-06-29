from django.contrib import admin

from .models import Estoque, InventarioEstoque, ItemInventarioEstoque, MovimentacaoEstoque, PerdaEstoque


@admin.register(Estoque)
class EstoqueAdmin(admin.ModelAdmin):
    list_display = ("produto", "filial", "quantidade_atual", "quantidade_reservada", "quantidade_disponivel", "atualizado_em")
    search_fields = ("produto__nome", "produto__codigo_barras", "filial__nome")
    list_filter = ("filial",)


@admin.register(MovimentacaoEstoque)
class MovimentacaoEstoqueAdmin(admin.ModelAdmin):
    list_display = ("produto", "filial", "tipo", "quantidade", "usuario", "data")
    search_fields = ("produto__nome", "referencia", "motivo")
    list_filter = ("tipo", "filial", "data")


class ItemInventarioEstoqueInline(admin.TabularInline):
    model = ItemInventarioEstoque
    extra = 0


@admin.register(InventarioEstoque)
class InventarioEstoqueAdmin(admin.ModelAdmin):
    list_display = ("id", "filial", "descricao", "status", "usuario", "criado_em", "aplicado_em")
    list_filter = ("status", "filial", "criado_em")
    search_fields = ("descricao",)
    inlines = [ItemInventarioEstoqueInline]


@admin.register(PerdaEstoque)
class PerdaEstoqueAdmin(admin.ModelAdmin):
    list_display = ("produto", "filial", "tipo", "quantidade", "valor_custo_estimado", "usuario", "data")
    list_filter = ("tipo", "filial", "data")
    search_fields = ("produto__nome", "produto__codigo_barras", "motivo")

# Register your models here.
