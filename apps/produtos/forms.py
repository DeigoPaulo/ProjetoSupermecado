from django import forms

from .models import Categoria, Marca, Produto


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
            "is_active",
        ]


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
