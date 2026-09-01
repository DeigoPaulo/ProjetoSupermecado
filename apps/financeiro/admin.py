from django.contrib import admin

from .models import AceiteAmostraContabil, CategoriaFinanceira, CentroCusto, ContratoIntegracaoContabil, ContaContabil, ContaFinanceira, ContaMovimentoFinanceiro, LancamentoFinanceiro, TransferenciaFinanceira


@admin.register(ContaContabil)
class ContaContabilAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nome", "natureza", "tipo", "empresa", "conta_pai", "ativa")
    list_filter = ("natureza", "tipo", "ativa", "empresa")
    search_fields = ("codigo", "nome")


@admin.register(CentroCusto)
class CentroCustoAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nome", "empresa", "ativo")
    list_filter = ("ativo", "empresa")
    search_fields = ("codigo", "nome")


@admin.register(CategoriaFinanceira)
class CategoriaFinanceiraAdmin(admin.ModelAdmin):
    list_display = ("nome", "tipo", "is_active")
    list_filter = ("tipo", "is_active")
    search_fields = ("nome",)


@admin.register(ContaFinanceira)
class ContaFinanceiraAdmin(admin.ModelAdmin):
    list_display = ("descricao", "tipo", "status", "filial", "centro_custo", "valor", "vencimento", "data_pagamento")
    list_filter = ("tipo", "status", "filial", "vencimento")
    search_fields = ("descricao", "observacoes")
    readonly_fields = ("criado_em", "atualizado_em")


@admin.register(ContaMovimentoFinanceiro)
class ContaMovimentoFinanceiroAdmin(admin.ModelAdmin):
    list_display = ("nome", "filial", "tipo", "saldo_inicial", "ativa")
    list_filter = ("tipo", "ativa", "filial")
    search_fields = ("nome",)


@admin.register(LancamentoFinanceiro)
class LancamentoFinanceiroAdmin(admin.ModelAdmin):
    list_display = ("data", "conta", "tipo", "descricao", "valor", "origem", "usuario")
    list_filter = ("tipo", "origem", "data", "conta")
    search_fields = ("descricao",)
    readonly_fields = ("conta", "tipo", "origem", "descricao", "valor", "data", "conta_financeira", "centro_custo", "conta_contabil", "transferencia", "usuario", "criado_em")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(TransferenciaFinanceira)
class TransferenciaFinanceiraAdmin(admin.ModelAdmin):
    list_display = ("data", "conta_origem", "conta_destino", "valor", "usuario")
    list_filter = ("data", "conta_origem__filial")
    search_fields = ("descricao", "conta_origem__nome", "conta_destino__nome")
    readonly_fields = ("conta_origem", "conta_destino", "valor", "data", "descricao", "usuario", "criado_em")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(ContratoIntegracaoContabil)
class ContratoIntegracaoContabilAdmin(admin.ModelAdmin):
    list_display = (
        "empresa", "versao", "status", "software_contabil", "formato_entrega",
        "responsavel_efd_icms_ipi", "criado_por", "criado_em",
    )
    list_filter = ("status", "formato_entrega", "responsavel_efd_icms_ipi", "empresa")
    search_fields = ("empresa__nome_fantasia", "software_contabil", "responsavel_efd_nome")
    readonly_fields = (
        "empresa", "versao", "software_contabil", "formato_entrega", "contrato_tecnico",
        "responsavel_efd_icms_ipi", "responsavel_efd_nome", "aceite_referencia",
        "observacoes", "status", "criado_por", "criado_em",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return bool(request.user.is_superuser)

    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(AceiteAmostraContabil)
class AceiteAmostraContabilAdmin(admin.ModelAdmin):
    list_display = (
        "competencia", "empresa", "contrato_integracao", "referencia_aceite",
        "registrado_por", "registrado_em",
    )
    list_filter = ("competencia", "empresa")
    search_fields = ("empresa__nome_fantasia", "referencia_aceite", "pacote_sha256")
    readonly_fields = (
        "empresa", "competencia", "contrato_integracao", "pacote_sha256",
        "relatorio_validacao", "referencia_aceite", "registrado_por", "registrado_em",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return bool(request.user.is_superuser)

    def has_delete_permission(self, request, obj=None):
        return False
