from django import forms

from .models import ConfiguracaoFiscal, NaturezaOperacao, SerieFiscal


class ConfiguracaoFiscalForm(forms.ModelForm):
    certificado_arquivo = forms.FileField(
        required=False,
        label="Certificado A1 (.pfx/.p12)",
        help_text="O arquivo sera armazenado criptografado e nao ficara disponivel para download.",
    )
    certificado_senha = forms.CharField(
        required=False,
        label="Senha do certificado",
        widget=forms.PasswordInput(render_value=False),
        help_text="Informe a senha apenas quando enviar um novo certificado.",
    )

    class Meta:
        model = ConfiguracaoFiscal
        fields = [
            "filial",
            "ambiente",
            "regime_tributario",
            "inscricao_estadual",
            "csc_id",
            "csc_token",
            "certificado_nome",
            "certificado_validade",
            "certificado_arquivo",
            "certificado_senha",
            "ativo",
        ]
        widgets = {
            "certificado_validade": forms.DateInput(attrs={"type": "date"}),
        }

    def clean_certificado_arquivo(self):
        arquivo = self.cleaned_data.get("certificado_arquivo")
        if not arquivo:
            return arquivo
        nome = arquivo.name.lower()
        if not nome.endswith((".pfx", ".p12")):
            raise forms.ValidationError("Envie um certificado A1 nos formatos .pfx ou .p12.")
        if arquivo.size > 2 * 1024 * 1024:
            raise forms.ValidationError("O certificado deve ter no maximo 2 MB.")
        return arquivo

    def clean(self):
        cleaned = super().clean()
        arquivo = cleaned.get("certificado_arquivo")
        senha = cleaned.get("certificado_senha")
        if arquivo and not senha:
            self.add_error("certificado_senha", "Informe a senha do certificado A1.")
        if senha and not arquivo:
            self.add_error("certificado_arquivo", "Envie o arquivo do certificado para trocar a senha.")
        return cleaned


class SerieFiscalForm(forms.ModelForm):
    class Meta:
        model = SerieFiscal
        fields = ["filial", "tipo_documento", "serie", "proximo_numero", "ativo"]


class NaturezaOperacaoForm(forms.ModelForm):
    class Meta:
        model = NaturezaOperacao
        fields = ["descricao", "cfop", "tipo_documento", "movimenta_estoque", "ativo"]
