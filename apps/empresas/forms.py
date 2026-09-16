from django import forms

from apps.core_forms import aplicar_select2
from apps.fiscal.estrategia_normalizacao_cnpj import canonicalizar_cnpj, validar_dv_cnpj
from apps.fiscal.portao_escrita_canonica_cnpj import preparar_escrita_canonica_cnpj

from .models import Empresa, Filial, ModoImplantacao, PoliticaConflitoSincronizacao


def _cnpj_canonico_valido(valor):
    try:
        canonico = canonicalizar_cnpj(valor)
    except ValueError:
        return ""
    return canonico if canonico and validar_dv_cnpj(canonico) else ""


def _existe_colisao_cnpj(queryset, canonico, *, excluir_pk=None):
    if excluir_pk is not None:
        queryset = queryset.exclude(pk=excluir_pk)
    return any(
        _cnpj_canonico_valido(valor) == canonico
        for valor in queryset.values_list("cnpj", flat=True).iterator()
    )


def _validar_proposta_cnpj(valor, *, fronteira, instance, empresa_id=None):
    operacao = "ATUALIZACAO" if instance and instance.pk else "CRIACAO"
    resultado = preparar_escrita_canonica_cnpj(
        valor,
        fronteira=fronteira,
        operacao=operacao,
        empresa_id=empresa_id,
        valor_atual=getattr(instance, "cnpj", None),
    )
    status = resultado["status"]
    if status == "PROPOSTA_INVALIDA":
        raise forms.ValidationError(
            "Informe um CNPJ no formato oficial e com dígitos verificadores válidos.",
            code="cnpj_invalido",
        )
    if status == "LEGADO_INVALIDO_REQUER_REVISAO":
        raise forms.ValidationError(
            "O CNPJ atual é legado inválido e exige revisão manual antes da atualização.",
            code="cnpj_legado_invalido",
        )
    if status == "TROCA_IDENTIDADE_REQUER_CONTROLES_EXTERNOS":
        raise forms.ValidationError(
            "A troca do CNPJ exige revisão de identidade e não pode ser feita por este formulário.",
            code="cnpj_troca_identidade",
        )
    if status not in {"CANONICO_PREPARADO", "SEM_ALTERACAO_CANONICA"}:
        raise forms.ValidationError(
            "Não foi possível validar o CNPJ neste cadastro.",
            code="cnpj_nao_validado",
        )
    return resultado["proposta"]["valor_canonico"]


class EmpresaForm(forms.ModelForm):
    class Meta:
        model = Empresa
        fields = [
            "razao_social",
            "nome_fantasia",
            "cnpj",
            "telefone",
            "email",
            "cep",
            "logradouro",
            "numero",
            "complemento",
            "bairro",
            "municipio",
            "uf",
            "endereco",
            "regime_tributario",
            "logo",
            "modo_implantacao",
            "sincronizacao_automatica",
            "url_sincronizacao",
            "politica_conflito_sincronizacao",
            "bloquear_finalizacao_entrada_divergente",
            "is_active",
        ]
        widgets = {
            "cnpj": forms.TextInput(attrs={"class": "mask-cnpj", "data-lookup-target": "cnpj"}),
            "telefone": forms.TextInput(attrs={"class": "mask-phone"}),
            "cep": forms.TextInput(attrs={"class": "mask-cep", "data-lookup-target": "cep", "placeholder": "00000-000"}),
            "endereco": forms.HiddenInput(),
            "logo": forms.ClearableFileInput(attrs={"accept": ".png,.jpg,.jpeg,image/png,image/jpeg"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["politica_conflito_sincronizacao"].required = False

    def clean_cnpj(self):
        canonico = _validar_proposta_cnpj(
            self.cleaned_data.get("cnpj"),
            fronteira="EMPRESA",
            instance=self.instance,
        )
        if _existe_colisao_cnpj(
            Empresa.objects.all(), canonico, excluir_pk=getattr(self.instance, "pk", None)
        ):
            raise forms.ValidationError(
                "Empresa com este CNPJ já existe.",
                code="cnpj_colisao_canonica",
            )
        return canonico

    def clean(self):
        cleaned = super().clean()
        cleaned["politica_conflito_sincronizacao"] = cleaned.get("politica_conflito_sincronizacao") or PoliticaConflitoSincronizacao.MANUAL
        modo = cleaned.get("modo_implantacao")
        url = (cleaned.get("url_sincronizacao") or "").strip()
        sincroniza = cleaned.get("sincronizacao_automatica")
        if modo == ModoImplantacao.LOCAL:
            cleaned["sincronizacao_automatica"] = False
            cleaned["url_sincronizacao"] = ""
        elif sincroniza and not url:
            self.add_error("url_sincronizacao", "Informe a URL HTTPS do servidor de sincronização.")
        elif url and not url.lower().startswith("https://"):
            self.add_error("url_sincronizacao", "A sincronização deve usar uma URL HTTPS.")
        return cleaned


class FilialForm(forms.ModelForm):
    class Meta:
        model = Filial
        fields = [
            "empresa",
            "nome",
            "cnpj",
            "telefone",
            "cep",
            "logradouro",
            "numero",
            "complemento",
            "bairro",
            "endereco",
            "municipio",
            "uf",
            "codigo_municipio_ibge",
            "is_active",
        ]
        widgets = {
            "cnpj": forms.TextInput(attrs={"class": "mask-cnpj", "data-lookup-target": "cnpj"}),
            "telefone": forms.TextInput(attrs={"class": "mask-phone"}),
            "cep": forms.TextInput(attrs={"class": "mask-cep", "data-lookup-target": "cep", "placeholder": "00000-000"}),
            "endereco": forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        aplicar_select2(self, ["empresa"])

    def clean_cnpj(self):
        valor = self.cleaned_data.get("cnpj")
        if not str(valor or "").strip():
            return ""
        empresa = self.cleaned_data.get("empresa")
        if empresa is None:
            return valor
        canonico = _validar_proposta_cnpj(
            valor,
            fronteira="FILIAL",
            instance=self.instance,
            empresa_id=empresa.pk,
        )
        if _existe_colisao_cnpj(
            Filial.objects.filter(empresa=empresa),
            canonico,
            excluir_pk=getattr(self.instance, "pk", None),
        ):
            raise forms.ValidationError(
                "Já existe uma filial desta empresa com este CNPJ.",
                code="cnpj_colisao_canonica",
            )
        return canonico

    def clean_codigo_municipio_ibge(self):
        codigo = self.cleaned_data.get("codigo_municipio_ibge", "").strip()
        if codigo and (not codigo.isdigit() or len(codigo) != 7):
            raise forms.ValidationError("Informe o código IBGE com 7 digitos.")
        return codigo
