from django import forms

from apps.clientes.escopo import empresa_id_do_usuario

from .models import ConfiguracaoFiscal, InutilizacaoNumeracaoFiscal, NaturezaOperacao, SerieFiscal
from .perfis_uf import aplicar_endpoints_nfce_uf, pendencias_endpoints_nfce, perfil_fiscal_uf


class ConfiguracaoFiscalForm(forms.ModelForm):
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.perfil_fiscal = perfil_fiscal_uf(getattr(getattr(self.instance, "filial", None), "uf", ""))
        empresa_id = empresa_id_do_usuario(user) if user else None
        if empresa_id is not None:
            self.fields["filial"].queryset = self.fields["filial"].queryset.filter(empresa_id=empresa_id)
    certificado_arquivo = forms.FileField(
        required=False,
        label="Certificado A1 (.pfx/.p12)",
        help_text="O arquivo será armazenado criptografado e não ficara disponível para download.",
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
            "crt",
            "inscricao_estadual",
            "csc_id",
            "csc_token",
            "url_qrcode_nfce",
            "url_consulta_nfce",
            "certificado_nome",
            "certificado_validade",
            "permite_contingencia_offline",
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
            raise forms.ValidationError("O certificado deve ter no máximo 2 MB.")
        return arquivo

    def clean(self):
        cleaned = super().clean()
        self.perfil_fiscal = aplicar_endpoints_nfce_uf(cleaned) or self.perfil_fiscal
        arquivo = cleaned.get("certificado_arquivo")
        senha = cleaned.get("certificado_senha")
        if arquivo and not senha:
            self.add_error("certificado_senha", "Informe a senha do certificado A1.")
        if senha and not arquivo:
            self.add_error("certificado_arquivo", "Envie o arquivo do certificado para trocar a senha.")
        filial = cleaned.get("filial")
        if filial and self.perfil_fiscal:
            self.instance.ambiente = cleaned.get("ambiente") or self.instance.ambiente
            self.instance.url_qrcode_nfce = cleaned.get("url_qrcode_nfce") or ""
            self.instance.url_consulta_nfce = cleaned.get("url_consulta_nfce") or ""
            for pendencia in pendencias_endpoints_nfce(filial, self.instance):
                campo = "url_qrcode_nfce" if "QR Code" in pendencia else "url_consulta_nfce"
                self.add_error(campo, pendencia)
        return cleaned


class SerieFiscalForm(forms.ModelForm):
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        empresa_id = empresa_id_do_usuario(user) if user else None
        if empresa_id is not None:
            self.fields["filial"].queryset = self.fields["filial"].queryset.filter(empresa_id=empresa_id)
    class Meta:
        model = SerieFiscal
        fields = ["filial", "tipo_documento", "serie", "proximo_numero", "ativo"]


class InutilizacaoNumeracaoFiscalForm(forms.ModelForm):
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        empresa_id = empresa_id_do_usuario(user) if user else None
        if empresa_id is not None:
            self.fields["filial"].queryset = self.fields["filial"].queryset.filter(
                empresa_id=empresa_id,
                is_active=True,
            )
        self.fields["ano"].widget.attrs.update({"min": 2006, "max": 2099})
        self.fields["serie"].widget.attrs.update({"min": 0, "max": 889})
        self.fields["numero_inicial"].widget.attrs.update({"min": 1, "max": 999999999})
        self.fields["numero_final"].widget.attrs.update({"min": 1, "max": 999999999})
        self.fields["justificativa"].widget.attrs.update({"minlength": 15, "maxlength": 255, "rows": 3})

    class Meta:
        model = InutilizacaoNumeracaoFiscal
        fields = [
            "filial",
            "tipo_documento",
            "ano",
            "serie",
            "numero_inicial",
            "numero_final",
            "justificativa",
        ]
        widgets = {
            "justificativa": forms.Textarea,
        }


class NaturezaOperacaoForm(forms.ModelForm):
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        empresa_id = empresa_id_do_usuario(user) if user else None
        if empresa_id is not None:
            self.instance.empresa_id = empresa_id
            self.fields.pop("empresa", None)
        elif self.instance.pk:
            self.fields["empresa"].disabled = True

    class Meta:
        model = NaturezaOperacao
        fields = [
            "empresa", "descricao", "cfop", "tipo_documento", "movimenta_estoque",
            "ipi_incluso_preco", "ipi_compoe_base_icms", "ipi_compoe_base_pis_cofins",
            "ativo",
        ]

    def clean(self):
        cleaned = super().clean()
        if self.user and empresa_id_do_usuario(self.user) == 0:
            self.add_error(None, "Usuario sem empresa ativa nao pode cadastrar natureza de operacao.")
        if not cleaned.get("ipi_incluso_preco") and (
            cleaned.get("ipi_compoe_base_icms") or cleaned.get("ipi_compoe_base_pis_cofins")
        ):
            self.add_error(
                "ipi_incluso_preco",
                "Para definir as bases, confirme primeiro que o IPI tributado está incluído no preço.",
            )
        return cleaned

    def save(self, commit=True):
        natureza = super().save(commit=False)
        empresa_id = empresa_id_do_usuario(self.user) if self.user else None
        if empresa_id is not None:
            natureza.empresa_id = empresa_id
        if commit:
            natureza.save()
            self.save_m2m()
        return natureza
