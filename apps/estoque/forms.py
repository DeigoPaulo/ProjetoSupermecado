from django import forms
from django.forms import formset_factory, inlineformset_factory

from apps.clientes.escopo import empresa_id_do_usuario
from apps.core_forms import aplicar_select2

from .escopo import usuarios_para_usuario
from .models import (
    ComposicaoProduto,
    ConfiguracaoSLASetorProducao,
    InventarioEstoque,
    ItemComposicaoProduto,
    ItemInventarioEstoque,
    OrdemProducaoComposicao,
    PerdaEstoque,
    ReceitaDesmembramento,
    TipoDesmembramentoProduto,
    TipoMovimentacaoEstoque,
    TipoSaidaDesmembramento,
)


class MovimentacaoEstoqueForm(forms.Form):
    produto = forms.ModelChoiceField(queryset=None)
    filial = forms.ModelChoiceField(queryset=None)
    tipo = forms.ChoiceField(choices=TipoMovimentacaoEstoque.choices)
    quantidade = forms.DecimalField(max_digits=12, decimal_places=3, min_value=0.001)
    motivo = forms.CharField(max_length=255, required=False)
    referencia = forms.CharField(max_length=120, required=False)
    custo_unitario = forms.DecimalField(max_digits=10, decimal_places=2, required=False, min_value=0)
    codigo_lote = forms.CharField(max_length=60, required=False, label="Lote")
    fabricacao = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    validade = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.empresas.models import Filial
        from apps.produtos.models import Produto

        empresa_id = empresa_id_do_usuario(user) if user else None
        self.fields["produto"].queryset = Produto.objects.all()
        self.fields["filial"].queryset = Filial.objects.filter(is_active=True)
        if empresa_id is not None:
            self.fields["filial"].queryset = self.fields["filial"].queryset.filter(empresa_id=empresa_id)
        aplicar_select2(self, ["produto", "filial"])

    def clean(self):
        cleaned_data = super().clean()
        codigo_lote = (cleaned_data.get("codigo_lote") or "").strip()
        fabricacao = cleaned_data.get("fabricacao")
        validade = cleaned_data.get("validade")
        produto = cleaned_data.get("produto")
        tipo = cleaned_data.get("tipo")
        if produto and produto.exige_lote and tipo == TipoMovimentacaoEstoque.ENTRADA and not codigo_lote:
            self.add_error("codigo_lote", "Este produto exige lote nas novas entradas.")
        if (fabricacao or validade) and not codigo_lote:
            self.add_error("codigo_lote", "Informe o lote ao preencher fabricacao ou validade.")
        if fabricacao and validade and fabricacao > validade:
            self.add_error("validade", "A validade nao pode ser anterior a fabricacao.")
        if codigo_lote and tipo not in {
            TipoMovimentacaoEstoque.ENTRADA,
            TipoMovimentacaoEstoque.DEVOLUCAO,
            TipoMovimentacaoEstoque.AJUSTE,
            TipoMovimentacaoEstoque.SAIDA,
            TipoMovimentacaoEstoque.VENDA,
            TipoMovimentacaoEstoque.PERDA,
        }:
            self.add_error("codigo_lote", "Este tipo de movimento nao aceita lote.")
        return cleaned_data

class AtribuirSaldoLoteForm(forms.Form):
    codigo = forms.CharField(max_length=60, label="Codigo do lote")
    quantidade = forms.DecimalField(max_digits=12, decimal_places=3, min_value=0.001)
    custo_unitario = forms.DecimalField(max_digits=10, decimal_places=2, min_value=0)
    fabricacao = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    validade = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    motivo = forms.CharField(max_length=255)

    def clean(self):
        cleaned_data = super().clean()
        fabricacao = cleaned_data.get("fabricacao")
        validade = cleaned_data.get("validade")
        if fabricacao and validade and fabricacao > validade:
            self.add_error("validade", "A validade nao pode ser anterior a fabricacao.")
        return cleaned_data


class InventarioEstoqueForm(forms.ModelForm):
    class Meta:
        model = InventarioEstoque
        fields = ["filial", "descricao"]

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        empresa_id = empresa_id_do_usuario(user) if user else None
        if empresa_id is not None:
            self.fields["filial"].queryset = self.fields["filial"].queryset.filter(empresa_id=empresa_id)
        aplicar_select2(self, ["filial"])

