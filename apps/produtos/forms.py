from decimal import Decimal

from django import forms
from django.db.models import Q
from django.forms.models import BaseInlineFormSet

from apps.clientes.escopo import empresa_id_do_usuario
from apps.configuracoes.models import ModeloEtiqueta
from apps.core_forms import aplicar_select2
from apps.fornecedores.escopo import fornecedores_para_usuario

from .models import (
    Categoria, CodigoBarrasProduto, ConfiguracaoBalancaProduto, InformacaoNutricional, Marca, Produto,
    ProdutoFornecedor, ProdutoImagem, SetorBalanca,
)


class CategoriaForm(forms.ModelForm):
    class Meta:
        model = Categoria
        fields = ["nome", "nivel", "parent", "descricao", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        superiores = Categoria.objects.all()
        if self.instance.pk:
            superiores = superiores.exclude(pk=self.instance.pk)
        self.fields["parent"].queryset = superiores
        aplicar_select2(self, ["parent"], ajax_urls={"parent": "/produtos/categorias/busca.json"})
        self.fields["nivel"].required = False

    def clean_nivel(self):
        return self.cleaned_data.get("nivel") or "GRUPO"


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
            "tipo_produto",
            "categoria",
            "marca",
            "unidade",
            "unidade_compra",
            "fator_conversao_compra",
            "peso_liquido",
            "peso_bruto",
            "produto_pesavel",
            "preco_custo",
            "margem_desejada_percentual",
            "preco_venda",
            "preco_promocional",
            "estoque_minimo",
            "exige_lote",
            "vendido_no_pdv",
            "vendido_no_marketplace",
            "produtos_similares",
            "imagem",
            "ncm",
            "cest",
            "origem_mercadoria",
            "cst_icms",
            "csosn",
            "aliquota_icms",
            "reducao_base_icms",
            "aliquota_fcp",
            "codigo_beneficio_fiscal",
            "cst_pis",
            "aliquota_pis",
            "cst_cofins",
            "aliquota_cofins",
            "cst_ipi",
            "codigo_enquadramento_ipi",
            "aliquota_ipi",
            "cst_ibs_cbs",
            "classificacao_tributaria_ibs_cbs",
            "is_active",
        ]
        widgets = {
            "imagem": forms.ClearableFileInput(attrs={"accept": ".png,.jpg,.jpeg,image/png,image/jpeg"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        aplicar_select2(
            self,
            ["categoria", "marca", "produtos_similares"],
            ajax_urls={
                "categoria": "/produtos/categorias/busca.json",
                "marca": "/produtos/marcas/busca.json",
                "produtos_similares": "/estoque/produtos/busca.json",
            },
        )
        similares = Produto.objects.all().order_by("nome")
        if self.instance.pk:
            similares = similares.exclude(pk=self.instance.pk)
        self.fields["produtos_similares"].queryset = similares
        # Mantém compatibilidade com importadores e formulários anteriores à unidade de compra.
        self.fields["tipo_produto"].required = False
        self.fields["unidade_compra"].required = False
        self.fields["fator_conversao_compra"].required = False

    def clean_tipo_produto(self):
        return self.cleaned_data.get("tipo_produto") or "MERCADORIA"

    def clean_unidade_compra(self):
        return self.cleaned_data.get("unidade_compra") or self.cleaned_data.get("unidade") or "UN"

    def clean_fator_conversao_compra(self):
        return self.cleaned_data.get("fator_conversao_compra") or Decimal("1.000")

    def clean_codigo_barras(self):
        codigo = (self.cleaned_data.get("codigo_barras") or "").strip()
        adicionais = CodigoBarrasProduto.objects.filter(codigo=codigo)
        if self.instance.pk:
            adicionais = adicionais.exclude(produto=self.instance)
        if codigo and adicionais.exists():
            raise forms.ValidationError("Este código já está cadastrado como EAN adicional de outro produto.")
        return codigo

    def clean_codigo_interno(self):
        codigo = (self.cleaned_data.get("codigo_interno") or "").strip().upper()
        if not codigo:
            return ""
        existentes = Produto.all_objects.filter(codigo_interno=codigo)
        if self.instance.pk:
            existentes = existentes.exclude(pk=self.instance.pk)
        if existentes.exists():
            raise forms.ValidationError("Este código interno já está sendo usado por outro produto.")
        return codigo

    def clean_ncm(self):
        ncm = "".join(filter(str.isdigit, self.cleaned_data.get("ncm", "")))
        if ncm and len(ncm) != 8:
            raise forms.ValidationError("NCM deve possuir 8 dígitos.")
        return ncm

    def clean_cest(self):
        cest = "".join(filter(str.isdigit, self.cleaned_data.get("cest", "")))
        if cest and len(cest) != 7:
            raise forms.ValidationError("CEST deve possuir 7 dígitos.")
        return cest


    def _codigo_numerico(self, campo, tamanho, rotulo):
        valor = "".join(filter(str.isdigit, self.cleaned_data.get(campo, "")))
        if valor and len(valor) != tamanho:
            raise forms.ValidationError(f"{rotulo} deve possuir {tamanho} dígitos.")
        return valor

    def clean_cst_pis(self):
        return self._codigo_numerico("cst_pis", 2, "CST PIS")

    def clean_cst_cofins(self):
        return self._codigo_numerico("cst_cofins", 2, "CST COFINS")

    def clean_cst_ipi(self):
        return self._codigo_numerico("cst_ipi", 2, "CST IPI")

    def clean_codigo_enquadramento_ipi(self):
        return self._codigo_numerico("codigo_enquadramento_ipi", 3, "Código de enquadramento IPI")

    def clean_cst_ibs_cbs(self):
        return self._codigo_numerico("cst_ibs_cbs", 3, "CST IBS/CBS")

    def clean_classificacao_tributaria_ibs_cbs(self):
        return self._codigo_numerico(
            "classificacao_tributaria_ibs_cbs", 6, "Classificação tributária IBS/CBS"
        )

    def clean_codigo_beneficio_fiscal(self):
        return (self.cleaned_data.get("codigo_beneficio_fiscal") or "").strip().upper()


CAMPOS_NUTRICIONAIS_DECIMAIS = [
    "porcao_quantidade",
    "porcoes_por_embalagem",
    "valor_energetico_kcal",
    "carboidratos_g",
    "acucares_totais_g",
    "acucares_adicionados_g",
    "proteinas_g",
    "gorduras_totais_g",
    "gorduras_saturadas_g",
    "gorduras_trans_g",
    "fibra_alimentar_g",
    "sodio_mg",
]


class InformacaoNutricionalForm(forms.ModelForm):
    class Meta:
        model = InformacaoNutricional
        fields = [
            "base_calculo",
            "porcao_quantidade",
            "porcao_unidade",
            "medida_caseira",
            "porcoes_por_embalagem",
            "valor_energetico_kcal",
            "carboidratos_g",
            "acucares_totais_g",
            "acucares_adicionados_g",
            "proteinas_g",
            "gorduras_totais_g",
            "gorduras_saturadas_g",
            "gorduras_trans_g",
            "fibra_alimentar_g",
            "sodio_mg",
            "ingredientes",
            "alergicos",
            "gluten",
            "lactose",
        ]
        widgets = {
            "ingredientes": forms.Textarea(attrs={"rows": 2}),
            "alergicos": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for nome in CAMPOS_NUTRICIONAIS_DECIMAIS:
            self.fields[nome].widget.attrs.update({"min": "0", "step": "0.01", "inputmode": "decimal"})


InformacaoNutricionalFormSet = forms.inlineformset_factory(
    Produto,
    InformacaoNutricional,
    form=InformacaoNutricionalForm,
    extra=1,
    max_num=1,
    validate_max=True,
    can_delete=True,
)


class CodigoBarrasProdutoInlineFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        principal = (self.instance.codigo_barras or "").strip()
        vistos = set()
        for formulario in self.forms:
            if not formulario.cleaned_data or formulario.cleaned_data.get("DELETE"):
                continue
            codigo = (formulario.cleaned_data.get("codigo") or "").strip()
            if not codigo:
                continue
            if codigo == principal:
                raise forms.ValidationError("O EAN adicional deve ser diferente do código principal.")
            if codigo in vistos:
                raise forms.ValidationError("Não repita o mesmo EAN adicional.")
            vistos.add(codigo)
            principais = Produto.all_objects.filter(codigo_barras=codigo)
            if self.instance.pk:
                principais = principais.exclude(pk=self.instance.pk)
            if principais.exists():
                raise forms.ValidationError("Um EAN adicional já é o código principal de outro produto.")


CodigoBarrasProdutoFormSet = forms.inlineformset_factory(
    Produto,
    CodigoBarrasProduto,
    formset=CodigoBarrasProdutoInlineFormSet,
    fields=["codigo", "tipo", "fator_conversao", "permite_venda", "is_active"],
    extra=3,
    can_delete=True,
    widgets={
        "fator_conversao": forms.NumberInput(attrs={"min": "0.001", "step": "0.001"}),
    },
)

class SetorBalancaForm(forms.ModelForm):
    class Meta:
        model = SetorBalanca
        fields = ["empresa", "codigo", "nome", "is_active"]

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.empresas.models import Empresa

        empresa_id = empresa_id_do_usuario(user)
        empresas = Empresa.objects.filter(is_active=True)
        if empresa_id is not None:
            empresas = empresas.filter(pk=empresa_id)
            self.fields["empresa"].initial = empresa_id
        self.fields["empresa"].queryset = empresas
        aplicar_select2(self, ["empresa"])


class ConfiguracaoBalancaProdutoForm(forms.ModelForm):
    class Meta:
        model = ConfiguracaoBalancaProduto
        fields = ["setor", "plu", "tara_kg", "validade_dias", "is_active"]
        widgets = {
            "plu": forms.NumberInput(attrs={"min": 1, "max": 999999, "inputmode": "numeric"}),
            "tara_kg": forms.NumberInput(attrs={"min": 0, "step": "0.001", "inputmode": "decimal"}),
            "validade_dias": forms.NumberInput(attrs={"min": 0, "max": 3650, "inputmode": "numeric"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        empresa_id = empresa_id_do_usuario(user)
        setores = self.fields["setor"].queryset.filter(is_active=True)
        if empresa_id is not None:
            setores = setores.filter(empresa_id=empresa_id)
        self.fields["setor"].queryset = setores.select_related("empresa")
        aplicar_select2(self, ["setor"], ajax_urls={"setor": "/produtos/setores-balanca/busca.json"})

    def clean(self):
        cleaned = super().clean()
        setor = cleaned.get("setor")
        if setor:
            self.instance.empresa = setor.empresa
        return cleaned


class ConfiguracaoBalancaProdutoInlineFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        setores = set()
        empresas = set()
        setor_plu = set()
        for formulario in self.forms:
            if not formulario.cleaned_data or formulario.cleaned_data.get("DELETE"):
                continue
            setor = formulario.cleaned_data.get("setor")
            plu = formulario.cleaned_data.get("plu")
            if not setor or not plu:
                continue
            if setor.empresa_id in empresas:
                raise forms.ValidationError("Cadastre somente um PLU do produto por empresa.")
            empresas.add(setor.empresa_id)
            if setor.pk in setores:
                raise forms.ValidationError("Cadastre somente uma configuração do produto por setor de balança.")
            if (setor.pk, plu) in setor_plu:
                raise forms.ValidationError("Não repita o mesmo PLU no setor de balança.")
            setores.add(setor.pk)
            setor_plu.add((setor.pk, plu))


ConfiguracaoBalancaProdutoFormSet = forms.inlineformset_factory(
    Produto,
    ConfiguracaoBalancaProduto,
    form=ConfiguracaoBalancaProdutoForm,
    formset=ConfiguracaoBalancaProdutoInlineFormSet,
    extra=2,
    can_delete=True,
)

class ProdutoFornecedorForm(forms.ModelForm):
    class Meta:
        model = ProdutoFornecedor
        fields = ["fornecedor", "codigo_no_fornecedor", "ultimo_custo", "principal", "is_active"]

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["fornecedor"].queryset = fornecedores_para_usuario(user, self.fields["fornecedor"].queryset)
        aplicar_select2(self, ["fornecedor"], ajax_urls={"fornecedor": "/fornecedores/busca.json"})


class ProdutoFornecedorInlineFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        principais = 0
        fornecedores = set()
        for formulario in self.forms:
            if not formulario.cleaned_data or formulario.cleaned_data.get("DELETE"):
                continue
            fornecedor = formulario.cleaned_data.get("fornecedor")
            if not fornecedor:
                continue
            if fornecedor.pk in fornecedores:
                raise forms.ValidationError("Não repita o mesmo fornecedor para o produto.")
            fornecedores.add(fornecedor.pk)
            if formulario.cleaned_data.get("principal"):
                principais += 1
        if principais > 1:
            raise forms.ValidationError("Marque somente um fornecedor principal por empresa.")


ProdutoFornecedorFormSet = forms.inlineformset_factory(
    Produto,
    ProdutoFornecedor,
    form=ProdutoFornecedorForm,
    formset=ProdutoFornecedorInlineFormSet,
    extra=2,
    can_delete=True,
)


ProdutoImagemFormSet = forms.inlineformset_factory(
    Produto,
    ProdutoImagem,
    fields=["imagem", "legenda", "ordem"],
    extra=3,
    can_delete=True,
    widgets={
        "imagem": forms.ClearableFileInput(attrs={"accept": ".png,.jpg,.jpeg,image/png,image/jpeg"}),
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
    modelo_salvo = forms.ModelChoiceField(label="Modelo profissional", queryset=Produto.objects.none(), required=False)
    percentual = forms.DecimalField(label="Percentual de reajuste", max_digits=6, decimal_places=2)
    motivo = forms.CharField(label="Motivo", max_length=255)
    aplicar_em_promocional = forms.BooleanField(label="Aplicar tambem no preço promocional", required=False)

    def __init__(self, *args, filial=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["categoria"].queryset = Categoria.objects.all()
        self.fields["marca"].queryset = Marca.objects.all()
        modelos = ModeloEtiqueta.objects.filter(is_active=True, configuracao__is_active=True).select_related("configuracao")
        if filial:
            modelos = modelos.filter(
                Q(configuracao__filial=filial) | Q(configuracao__filial__isnull=True, configuracao__empresa=filial.empresa)
            )
        self.fields["modelo_salvo"].queryset = modelos
        aplicar_select2(
            self,
            ["categoria", "marca", "modelo_salvo"],
            ajax_urls={"categoria": "/produtos/categorias/busca.json", "marca": "/produtos/marcas/busca.json"},
        )

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("categoria") and not cleaned.get("marca"):
            raise forms.ValidationError("Informe ao menos categoria ou marca para limitar o reajuste.")
        if cleaned.get("percentual") == 0:
            raise forms.ValidationError("Percentual não pode ser zero.")
        return cleaned


class EtiquetaProdutoForm(forms.Form):
    MODELO_COMPACTO = "compacto"
    MODELO_COMPLETO = "completo"
    MODELO_A4 = "a4"
    MODELO_CONFIGURADO = "configurado"
    MODELOS = [
        (MODELO_COMPACTO, "Compacto gondola 110 x 30 mm"),
        (MODELO_COMPLETO, "Completo gondola 100 x 50 mm"),
        (MODELO_A4, "A4 multiplas etiquetas"),
        (MODELO_CONFIGURADO, "Modelo profissional configurado"),
    ]

    busca = forms.CharField(label="Busca", max_length=255, required=False)
    modelo = forms.ChoiceField(label="Modelo", choices=MODELOS, initial=MODELO_COMPACTO)
    categoria = forms.ModelChoiceField(label="Categoria", queryset=Categoria.objects.none(), required=False)
    marca = forms.ModelChoiceField(label="Marca", queryset=Marca.objects.none(), required=False)
    modelo_salvo = forms.ModelChoiceField(label="Modelo profissional", queryset=ModeloEtiqueta.objects.none(), required=False)
    quantidade_copias = forms.IntegerField(label="Copias por produto", min_value=1, max_value=20, initial=1)
    incluir_inativos = forms.BooleanField(label="Incluir produtos inativos", required=False)

    def __init__(self, *args, filial=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["busca"].widget.attrs.update(
            {
                "autofocus": "autofocus",
                "autocomplete": "off",
                "placeholder": "Bipe o código de barras, SKU ou digite o nome",
            }
        )
        self.fields["categoria"].queryset = Categoria.objects.all()
        self.fields["marca"].queryset = Marca.objects.all()
        modelos = ModeloEtiqueta.objects.filter(is_active=True, configuracao__is_active=True).select_related("configuracao")
        if filial:
            modelos = modelos.filter(
                Q(configuracao__filial=filial) | Q(configuracao__filial__isnull=True, configuracao__empresa=filial.empresa)
            )
        self.fields["modelo_salvo"].queryset = modelos
        aplicar_select2(
            self,
            ["categoria", "marca", "modelo_salvo"],
            ajax_urls={"categoria": "/produtos/categorias/busca.json", "marca": "/produtos/marcas/busca.json"},
        )
