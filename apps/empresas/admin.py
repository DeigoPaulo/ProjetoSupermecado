from django.contrib import admin

from .models import DocumentoFiscalSincronizado, Empresa, EventoEntradaSincronizacao, EventoSincronizacao, Filial, VendaSincronizada


@admin.register(Empresa)
class EmpresaAdmin(admin.ModelAdmin):
    list_display = ("nome_fantasia", "razao_social", "cnpj", "modo_implantacao", "politica_conflito_sincronizacao", "sincronizacao_automatica", "is_active")
    search_fields = ("nome_fantasia", "razao_social", "cnpj")
    list_filter = ("modo_implantacao", "politica_conflito_sincronizacao", "sincronizacao_automatica", "is_active")


@admin.register(Filial)
class FilialAdmin(admin.ModelAdmin):
    list_display = ("nome", "empresa", "cnpj", "municipio", "uf", "codigo_municipio_ibge", "is_active")
    search_fields = ("nome", "empresa__nome_fantasia", "cnpj", "municipio", "codigo_municipio_ibge")
    list_filter = ("empresa", "uf", "is_active")


@admin.register(EventoSincronizacao)
class EventoSincronizacaoAdmin(admin.ModelAdmin):
    list_display = ("tipo", "empresa", "filial", "status", "tentativas", "criado_em", "processado_em")
    list_filter = ("status", "tipo", "empresa")
    search_fields = ("identificador", "chave_idempotencia", "objeto_tipo", "objeto_id", "ultimo_erro")
    readonly_fields = ("identificador", "chave_idempotencia", "payload", "criado_em", "atualizado_em")


@admin.register(EventoEntradaSincronizacao)
class EventoEntradaSincronizacaoAdmin(admin.ModelAdmin):
    list_display = ("tipo", "empresa", "status", "recebido_em", "processado_em")
    list_filter = ("status", "tipo", "empresa")
    search_fields = ("identificador", "chave_idempotencia", "ultimo_erro")
    readonly_fields = ("identificador", "chave_idempotencia", "payload", "recebido_em", "atualizado_em")


@admin.register(VendaSincronizada)
class VendaSincronizadaAdmin(admin.ModelAdmin):
    list_display = ("venda_externa_id", "empresa", "filial", "total_liquido", "realizada_em", "recebida_em")
    list_filter = ("empresa", "filial")
    search_fields = ("venda_externa_id", "operador", "cliente")
    readonly_fields = ("evento", "itens", "pagamentos", "recebida_em", "atualizada_em")


@admin.register(DocumentoFiscalSincronizado)
class DocumentoFiscalSincronizadoAdmin(admin.ModelAdmin):
    list_display = ("documento_externo_id", "empresa", "filial", "tipo_documento", "status", "valor_total", "emitido_em")
    list_filter = ("empresa", "filial", "tipo_documento", "status")
    search_fields = ("documento_externo_id", "venda_externa_id", "chave_acesso", "protocolo")
    readonly_fields = ("evento", "payload", "recebido_em", "atualizado_em")

# Register your models here.
