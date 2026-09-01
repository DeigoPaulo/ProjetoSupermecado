from django.contrib import admin

from .models import (
    CatalogoCEST,
    CatalogoCFOP,
    CatalogoNCM,
    CatalogoBeneficioFiscal,
    ConfiguracaoFiscal,
    DocumentoFiscal,
    ItemCEST,
    ItemCFOP,
    ItemNCM,
    ItemBeneficioFiscal,
    NaturezaOperacao,
    SerieFiscal,
)

class ItemBeneficioFiscalInline(admin.TabularInline):
    model = ItemBeneficioFiscal
    extra = 0
    can_delete = False
    readonly_fields = ["codigo", "csts", "dispositivo_legal", "descricao", "observacao"]


@admin.register(CatalogoBeneficioFiscal)
class CatalogoBeneficioFiscalAdmin(admin.ModelAdmin):
    list_display = ["uf", "versao", "vigencia_inicio", "vigencia_fim", "quantidade_itens", "ativo"]
    list_filter = ["uf", "ativo"]
    search_fields = ["versao", "fonte_nome", "fonte_sha256"]
    readonly_fields = [
        "uf", "versao", "fonte_nome", "fonte_url", "fonte_sha256", "publicado_em",
        "vigencia_inicio", "vigencia_fim", "quantidade_itens", "codigos_duplicados",
        "importado_em", "importado_por",
    ]
    inlines = [ItemBeneficioFiscalInline]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(CatalogoNCM)
class CatalogoNCMAdmin(admin.ModelAdmin):
    list_display = ["versao", "referencia_em", "ato", "quantidade_itens", "ativo"]
    list_filter = ["ativo", "referencia_em"]
    search_fields = ["versao", "ato", "fonte_sha256"]
    readonly_fields = [
        "versao", "referencia_em", "ato", "fonte_nome", "fonte_url",
        "fonte_sha256", "quantidade_itens", "quantidade_linhas_origem",
        "importado_em", "importado_por",
    ]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ItemNCM)
class ItemNCMAdmin(admin.ModelAdmin):
    list_display = ["codigo_formatado", "descricao", "vigencia_inicio", "vigencia_fim", "catalogo"]
    list_filter = ["catalogo"]
    search_fields = ["codigo", "codigo_formatado", "descricao"]
    readonly_fields = ["catalogo", "codigo", "codigo_formatado", "descricao", "vigencia_inicio", "vigencia_fim", "ato_inicio"]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CatalogoCEST)
class CatalogoCESTAdmin(admin.ModelAdmin):
    list_display = ["versao", "referencia_em", "ato", "quantidade_itens", "ativo"]
    list_filter = ["ativo", "referencia_em"]
    search_fields = ["versao", "ato", "fonte_sha256"]
    readonly_fields = [
        "versao", "referencia_em", "ato", "fonte_nome", "fonte_url",
        "fonte_sha256", "quantidade_itens", "quantidade_linhas_origem",
        "quantidade_tabelas_origem", "importado_em", "importado_por",
    ]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ItemCEST)
class ItemCESTAdmin(admin.ModelAdmin):
    list_display = ["codigo_formatado", "segmento_nome", "ncm_sh_original", "descricao", "catalogo"]
    list_filter = ["catalogo", "segmento_codigo"]
    search_fields = ["codigo", "codigo_formatado", "ncm_sh_original", "descricao"]
    readonly_fields = [
        "catalogo", "codigo", "codigo_formatado", "item", "segmento_codigo",
        "segmento_nome", "ncm_sh_original", "ncm_prefixos", "descricao",
    ]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(CatalogoCFOP)
class CatalogoCFOPAdmin(admin.ModelAdmin):
    list_display = ["versao", "referencia_em", "ato", "quantidade_itens", "ativo"]
    list_filter = ["ativo", "referencia_em"]
    search_fields = ["versao", "ato", "fonte_sha256"]
    readonly_fields = [
        "versao", "referencia_em", "ato", "fonte_nome", "fonte_url",
        "fonte_sha256", "quantidade_itens", "quantidade_linhas_origem",
        "quantidade_agrupadores", "importado_em", "importado_por",
    ]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ItemCFOP)
class ItemCFOPAdmin(admin.ModelAdmin):
    list_display = ["codigo_formatado", "titulo", "direcao", "alcance", "catalogo"]
    list_filter = ["catalogo", "direcao", "alcance"]
    search_fields = ["codigo", "codigo_formatado", "titulo", "nota_explicativa"]
    readonly_fields = [
        "catalogo", "codigo", "codigo_formatado", "titulo", "nota_explicativa",
        "direcao", "alcance",
    ]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

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
