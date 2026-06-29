from django.contrib import admin

from .models import Caixa, Sangria, Suprimento


@admin.register(Caixa)
class CaixaAdmin(admin.ModelAdmin):
    list_display = ("id", "filial", "usuario_abertura", "data_abertura", "status", "valor_inicial", "valor_final")
    list_filter = ("status", "filial")


admin.site.register(Sangria)
admin.site.register(Suprimento)

# Register your models here.
