from django import forms

from apps.core_forms import aplicar_select2
from apps.pdv.models import TerminalPdv
from apps.vendas.models import FormaPagamento

from .models import ConfiguracaoImpressao, TipoDocumentoImpressao


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
            "gaveta_automatica",
            "abrir_gaveta_em_dinheiro",
            "abrir_gaveta_em_movimento_caixa",
            "numero_vias",
            "is_active",
        ]
        widgets = {
            "mensagem_rodape": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        aplicar_select2(self, ["empresa", "filial"])
        self.fields["impressora_padrao"].widget.attrs.update(
            {
                "list": "printer-suggestions",
                "placeholder": "Ex.: Caixa 01, EPSON TM-T20, PDF",
            }
        )

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

    def clean(self):
        cleaned = super().clean()
        usa_gaveta = cleaned.get("gaveta_automatica")
        tipo_documento = cleaned.get("tipo_documento")
        tipos_caixa = {
            TipoDocumentoImpressao.CUPOM_NAO_FISCAL,
            TipoDocumentoImpressao.CUPOM_FISCAL,
            TipoDocumentoImpressao.FECHAMENTO_CAIXA,
        }
        if usa_gaveta and tipo_documento not in tipos_caixa:
            self.add_error("gaveta_automatica", "Gaveta automatica deve ser configurada apenas para documentos de caixa.")
        if not usa_gaveta:
            cleaned["abrir_gaveta_em_dinheiro"] = False
            cleaned["abrir_gaveta_em_movimento_caixa"] = False
        return cleaned


class FormaPagamentoForm(forms.ModelForm):
    TIPOS = [
        ("DINHEIRO", "Dinheiro"),
        ("PIX", "PIX"),
        ("CARTAO", "Cartao / TEF"),
        ("CREDIARIO", "Crediario"),
        ("VALE", "Vale / convenio"),
        ("OUTRO", "Outro"),
    ]
    tipo = forms.ChoiceField(choices=TIPOS)

    class Meta:
        model = FormaPagamento
        fields = ["nome", "tipo", "conta_movimento_padrao", "permite_troco", "exige_autorizacao", "ativo"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        aplicar_select2(self, ["conta_movimento_padrao"])

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("permite_troco") and cleaned.get("tipo") != "DINHEIRO":
            self.add_error("permite_troco", "Troco deve ser habilitado somente para pagamentos em dinheiro.")
        return cleaned


class TerminalPdvForm(forms.ModelForm):
    class Meta:
        model = TerminalPdv
        fields = ["filial", "nome", "descricao", "permite_modo_offline", "ativo"]
        widgets = {
            "descricao": forms.TextInput(attrs={"placeholder": "Ex.: Balcao principal, frente de loja, caixa rapido"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        aplicar_select2(self, ["filial"])
