from django import forms

from apps.core_forms import aplicar_select2

from .models import Categoria, Marca, Produto, ProdutoImagem


class CategoriaForm(forms.ModelForm):
    class Meta:
        model = Categoria
        fields = ["nome", "descricao", "is_active"]


class MarcaForm(forms.ModelForm):
    class Meta:
        model = Marca
        fields = ["nome", "is_active"]


class ProdutoForm(forms.ModelForm):
    class Meta:
        model = Produto
        fields = [
            "codigo_barras",
            "codigo_interno",
            "nome",
            "descricao",
            "categoria",
            "marca",
            "unidade",
            "produto_pesavel",
            "preco_custo",
            "preco_venda",
            "preco_promocional",
            "estoque_minimo",
            "vendido_no_pdv",
            "vendido_no_marketplace",
            "imagem",
            "ncm",
            "cest",
            "origem_mercadoria",
            "cst_icms",
            "csosn",
            "aliquota_icms",
            "is_active",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        aplicar_select2(self, ["categoria", "marca"])

    def clean_ncm(self):
        ncm = "".join(filter(str.isdigit, self.cleaned_data.get("ncm", "")))
        if ncm and len(ncm) != 8:
            raise forms.ValidationError("NCM deve possuir 8 digitos.")
        return ncm

    def clean_cest(self):
        cest = "".join(filter(str.isdigit, self.cleaned_data.get("cest", "")))
        if cest and len(cest) != 7:
            raise forms.ValidationError("CEST deve possuir 7 digitos.")
        return cest


ProdutoImagemFormSet = forms.inlineformset_factory(
    Produto,
    ProdutoImagem,
    fields=["imagem", "legenda", "ordem"],
    extra=3,
    can_delete=True,
    widgets={
        "imagem": forms.ClearableFileInput(attrs={"accept": "image/*"}),
        "ordem": forms.NumberInput(attrs={"min": 0}),
    },
)


class ProdutoImportCSVForm(forms.Form):
    arquivo = forms.FileField(label="Arquivo CSV")
    atualizar_existentes = forms.BooleanField(label="Atualizar produtos existentes", required=False, initial=True)

    def clean_arquivo(self):
        arquivo = self.cleaned_data["arquivo"]
        if not arquivo.name.lower().endswith(".csv"):
            raise forms.ValidationError("Envie um arquivo CSV.")
        return arquivo


class ReajustePrecoForm(forms.Form):
    categoria = forms.ModelChoiceField(label="Categoria", queryset=Categoria.objects.none(), required=False)
    marca = forms.ModelChoiceField(label="Marca", queryset=Marca.objects.none(), required=False)
    percentual = forms.DecimalField(label="Percentual de reajuste", max_digits=6, decimal_places=2)
    motivo = forms.CharField(label="Motivo", max_length=255)
    aplicar_em_promocional = forms.BooleanField(label="Aplicar tambem no preco promocional", required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["categoria"].queryset = Categoria.objects.all()
        self.fields["marca"].queryset = Marca.objects.all()
        aplicar_select2(self, ["categoria", "marca"])

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("categoria") and not cleaned.get("marca"):
            raise forms.ValidationError("Informe ao menos categoria ou marca para limitar o reajuste.")
        if cleaned.get("percentual") == 0:
            raise forms.ValidationError("Percentual nao pode ser zero.")
        return cleaned


class EtiquetaProdutoForm(forms.Form):
    busca = forms.CharField(label="Busca", max_length=255, required=False)
    categoria = forms.ModelChoiceField(label="Categoria", queryset=Categoria.objects.none(), required=False)
    marca = forms.ModelChoiceField(label="Marca", queryset=Marca.objects.none(), required=False)
    quantidade_copias = forms.IntegerField(label="Copias por produto", min_value=1, max_value=20, initial=1)
    incluir_inativos = forms.BooleanField(label="Incluir produtos inativos", required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["categoria"].queryset = Categoria.objects.all()
        self.fields["marca"].queryset = Marca.objects.all()
        aplicar_select2(self, ["categoria", "marca"])
