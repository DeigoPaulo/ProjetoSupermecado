from django.contrib import admin

from .models import ConfiguracaoFiscal, DocumentoFiscal, NaturezaOperacao, SerieFiscal


@admin.register(ConfiguracaoFiscal)
class ConfiguracaoFiscalAdmin(admin.ModelAdmin):
    list_display = ["filial", "ambiente", "inscricao_estadual", "certificado_validade", "ativo"]
    list_filter = ["ambiente", "ativo"]
    search_fields = ["filial__nome", "inscricao_estadual"]


@admin.register(SerieFiscal)
class SerieFiscalAdmin(admin.ModelAdmin):
    list_display = ["filial", "tipo_documento", "serie", "proximo_numero", "ativo"]
    list_filter = ["tipo_documento", "ativo"]


@admin.register(NaturezaOperacao)
class NaturezaOperacaoAdmin(admin.ModelAdmin):
    list_display = ["empresa", "descricao", "cfop", "tipo_documento", "padrao", "movimenta_estoque", "ativo"]
    list_filter = ["empresa", "tipo_documento", "padrao", "ativo"]
    search_fields = ["empresa__nome_fantasia", "empresa__razao_social", "descricao", "cfop"]


@admin.register(DocumentoFiscal)
class DocumentoFiscalAdmin(admin.ModelAdmin):
    list_display = ["id", "filial", "tipo_documento", "serie", "numero", "status", "valor_total", "criado_em"]
    list_filter = ["tipo_documento", "ambiente", "status"]
    search_fields = ["numero", "chave_acesso", "protocolo", "venda__id"]
    readonly_fields = ["criado_em", "atualizado_em"]