class ItemInventarioEstoqueForm(forms.ModelForm):
    class Meta:
        model = ItemInventarioEstoque
        fields = ["produto", "quantidade_contada", "observacao"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.produtos.models import Produto

        self.fields["produto"].queryset = Produto.objects.all()
        aplicar_select2(self, ["produto"])


class PerdaEstoqueForm(forms.ModelForm):
    class Meta:
        model = PerdaEstoque
        fields = ["produto", "filial", "tipo", "quantidade", "motivo"]

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.empresas.models import Filial
        from apps.produtos.models import Produto

        empresa_id = empresa_id_do_usuario(user) if user else None
        self.fields["produto"].queryset = Produto.objects.all()
        self.fields["filial"].queryset = Filial.objects.filter(is_active=True)
        if empresa_id is not None:
            self.fields["filial"].queryset = self.fields["filial"].queryset.filter(empresa_id=empresa_id)
        aplicar_select2(self, ["produto", "filial"])

class DesmembramentoProdutoForm(forms.Form):
    receita = forms.ModelChoiceField(queryset=None, required=False, label="Receita padrao")
    filial = forms.ModelChoiceField(queryset=None)
    produto_origem = forms.ModelChoiceField(queryset=None, label="Produto origem")
    quantidade_origem = forms.DecimalField(max_digits=12, decimal_places=3, min_value=0.001)
    tipo = forms.ChoiceField(choices=TipoDesmembramentoProduto.choices, initial=TipoDesmembramentoProduto.SIMPLES)
    motivo = forms.CharField(max_length=255)
    observacao = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), required=False)

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.empresas.models import Filial
        from apps.produtos.models import Produto

        empresa_id = empresa_id_do_usuario(user) if user else None
        self.fields["receita"].queryset = ReceitaDesmembramento.objects.filter(is_active=True).select_related(
            "produto_origem", "produto_destino"
        )
        self.fields["filial"].queryset = Filial.objects.filter(is_active=True)
        if empresa_id is not None:
            self.fields["receita"].queryset = self.fields["receita"].queryset.filter(empresa_id=empresa_id)
            self.fields["filial"].queryset = self.fields["filial"].queryset.filter(empresa_id=empresa_id)
        self.fields["produto_origem"].queryset = Produto.objects.all()
        self.fields["produto_origem"].widget.attrs["data-ajax-url"] = "/estoque/produtos/busca.json"
        self.fields["receita"].widget.attrs["data-recipe-select"] = "true"
        self.fields["produto_origem"].widget.attrs["data-placeholder"] = "Bipe ou busque origem por EAN, SKU ou nome"
        aplicar_select2(self, ["receita", "filial", "produto_origem"])

        receita = None
        receita_id = self.data.get("receita") if self.is_bound else self.initial.get("receita")
        if receita_id:
            try:
                receita = self.fields["receita"].queryset.get(pk=receita_id)
            except (ReceitaDesmembramento.DoesNotExist, ValueError, TypeError):
                receita = None
        if receita and not self.is_bound:
            self.initial.update(
                {
                    "receita": receita,
                    "filial": receita.filial,
                    "produto_origem": receita.produto_origem,
                    "quantidade_origem": receita.quantidade_origem,
                    "tipo": receita.tipo,
                    "observacao": receita.observacao,
                }
            )

