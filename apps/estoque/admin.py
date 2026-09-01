from django.contrib import admin

from .models import ConferenciaFisicaValidadeLote, ContagemLoteInventarioValidade, EscopoLoteInventarioValidade, Estoque, ExecucaoManutencaoInventarioValidade, FechamentoEstoqueContabil, InventarioEstoque, ItemFechamentoEstoqueContabil, ItemInventarioEstoque, LoteEstoque, MovimentacaoEstoque, MovimentacaoLoteEstoque, OrigemItemInventarioValidade, PerdaEstoque, RetificacaoCapacidadeLoteEstoque


@admin.register(Estoque)
class EstoqueAdmin(admin.ModelAdmin):
    list_display = ("produto", "filial", "quantidade_atual", "quantidade_reservada", "quantidade_disponivel", "atualizado_em")
    search_fields = ("produto__nome", "produto__codigo_barras", "filial__nome")
    list_filter = ("filial",)


@admin.register(MovimentacaoEstoque)
class MovimentacaoEstoqueAdmin(admin.ModelAdmin):
    list_display = ("produto", "filial", "tipo", "quantidade", "usuario", "data")
    search_fields = ("produto__nome", "referencia", "motivo")
    list_filter = ("tipo", "filial", "data")


@admin.register(MovimentacaoLoteEstoque)
class MovimentacaoLoteEstoqueAdmin(admin.ModelAdmin):
    list_display = (
        "movimentacao", "lote_codigo_snapshot", "quantidade",
        "tratamento_status_snapshot", "lote_validade_snapshot", "snapshot_integro",
    )
    list_filter = ("tratamento_status_snapshot", "lote_validade_snapshot")
    search_fields = (
        "lote_codigo_snapshot", "lote__codigo", "movimentacao__referencia", "snapshot_sha256",
    )
    readonly_fields = (
        "movimentacao", "lote", "quantidade", "custo_unitario",
        "lote_codigo_snapshot", "lote_validade_snapshot",
        "tratamento_status_snapshot", "snapshot_sha256",
    )

    @admin.display(boolean=True, description="Snapshot íntegro")
    def snapshot_integro(self, obj):
        return obj.snapshot_integro

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return bool(obj) and super().has_view_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(LoteEstoque)
class LoteEstoqueAdmin(admin.ModelAdmin):
    list_display = ("codigo", "produto", "filial", "quantidade_atual", "quantidade_acrescimos_auditados", "validade", "tratamento_validade_status", "custo_unitario", "criado_em")
    search_fields = ("codigo", "produto__nome", "produto__codigo_barras", "origem_referencia")
    list_filter = ("filial", "validade", "tratamento_validade_status", "criado_em")


