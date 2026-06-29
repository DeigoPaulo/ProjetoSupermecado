from django.contrib import admin

from .models import ConfiguracaoImpressao


@admin.register(ConfiguracaoImpressao)
class ConfiguracaoImpressaoAdmin(admin.ModelAdmin):
    list_display = ("empresa", "filial", "tipo_documento", "modelo_papel", "impressao_automatica", "is_active")
    list_filter = ("tipo_documento", "modelo_papel", "impressao_automatica", "is_active")

# Register your models here.