class DesmembramentoDestinoForm(forms.Form):
    produto_destino = forms.ModelChoiceField(queryset=None, label="Produto destino")
    quantidade_destino = forms.DecimalField(max_digits=12, decimal_places=3, min_value=0.001, label="Quantidade")
    percentual_rendimento_esperado = forms.DecimalField(
        max_digits=7,
        decimal_places=2,
        min_value=0,
        max_value=100,
        required=False,
        label="Rendimento esperado %",
    )
    lote = forms.CharField(max_length=60, required=False)
    validade = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    tipo_saida_destino = forms.ChoiceField(
        choices=TipoSaidaDesmembramento.choices,
        initial=TipoSaidaDesmembramento.VENDAVEL,
        label="Classificacao",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.produtos.models import Produto

        self.fields["produto_destino"].queryset = Produto.objects.all()
        self.fields["produto_destino"].widget.attrs["data-ajax-url"] = "/estoque/produtos/busca.json"
        self.fields["produto_destino"].widget.attrs["data-placeholder"] = "Bipe ou busque destino por EAN, SKU ou nome"
        aplicar_select2(self, ["produto_destino"])


DesmembramentoDestinoFormSet = formset_factory(
    DesmembramentoDestinoForm,
    extra=0,
    min_num=1,
    validate_min=True,
    can_delete=True,
)


class ReceitaDesmembramentoForm(forms.ModelForm):
    class Meta:
        model = ReceitaDesmembramento
        fields = [
            "empresa", "filial", "produto_origem", "quantidade_origem", "produto_destino",
            "quantidade_destino", "tipo", "tipo_saida", "observacao", "is_active",
        ]

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.empresas.models import Empresa, Filial
        from apps.produtos.models import Produto

        empresa_id = empresa_id_do_usuario(user) if user else None
        self.fields["empresa"].queryset = Empresa.objects.filter(is_active=True)
        self.fields["filial"].queryset = Filial.objects.filter(is_active=True)
        if empresa_id is not None:
            self.fields["empresa"].queryset = self.fields["empresa"].queryset.filter(pk=empresa_id)
            self.fields["filial"].queryset = self.fields["filial"].queryset.filter(empresa_id=empresa_id)
        self.fields["produto_origem"].queryset = Produto.objects.all()
        self.fields["produto_destino"].queryset = Produto.objects.all()
        self.fields["produto_origem"].widget.attrs["data-ajax-url"] = "/estoque/produtos/busca.json"
        self.fields["produto_destino"].widget.attrs["data-ajax-url"] = "/estoque/produtos/busca.json"
        aplicar_select2(self, ["empresa", "filial", "produto_origem", "produto_destino"])

class ComposicaoProdutoForm(forms.ModelForm):
    class Meta:
        model = ComposicaoProduto
        fields = ["empresa", "filial", "produto_final", "quantidade_final", "tipo", "observacao", "is_active"]

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.empresas.models import Empresa, Filial
        from apps.produtos.models import Produto

        empresa_id = empresa_id_do_usuario(user) if user else None
        self.fields["empresa"].queryset = Empresa.objects.filter(is_active=True)
        self.fields["filial"].queryset = Filial.objects.filter(is_active=True)
        if empresa_id is not None:
            self.fields["empresa"].queryset = self.fields["empresa"].queryset.filter(pk=empresa_id)
            self.fields["filial"].queryset = self.fields["filial"].queryset.filter(empresa_id=empresa_id)
        self.fields["produto_final"].queryset = Produto.objects.all()
        self.fields["produto_final"].widget.attrs["data-ajax-url"] = "/estoque/produtos/busca.json"
        aplicar_select2(self, ["empresa", "filial", "produto_final"])

class ItemComposicaoProdutoForm(forms.ModelForm):
    class Meta:
        model = ItemComposicaoProduto
        fields = ["produto_componente", "quantidade"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.produtos.models import Produto

        self.fields["produto_componente"].queryset = Produto.objects.all()
        self.fields["produto_componente"].widget.attrs["data-ajax-url"] = "/estoque/produtos/busca.json"
        self.fields["produto_componente"].widget.attrs["data-placeholder"] = "Busque componente por EAN, SKU ou nome"
        aplicar_select2(self, ["produto_componente"])


ItemComposicaoProdutoFormSet = inlineformset_factory(
    ComposicaoProduto,
    ItemComposicaoProduto,
    form=ItemComposicaoProdutoForm,
    extra=1,
    min_num=1,
    validate_min=True,
    can_delete=True,
)


class ProducaoComposicaoForm(forms.Form):
    filial = forms.ModelChoiceField(queryset=None)
    quantidade_final = forms.DecimalField(max_digits=12, decimal_places=3, min_value=0.001)
    motivo = forms.CharField(max_length=255)
    observacao = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), required=False)
    codigo_lote = forms.CharField(max_length=60, required=False, label="Lote do produto final")
    fabricacao = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    validade = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))

    def __init__(self, *args, composicao=None, user=None, **kwargs):
        self._composicao = composicao
        super().__init__(*args, **kwargs)
        from apps.empresas.models import Filial

        empresa_id = empresa_id_do_usuario(user) if user else None
        self.fields["filial"].queryset = Filial.objects.filter(is_active=True)
        if empresa_id is not None:
            self.fields["filial"].queryset = self.fields["filial"].queryset.filter(empresa_id=empresa_id)
        if composicao and composicao.filial_id:
            self.fields["filial"].queryset = self.fields["filial"].queryset.filter(pk=composicao.filial_id)
            self.initial.setdefault("filial", composicao.filial)
        self.initial.setdefault("quantidade_final", composicao.quantidade_final if composicao else 1)
        aplicar_select2(self, ["filial"])

    def clean(self):
        cleaned_data = super().clean()
        codigo_lote = (cleaned_data.get("codigo_lote") or "").strip()
        fabricacao = cleaned_data.get("fabricacao")
        validade = cleaned_data.get("validade")
        if self.composicao and self.composicao.produto_final.exige_lote and not codigo_lote:
            self.add_error("codigo_lote", "O produto final exige lote.")
        if (fabricacao or validade) and not codigo_lote:
            self.add_error("codigo_lote", "Informe o lote ao preencher fabricacao ou validade.")
        if fabricacao and validade and fabricacao > validade:
            self.add_error("validade", "A validade nao pode ser anterior a fabricacao.")
        return cleaned_data

    @property
    def composicao(self):
        return getattr(self, "_composicao", None)

