from datetime import timedelta

from django import forms
from django.utils import timezone

from apps.vendas.models import TipoDocumentoConsumidor

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

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.accounts.permissions import ADMINISTRACAO, has_role
        from apps.empresas.models import Filial

        filiais = Filial.objects.filter(is_active=True)
        if user and not user.is_superuser:
            perfil = getattr(user, "perfil_supermercado", None)
            if not perfil or not perfil.is_active or not perfil.filial_id:
                filiais = filiais.none()
            elif has_role(user, ADMINISTRACAO):
                filiais = filiais.filter(empresa_id=perfil.filial.empresa_id)
            else:
                filiais = filiais.filter(id=perfil.filial_id)
        self.fields["filial"].queryset = filiais


class FinalizarVendaForm(forms.Form):
    caixa = forms.ModelChoiceField(label="Caixa", queryset=Caixa.objects.none())
    cliente = forms.ModelChoiceField(label="Cliente", queryset=None, required=False, empty_label="Cliente avulso")
    documento_consumidor_tipo = forms.ChoiceField(
        label="Documento na nota",
        choices=TipoDocumentoConsumidor.choices,
        required=False,
        initial=TipoDocumentoConsumidor.NAO_IDENTIFICADO,
    )
    documento_consumidor = forms.CharField(
        label="CPF/CNPJ na nota",
        required=False,
        max_length=32,
        widget=forms.TextInput(attrs={"autocomplete": "off", "inputmode": "numeric", "placeholder": "Opcional"}),
    )
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

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.clientes.escopo import clientes_para_usuario
        from apps.clientes.models import Cliente
        from apps.vendas.models import FormaPagamento

        self.fields["caixa"].queryset = Caixa.objects.filter(status="ABERTO")
        if user and not user.is_superuser:
            perfil = getattr(user, "perfil_supermercado", None)
            if perfil and perfil.is_active and perfil.filial_id:
                self.fields["caixa"].queryset = self.fields["caixa"].queryset.filter(
                    filial__empresa_id=perfil.filial.empresa_id,
                    usuario_abertura=user,
                )
            else:
                self.fields["caixa"].queryset = self.fields["caixa"].queryset.none()
        primeiro_caixa = self.fields["caixa"].queryset.first()
        if primeiro_caixa:
            self.fields["caixa"].initial = primeiro_caixa
        self.fields["cliente"].queryset = clientes_para_usuario(user, Cliente.objects.filter(is_active=True))
        self.fields["vencimento_financeiro"].initial = timezone.localdate() + timedelta(days=30)


class PreVendaForm(forms.Form):
    filial = forms.ModelChoiceField(label="Filial", queryset=None)
    cliente = forms.ModelChoiceField(label="Cliente", queryset=None, required=False, empty_label="Cliente avulso")
    desconto = forms.DecimalField(label="Desconto", max_digits=12, decimal_places=2, min_value=0, initial=0)
    validade = forms.DateField(label="Validade", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    observacao = forms.CharField(label="Observacao", required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.clientes.escopo import clientes_para_usuario
        from apps.clientes.models import Cliente
        from apps.empresas.models import Filial

        self.fields["filial"].queryset = Filial.objects.filter(is_active=True)
        if user and not user.is_superuser:
            perfil = getattr(user, "perfil_supermercado", None)
            if perfil and perfil.filial_id:
                self.fields["filial"].queryset = self.fields["filial"].queryset.filter(empresa_id=perfil.filial.empresa_id)
        primeira_filial = self.fields["filial"].queryset.first()
        if primeira_filial:
            self.fields["filial"].initial = primeira_filial
        self.fields["cliente"].queryset = clientes_para_usuario(user, Cliente.objects.filter(is_active=True))
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
