from django.contrib import admin

from .models import Cliente


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ("nome", "cpf_cnpj", "telefone", "is_active")
    search_fields = ("nome", "cpf_cnpj", "telefone", "email")
    list_filter = ("is_active",)

# Register your models here.