class OrdemProducaoComposicaoForm(forms.ModelForm):
    class Meta:
        model = OrdemProducaoComposicao
        fields = [
            "composicao", "filial", "quantidade_planejada", "data_programada", "prioridade",
            "setor_responsavel", "etapa_operacional", "responsavel_operacional", "motivo", "observacao",
        ]
        widgets = {"data_programada": forms.DateInput(attrs={"type": "date"}), "observacao": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        from django.contrib.auth import get_user_model
        from apps.empresas.models import Filial

        empresa_id = empresa_id_do_usuario(user) if user else None
        self.fields["composicao"].queryset = ComposicaoProduto.objects.filter(is_active=True).select_related("produto_final", "filial")
        self.fields["filial"].queryset = Filial.objects.filter(is_active=True)
        if empresa_id is not None:
            self.fields["composicao"].queryset = self.fields["composicao"].queryset.filter(empresa_id=empresa_id)
            self.fields["filial"].queryset = self.fields["filial"].queryset.filter(empresa_id=empresa_id)
        usuarios = get_user_model().objects.filter(is_active=True)
        self.fields["responsavel_operacional"].queryset = (
            usuarios_para_usuario(user, usuarios).order_by("username") if user else usuarios.order_by("username")
        )
        aplicar_select2(self, ["composicao", "filial", "responsavel_operacional"])

    def clean(self):
        cleaned = super().clean()
        composicao = cleaned.get("composicao")
        filial = cleaned.get("filial")
        if composicao and filial and composicao.filial_id and composicao.filial_id != filial.id:
            self.add_error("filial", "A filial deve ser a mesma vinculada à composição.")
        return cleaned

class ConfiguracaoSLASetorProducaoForm(forms.ModelForm):
    class Meta:
        model = ConfiguracaoSLASetorProducao
        fields = ["empresa", "filial", "setor", "meta_minutos", "observacao", "is_active"]

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.empresas.models import Empresa, Filial

        empresa_id = empresa_id_do_usuario(user) if user else None
        self.fields["empresa"].queryset = Empresa.objects.filter(is_active=True)
        self.fields["filial"].queryset = Filial.objects.filter(is_active=True)
        if empresa_id is not None:
            self.fields["empresa"].queryset = self.fields["empresa"].queryset.filter(pk=empresa_id)
            self.fields["filial"].queryset = self.fields["filial"].queryset.filter(empresa_id=empresa_id)
        self.fields["filial"].required = False
        self.fields["setor"].widget.attrs["placeholder"] = "Ex.: Padaria, Acougue, Hortifruti"
        self.fields["meta_minutos"].widget.attrs["min"] = 1
        aplicar_select2(self, ["empresa", "filial"])

    def clean(self):
        cleaned = super().clean()
        empresa = cleaned.get("empresa")
        filial = cleaned.get("filial")
        if empresa and filial and filial.empresa_id != empresa.id:
            self.add_error("filial", "A filial deve pertencer à empresa informada.")
        return cleaned
