from django.contrib import admin

from .models import Categoria, Marca, Produto


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ("nome", "is_active")
    search_fields = ("nome",)
    list_filter = ("is_active",)


@admin.register(Marca)
class MarcaAdmin(admin.ModelAdmin):
    list_display = ("nome", "is_active")
    search_fields = ("nome",)
    list_filter = ("is_active",)


@admin.register(Produto)
class ProdutoAdmin(admin.ModelAdmin):
    list_display = ("nome", "codigo_barras", "categoria", "preco_venda", "produto_pesavel", "exige_lote", "is_active")
    search_fields = ("nome", "codigo_barras", "codigo_interno")
    list_filter = (
        "categoria",
        "marca",
        "produto_pesavel",
        "exige_lote",
        "vendido_no_pdv",
        "vendido_no_marketplace",
        "is_active",
    )

# Register your models here.
