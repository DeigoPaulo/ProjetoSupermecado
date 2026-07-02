from django import forms

from .models import CategoriaFinanceira, ContaFinanceira


class CategoriaFinanceiraForm(forms.ModelForm):
    class Meta:
        model = CategoriaFinanceira
        fields = ["nome", "tipo", "is_active"]


class ContaFinanceiraForm(forms.ModelForm):
    class Meta:
        model = ContaFinanceira
        fields = [
            "tipo",
            "descricao",
            "categoria",
            "filial",
            "fornecedor",
            "cliente",
            "valor",
            "vencimento",
            "observacoes",
        ]
        widgets = {
            "vencimento": forms.DateInput(attrs={"type": "date"}),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }


class BaixaContaForm(forms.Form):
    data_pagamento = forms.DateField(label="Data do pagamento", widget=forms.DateInput(attrs={"type": "date"}))
    valor_pago = forms.DecimalField(label="Valor pago/recebido", max_digits=12, decimal_places=2)
    forma_pagamento = forms.CharField(label="Forma", max_length=80, required=False)
