from django import forms

from .models import ContratoLicenca, InstalacaoLocal, PlanoComercial


class PlanoComercialForm(forms.ModelForm):
    class Meta:
        model = PlanoComercial
        fields = ["nome", "valor_matriz", "valor_por_filial", "valor_por_terminal", "dias_aviso", "dias_tolerancia", "ativo"]


class ContratoLicencaForm(forms.ModelForm):
    class Meta:
        model = ContratoLicenca
        fields = [
            "empresa", "plano", "dia_vencimento", "valor_mensal", "cobranca_automatica",
            "bloqueio_automatico", "status", "motivo_bloqueio",
        ]

    def clean_dia_vencimento(self):
        dia = self.cleaned_data["dia_vencimento"]
        if not 1 <= dia <= 28:
            raise forms.ValidationError("Escolha um dia entre 1 e 28.")
        return dia


class InstalacaoLocalForm(forms.ModelForm):
    class Meta:
        model = InstalacaoLocal
        fields = ["empresa", "nome", "ativa"]

class EmitirLiberacaoEmergencialForm(forms.Form):
    codigo_desafio = forms.CharField(
        label="Código de desafio do servidor local",
        widget=forms.Textarea(attrs={"rows": 5, "autocomplete": "off"}),
    )
    motivo = forms.CharField(
        label="Motivo da liberação",
        min_length=10,
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    validade_horas = forms.TypedChoiceField(
        label="Validade",
        choices=((24, "24 horas"), (72, "3 dias"), (168, "7 dias")),
        coerce=int,
        initial=24,
    )


class AplicarLiberacaoEmergencialForm(forms.Form):
    codigo_liberacao = forms.CharField(
        label="Código de liberação emitido pela Deigo Tecnologia",
        widget=forms.Textarea(attrs={"rows": 6, "autocomplete": "off"}),
    )