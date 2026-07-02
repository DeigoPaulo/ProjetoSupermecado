from django import forms

from .models import ConfiguracaoImpressao


class ConfiguracaoImpressaoForm(forms.ModelForm):
    class Meta:
        model = ConfiguracaoImpressao
        fields = [
            "empresa",
            "filial",
            "tipo_documento",
            "modelo_papel",
            "exibir_logo",
            "tamanho_fonte",
            "margem_superior_mm",
            "margem_inferior_mm",
            "margem_esquerda_mm",
            "margem_direita_mm",
            "mensagem_rodape",
            "impressora_padrao",
            "impressao_automatica",
            "numero_vias",
            "is_active",
        ]
        widgets = {
            "mensagem_rodape": forms.Textarea(attrs={"rows": 3}),
        }

    def clean_tamanho_fonte(self):
        tamanho = self.cleaned_data["tamanho_fonte"]
        if tamanho < 8 or tamanho > 18:
            raise forms.ValidationError("Use fonte entre 8 e 18.")
        return tamanho

    def clean_numero_vias(self):
        vias = self.cleaned_data["numero_vias"]
        if vias < 1 or vias > 5:
            raise forms.ValidationError("Informe de 1 a 5 vias.")
        return vias
