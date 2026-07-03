from django import forms

from apps.core_forms import aplicar_select2

from .models import InventarioEstoque, ItemInventarioEstoque, PerdaEstoque, TipoMovimentacaoEstoque


class MovimentacaoEstoqueForm(forms.Form):
    produto = forms.ModelChoiceField(queryset=None)
    filial = forms.ModelChoiceField(queryset=None)
    tipo = forms.ChoiceField(choices=TipoMovimentacaoEstoque.choices)
    quantidade = forms.DecimalField(max_digits=12, decimal_places=3, min_value=0.001)
    motivo = forms.CharField(max_length=255, required=False)
    referencia = forms.CharField(max_length=120, required=False)
    custo_unitario = forms.DecimalField(max_digits=10, decimal_places=2, required=False, min_value=0)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.empresas.models import Filial
        from apps.produtos.models import Produto

        self.fields["produto"].queryset = Produto.objects.all()
        self.fields["filial"].queryset = Filial.objects.filter(is_active=True)
        aplicar_select2(self, ["produto", "filial"])


class InventarioEstoqueForm(forms.ModelForm):
    class Meta:
        model = InventarioEstoque
        fields = ["filial", "descricao"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        aplicar_select2(self, ["filial"])


class ItemInventarioEstoqueForm(forms.ModelForm):
    class Meta:
        model = ItemInventarioEstoque
        fields = ["produto", "quantidade_contada", "observacao"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.produtos.models import Produto

        self.fields["produto"].queryset = Produto.objects.all()
        aplicar_select2(self, ["produto"])


class PerdaEstoqueForm(forms.ModelForm):
    class Meta:
        model = PerdaEstoque
        fields = ["produto", "filial", "tipo", "quantidade", "motivo"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.empresas.models import Filial
        from apps.produtos.models import Produto

        self.fields["produto"].queryset = Produto.objects.all()
        self.fields["filial"].queryset = Filial.objects.filter(is_active=True)
        aplicar_select2(self, ["produto", "filial"])
