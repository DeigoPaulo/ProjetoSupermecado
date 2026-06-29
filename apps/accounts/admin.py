from django.contrib import admin

from .models import PerfilUsuario


@admin.register(PerfilUsuario)
class PerfilUsuarioAdmin(admin.ModelAdmin):
    list_display = ("usuario", "tipo", "filial", "is_active")
    list_filter = ("tipo", "filial", "is_active")
    search_fields = ("usuario__username", "usuario__email")

# Register your models here.
