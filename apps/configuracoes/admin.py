from django.contrib import admin

from .models import ConfiguracaoImpressao, ModeloEtiqueta


@admin.register(ConfiguracaoImpressao)
class ConfiguracaoImpressaoAdmin(admin.ModelAdmin):
    list_display = (
        "empresa",
        "filial",
        "tipo_documento",
        "modelo_papel",
        "impressao_automatica",
        "gaveta_automatica",
        "is_active",
    )
    list_filter = ("tipo_documento", "modelo_papel", "impressao_automatica", "gaveta_automatica", "is_active")


@admin.register(ModeloEtiqueta)
class ModeloEtiquetaAdmin(admin.ModelAdmin):
    list_display = ("nome", "configuracao", "terminal", "largura_mm", "altura_mm", "colunas", "padrao", "is_active")
    list_filter = ("orientacao", "padrao", "is_active")

# Register your models here.
