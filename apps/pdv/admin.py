from django.contrib import admin

from .models import Caixa, Sangria, Suprimento, TerminalPdv


@admin.register(TerminalPdv)
class TerminalPdvAdmin(admin.ModelAdmin):
    list_display = ("nome", "filial", "identificador", "chave_api_prefixo", "status_licenca", "provedor_tef", "modo_integracao_tef", "permite_modo_offline", "emite_documento_fiscal", "ativo", "ultima_conexao")
    list_filter = ("ativo", "status_licenca", "provedor_tef", "modo_integracao_tef", "permite_modo_offline", "emite_documento_fiscal", "filial")
    search_fields = ("nome", "identificador", "filial__nome")


@admin.register(Caixa)
class CaixaAdmin(admin.ModelAdmin):
    list_display = ("id", "filial", "usuario_abertura", "data_abertura", "status", "valor_inicial", "valor_final")
    list_filter = ("status", "filial")


admin.site.register(Sangria)
admin.site.register(Suprimento)

# Register your models here.
