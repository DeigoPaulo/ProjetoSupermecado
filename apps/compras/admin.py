from django.contrib import admin

from .models import (
    CotacaoCompra,
    EntradaCompra,
    ItemCotacaoCompra,
    ItemEntradaCompra,
    ItemPedidoCompra,
    PedidoCompra,
    PrecoRespostaCotacao,
    RespostaCotacaoFornecedor,
)


class ItemCotacaoCompraInline(admin.TabularInline):
    model = ItemCotacaoCompra
    extra = 0


@admin.register(CotacaoCompra)
class CotacaoCompraAdmin(admin.ModelAdmin):
    list_display = ("id", "referencia", "filial", "status", "created_at")
    list_filter = ("status", "filial", "created_at")
    search_fields = ("referencia", "filial__nome")
    inlines = [ItemCotacaoCompraInline]


class PrecoRespostaCotacaoInline(admin.TabularInline):
    model = PrecoRespostaCotacao
    extra = 0


@admin.register(RespostaCotacaoFornecedor)
class RespostaCotacaoFornecedorAdmin(admin.ModelAdmin):
    list_display = ("id", "cotacao", "fornecedor", "prazo_entrega_dias", "selecionada")
    list_filter = ("selecionada", "cotacao__status")
    search_fields = ("fornecedor__razao_social", "cotacao__referencia")
    inlines = [PrecoRespostaCotacaoInline]


class ItemPedidoCompraInline(admin.TabularInline):
    model = ItemPedidoCompra
    extra = 0


@admin.register(PedidoCompra)
class PedidoCompraAdmin(admin.ModelAdmin):
    list_display = ("id", "fornecedor", "filial", "status", "total_previsto", "created_at")
    list_filter = ("status", "filial", "created_at")
    search_fields = ("fornecedor__razao_social", "fornecedor__nome_fantasia", "referencia")
    inlines = [ItemPedidoCompraInline]


class ItemEntradaCompraInline(admin.TabularInline):
    model = ItemEntradaCompra
    extra = 0


@admin.register(EntradaCompra)
class EntradaCompraAdmin(admin.ModelAdmin):
    list_display = ("id", "fornecedor", "filial", "status", "total_produtos", "data_recebimento")
    list_filter = ("status", "filial", "data_recebimento")
    search_fields = ("fornecedor__razao_social", "fornecedor__nome_fantasia", "numero_documento", "chave_acesso_xml")
    inlines = [ItemEntradaCompraInline]

# Register your models here.
