from django import forms

from .models import Caixa, Sangria, Suprimento


class AdicionarItemForm(forms.Form):
    busca = forms.CharField(label="Produto", max_length=255)
    quantidade = forms.DecimalField(label="Quantidade", max_digits=12, decimal_places=3, min_value=0.001, initial=1)


class AbrirCaixaForm(forms.ModelForm):
    class Meta:
        model = Caixa
        fields = ["filial", "valor_inicial"]


class FinalizarVendaForm(forms.Form):
    caixa = forms.ModelChoiceField(label="Caixa", queryset=Caixa.objects.none())
    cliente = forms.ModelChoiceField(label="Cliente", queryset=None, required=False)
    forma_pagamento = forms.ModelChoiceField(label="Forma de pagamento", queryset=None)
    desconto = forms.DecimalField(label="Desconto", max_digits=12, decimal_places=2, min_value=0, initial=0)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.clientes.models import Cliente
        from apps.vendas.models import FormaPagamento

        self.fields["caixa"].queryset = Caixa.objects.filter(status="ABERTO")
        self.fields["cliente"].queryset = Cliente.objects.filter(is_active=True)
        self.fields["forma_pagamento"].queryset = FormaPagamento.objects.filter(ativo=True)


class SangriaForm(forms.ModelForm):
    class Meta:
        model = Sangria
        fields = ["valor", "motivo"]


class SuprimentoForm(forms.ModelForm):
    class Meta:
        model = Suprimento
        fields = ["valor", "motivo"]


class FecharCaixaForm(forms.ModelForm):
    class Meta:
        model = Caixa
        fields = ["valor_final"]