@admin.register(ConferenciaFisicaValidadeLote)
class ConferenciaFisicaValidadeLoteAdmin(admin.ModelAdmin):
    list_display = (
        "lote_codigo_snapshot",
        "produto_nome_snapshot",
        "filial_nome_snapshot",
        "quantidade_sistema_snapshot",
        "quantidade_observada",
        "diferenca_snapshot",
        "conferido_por",
        "conferido_em",
    )
    list_filter = ("empresa", "tratamento_status_snapshot", "conferido_em")
    search_fields = (
        "lote_codigo_snapshot",
        "produto_nome_snapshot",
        "produto_codigo_barras_snapshot",
        "conteudo_sha256",
    )
    readonly_fields = (
        "lote",
        "empresa",
        "filial_id_snapshot",
        "filial_nome_snapshot",
        "produto_id_snapshot",
        "produto_nome_snapshot",
        "produto_codigo_barras_snapshot",
        "lote_codigo_snapshot",
        "validade_snapshot",
        "quantidade_sistema_snapshot",
        "quantidade_observada",
        "diferenca_snapshot",
        "custo_unitario_snapshot",
        "tratamento_status_snapshot",
        "observacao",
        "conferido_por",
        "conferido_em",
        "conteudo_sha256",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return bool(obj) and super().has_view_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(OrigemItemInventarioValidade)
class OrigemItemInventarioValidadeAdmin(admin.ModelAdmin):
    list_display = ("item", "conferencia", "lote", "criado_em")
    list_filter = ("criado_em",)
    search_fields = (
        "item__inventario__descricao",
        "item__produto__nome",
        "conferencia__lote_codigo_snapshot",
        "conferencia__conteudo_sha256",
    )
    readonly_fields = ("item", "conferencia", "lote", "criado_em")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return bool(obj) and super().has_view_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(EscopoLoteInventarioValidade)
class EscopoLoteInventarioValidadeAdmin(admin.ModelAdmin):
    list_display = ("item", "lote", "origem", "criado_em")
    list_filter = ("criado_em",)
    search_fields = (
        "item__inventario__descricao",
        "item__produto__nome",
        "lote__codigo",
        "origem__conferencia__conteudo_sha256",
    )
    readonly_fields = ("item", "lote", "origem", "criado_em")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return bool(obj) and super().has_view_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(ContagemLoteInventarioValidade)
class ContagemLoteInventarioValidadeAdmin(admin.ModelAdmin):
    list_display = (
        "escopo", "quantidade_sistema_snapshot", "quantidade_contada",
        "contado_por", "contado_em",
    )
    list_filter = ("contado_em",)
    search_fields = (
        "escopo__item__inventario__descricao",
        "escopo__item__produto__nome",
        "escopo__lote__codigo",
        "conteudo_sha256",
    )
    readonly_fields = (
        "escopo", "quantidade_sistema_snapshot", "quantidade_contada",
        "observacao", "contado_por", "contado_em", "conteudo_sha256",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return bool(obj) and super().has_view_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(RetificacaoCapacidadeLoteEstoque)
class RetificacaoCapacidadeLoteEstoqueAdmin(admin.ModelAdmin):
    list_display = (
        "lote", "inventario", "acrescimo_autorizado", "nova_capacidade",
        "quantidade_contada", "solicitado_por", "autorizado_por", "aplicado_em",
    )
    list_filter = ("aplicado_em",)
    search_fields = (
        "lote__codigo", "lote__produto__nome", "inventario__descricao",
        "justificativa", "conteudo_sha256",
    )
    readonly_fields = (
        "lote", "inventario", "contagem", "quantidade_inicial_snapshot",
        "capacidade_adicional_anterior", "acrescimo_autorizado", "nova_capacidade",
        "quantidade_contada", "justificativa", "solicitado_por",
        "autorizado_por", "aplicado_em", "conteudo_sha256",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return bool(obj) and super().has_view_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return False

class ItemInventarioEstoqueInline(admin.TabularInline):
    model = ItemInventarioEstoque
    extra = 0
    can_delete = False
    readonly_fields = (
        "produto", "quantidade_sistema", "quantidade_contada",
        "diferenca", "observacao",
    )

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ExecucaoManutencaoInventarioValidade)
class ExecucaoManutencaoInventarioValidadeAdmin(admin.ModelAdmin):
    list_display = ("execucao_id", "status", "iniciada_em", "finalizada_em", "expirados_total", "erro_codigo")
    list_filter = ("status", "finalizada_em")
    search_fields = ("execucao_id", "erro_codigo", "conteudo_sha256")
    readonly_fields = (
        "execucao_id", "status", "iniciada_em", "finalizada_em", "expirados_total",
        "erro_codigo", "erro_resumo", "conteudo_sha256",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return bool(obj) and super().has_view_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(InventarioEstoque)
class InventarioEstoqueAdmin(admin.ModelAdmin):
    list_display = (
        "id", "filial", "descricao", "origem", "status", "usuario",
        "criado_em", "expira_em", "aplicado_em", "encerrado_em",
    )
    list_filter = (
        "origem", "status", "filial", "criado_em", "expira_em", "encerrado_em",
    )
    search_fields = (
        "descricao", "motivo_encerramento", "chave_origem", "chave_origem_base",
    )
    readonly_fields = (
        "filial", "usuario", "descricao", "status", "origem",
        "chave_origem", "chave_origem_base", "criado_em", "aplicado_em",
        "expira_em", "encerrado_em", "encerrado_por", "motivo_encerramento",
    )
    inlines = [ItemInventarioEstoqueInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return bool(obj) and super().has_view_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(PerdaEstoque)
class PerdaEstoqueAdmin(admin.ModelAdmin):
    list_display = ("produto", "filial", "lote", "tipo", "quantidade", "valor_custo_estimado", "usuario", "data")
    list_filter = ("tipo", "filial", "data")
    search_fields = ("produto__nome", "produto__codigo_barras", "motivo")
class ItemFechamentoEstoqueContabilInline(admin.TabularInline):
    model = ItemFechamentoEstoqueContabil
    extra = 0
    can_delete = False
    readonly_fields = (
        "produto", "codigo_interno", "codigo_barras", "nome_produto", "ncm", "cest", "unidade",
        "quantidade_fisica", "quantidade_reservada", "quantidade_disponivel", "custo_medio", "valor_custo",
    )

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(FechamentoEstoqueContabil)
class FechamentoEstoqueContabilAdmin(admin.ModelAdmin):
    list_display = (
        "data_referencia", "filial", "total_itens", "valor_total_custo", "criterio_custo", "capturado_por", "capturado_em"
    )
    list_filter = ("data_referencia", "filial")
    search_fields = ("filial__nome", "conteudo_sha256")
    readonly_fields = (
        "filial", "data_referencia", "criterio_custo", "total_itens", "valor_total_custo",
        "conteudo_sha256", "capturado_por", "capturado_em",
    )
    inlines = [ItemFechamentoEstoqueContabilInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return bool(obj) and super().has_view_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return False
