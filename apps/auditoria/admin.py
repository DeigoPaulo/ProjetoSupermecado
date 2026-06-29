from django.contrib import admin

from .models import LogAuditoria


@admin.register(LogAuditoria)
class LogAuditoriaAdmin(admin.ModelAdmin):
    list_display = ("modulo", "acao", "usuario", "objeto_tipo", "objeto_id", "criado_em")
    search_fields = ("modulo", "acao", "descricao", "objeto_tipo", "objeto_id")
    list_filter = ("modulo", "acao", "criado_em")
    readonly_fields = ("criado_em",)

# Register your models here.
