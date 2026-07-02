from django.contrib import admin

from .models import Empresa, Filial


@admin.register(Empresa)
class EmpresaAdmin(admin.ModelAdmin):
    list_display = ("nome_fantasia", "razao_social", "cnpj", "is_active")
    search_fields = ("nome_fantasia", "razao_social", "cnpj")
    list_filter = ("is_active",)


@admin.register(Filial)
class FilialAdmin(admin.ModelAdmin):
    list_display = ("nome", "empresa", "cnpj", "municipio", "uf", "codigo_municipio_ibge", "is_active")
    search_fields = ("nome", "empresa__nome_fantasia", "cnpj", "municipio", "codigo_municipio_ibge")
    list_filter = ("empresa", "uf", "is_active")

# Register your models here.
