from django import forms

from apps.core_forms import aplicar_select2

from .models import Empresa, Filial, ModoImplantacao


class EmpresaForm(forms.ModelForm):
    class Meta:
        model = Empresa
        fields = [
            "razao_social",
            "nome_fantasia",
            "cnpj",
            "telefone",
            "email",
            "endereco",
            "regime_tributario",
            "logo",
            "modo_implantacao",
            "sincronizacao_automatica",
            "url_sincronizacao",
            "is_active",
        ]
        widgets = {
            "cnpj": forms.TextInput(attrs={"class": "mask-cpf-cnpj", "data-lookup-target": "cnpj"}),
            "telefone": forms.TextInput(attrs={"class": "mask-phone"}),
            "endereco": forms.Textarea(attrs={"rows": 3, "data-lookup-target": "endereco"}),
            "logo": forms.ClearableFileInput(attrs={"accept": ".png,.jpg,.jpeg,image/png,image/jpeg"}),
        }

    def clean(self):
        cleaned = super().clean()
        modo = cleaned.get("modo_implantacao")
        url = (cleaned.get("url_sincronizacao") or "").strip()
        sincroniza = cleaned.get("sincronizacao_automatica")
        if modo == ModoImplantacao.LOCAL:
            cleaned["sincronizacao_automatica"] = False
            cleaned["url_sincronizacao"] = ""
        elif sincroniza and not url:
            self.add_error("url_sincronizacao", "Informe a URL HTTPS do servidor de sincronizacao.")
        elif url and not url.lower().startswith("https://"):
            self.add_error("url_sincronizacao", "A sincronizacao deve usar uma URL HTTPS.")
        return cleaned


class FilialForm(forms.ModelForm):
    class Meta:
        model = Filial
        fields = [
            "empresa",
            "nome",
            "cnpj",
            "telefone",
            "endereco",
            "municipio",
            "uf",
            "codigo_municipio_ibge",
            "is_active",
        ]
        widgets = {
            "cnpj": forms.TextInput(attrs={"class": "mask-cpf-cnpj", "data-lookup-target": "cnpj"}),
            "telefone": forms.TextInput(attrs={"class": "mask-phone"}),
            "endereco": forms.Textarea(attrs={"rows": 3, "data-lookup-target": "endereco"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        aplicar_select2(self, ["empresa"])

    def clean_codigo_municipio_ibge(self):
        codigo = self.cleaned_data.get("codigo_municipio_ibge", "").strip()
        if codigo and (not codigo.isdigit() or len(codigo) != 7):
            raise forms.ValidationError("Informe o codigo IBGE com 7 digitos.")
        return codigo
