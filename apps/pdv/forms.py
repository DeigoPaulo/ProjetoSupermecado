from datetime import timedelta

from django import forms
from django.utils import timezone

from .models import Caixa, Sangria, Suprimento


class AdicionarItemForm(forms.Form):
    busca = forms.CharField(
        label="Produto",
        max_length=255,
        widget=forms.TextInput(attrs={"autofocus": "autofocus", "autocomplete": "off", "placeholder": "Codigo de barras ou nome"}),
    )
    quantidade = forms.DecimalField(
        label="Quantidade",
        max_digits=12,
        decimal_places=3,
        min_value=0.001,
        initial=1,
        widget=forms.NumberInput(attrs={"step": "0.001", "inputmode": "decimal"}),
    )


class AbrirCaixaForm(forms.ModelForm):
    class Meta:
        model = Caixa
        fields = ["filial", "valor_inicial"]


class FinalizarVendaForm(forms.Form):
    caixa = forms.ModelChoiceField(label="Caixa", queryset=Caixa.objects.none())
    cliente = forms.ModelChoiceField(label="Cliente", queryset=None, required=False, empty_label="Cliente avulso")
    desconto = forms.DecimalField(label="Desconto", max_digits=12, decimal_places=2, min_value=0, initial=0)
    vencimento_financeiro = forms.DateField(
        label="Vencimento crediario",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    valor_recebido = forms.DecimalField(
        label="Pago pelo cliente",
        max_digits=12,
        decimal_places=2,
        min_value=0,
        required=False,
        widget=forms.NumberInput(attrs={"step": "0.01", "inputmode": "decimal"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.clientes.models import Cliente
        from apps.vendas.models import FormaPagamento

        self.fields["caixa"].queryset = Caixa.objects.filter(status="ABERTO")
        primeiro_caixa = self.fields["caixa"].queryset.first()
        if primeiro_caixa:
            self.fields["caixa"].initial = primeiro_caixa
        self.fields["cliente"].queryset = Cliente.objects.filter(is_active=True)
        self.fields["vencimento_financeiro"].initial = timezone.localdate() + timedelta(days=30)


class PreVendaForm(forms.Form):
    filial = forms.ModelChoiceField(label="Filial", queryset=None)
    cliente = forms.ModelChoiceField(label="Cliente", queryset=None, required=False, empty_label="Cliente avulso")
    desconto = forms.DecimalField(label="Desconto", max_digits=12, decimal_places=2, min_value=0, initial=0)
    validade = forms.DateField(label="Validade", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    observacao = forms.CharField(label="Observacao", required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.clientes.models import Cliente
        from apps.empresas.models import Filial

        self.fields["filial"].queryset = Filial.objects.filter(is_active=True)
        primeira_filial = self.fields["filial"].queryset.first()
        if primeira_filial:
            self.fields["filial"].initial = primeira_filial
        self.fields["cliente"].queryset = Cliente.objects.filter(is_active=True)
        self.fields["validade"].initial = timezone.localdate() + timedelta(days=7)


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


class ConferirCaixaForm(forms.ModelForm):
    class Meta:
        model = Caixa
        fields = ["valor_conferido", "observacao_conferencia"]
