from django import forms
from django.forms import inlineformset_factory

from apps.core_forms import aplicar_select2

from .models import EntradaCompra, ItemEntradaCompra


class EntradaCompraForm(forms.ModelForm):
    class Meta:
        model = EntradaCompra
        fields = ["fornecedor", "filial", "numero_documento", "data_emissao", "vencimento_financeiro", "gerar_conta_financeira", "observacoes"]
        widgets = {
            "data_emissao": forms.DateInput(attrs={"type": "date"}),
            "vencimento_financeiro": forms.DateInput(attrs={"type": "date"}),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        aplicar_select2(
            self,
            ["fornecedor", "filial"],
            ajax_urls={"fornecedor": "/fornecedores/busca.json", "filial": "/empresas/filiais/busca.json"},
        )


class ItemEntradaCompraForm(forms.ModelForm):
    class Meta:
        model = ItemEntradaCompra
        fields = ["produto", "quantidade", "custo_unitario", "atualizar_preco_custo"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        aplicar_select2(self, ["produto"], ajax_urls={"produto": "/estoque/produtos/busca.json"})


ItemEntradaCompraFormSet = inlineformset_factory(
    EntradaCompra,
    ItemEntradaCompra,
    form=ItemEntradaCompraForm,
    extra=3,
    can_delete=True,
)
