from django.contrib import admin

from .models import PromocaoProduto


@admin.register(PromocaoProduto)
class PromocaoProdutoAdmin(admin.ModelAdmin):
    list_display = ("produto", "nome", "preco_promocional", "inicio", "fim", "ativa")
    list_filter = ("ativa", "inicio", "fim")
    search_fields = ("produto__nome", "produto__codigo_barras", "nome")

# Register your models here.
