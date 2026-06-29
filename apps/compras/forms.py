from django import forms
from django.forms import inlineformset_factory

from .models import EntradaCompra, ItemEntradaCompra


class EntradaCompraForm(forms.ModelForm):
    class Meta:
        model = EntradaCompra
        fields = ["fornecedor", "filial", "numero_documento", "data_emissao", "observacoes"]
        widgets = {
            "data_emissao": forms.DateInput(attrs={"type": "date"}),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }


class ItemEntradaCompraForm(forms.ModelForm):
    class Meta:
        model = ItemEntradaCompra
        fields = ["produto", "quantidade", "custo_unitario", "atualizar_preco_custo"]


ItemEntradaCompraFormSet = inlineformset_factory(
    EntradaCompra,
    ItemEntradaCompra,
    form=ItemEntradaCompraForm,
    extra=3,
    can_delete=True,
)
