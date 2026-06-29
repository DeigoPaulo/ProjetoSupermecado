from django import forms

from .models import PromocaoProduto


class PromocaoProdutoForm(forms.ModelForm):
    class Meta:
        model = PromocaoProduto
        fields = ["produto", "nome", "preco_promocional", "inicio", "fim", "ativa"]
        widgets = {
            "inicio": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "fim": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }

    def clean(self):
        cleaned = super().clean()
        inicio = cleaned.get("inicio")
        fim = cleaned.get("fim")
        if inicio and fim and fim <= inicio:
            raise forms.ValidationError("A data final deve ser maior que a data inicial.")
        return cleaned
