from django import forms
from django.forms import formset_factory, inlineformset_factory

from apps.core_forms import aplicar_select2

from .models import (
    CotacaoCompra,
    EntradaCompra,
    ItemCotacaoCompra,
    ItemEntradaCompra,
    ItemPedidoCompra,
    PedidoCompra,
    RespostaCotacaoFornecedor,
)


class CotacaoCompraForm(forms.ModelForm):
    class Meta:
        model = CotacaoCompra
        fields = ["filial", "referencia", "validade", "observacoes"]
        widgets = {
            "validade": forms.DateInput(attrs={"type": "date"}),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        aplicar_select2(
            self,
            ["filial"],
            ajax_urls={"filial": "/empresas/filiais/busca.json"},
        )


class ItemCotacaoCompraForm(forms.ModelForm):
    class Meta:
        model = ItemCotacaoCompra
        fields = ["produto", "quantidade"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        aplicar_select2(self, ["produto"], ajax_urls={"produto": "/estoque/produtos/busca.json"})


ItemCotacaoCompraFormSet = inlineformset_factory(
    CotacaoCompra,
    ItemCotacaoCompra,
    form=ItemCotacaoCompraForm,
    extra=3,
    can_delete=True,
)


class RespostaCotacaoFornecedorForm(forms.ModelForm):
    class Meta:
        model = RespostaCotacaoFornecedor
        fields = ["fornecedor", "prazo_entrega_dias", "observacoes"]
        widgets = {"observacoes": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        aplicar_select2(
            self,
            ["fornecedor"],
            ajax_urls={"fornecedor": "/fornecedores/busca.json"},
        )


class PrecoRespostaCotacaoForm(forms.Form):
    item = forms.ModelChoiceField(queryset=ItemCotacaoCompra.objects.none(), widget=forms.HiddenInput)
    disponivel = forms.BooleanField(label="Disponivel", required=False, initial=True)
    custo_unitario = forms.DecimalField(
        label="Custo unitario",
        max_digits=10,
        decimal_places=2,
        min_value=0,
        required=False,
    )

    def __init__(self, *args, item_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["item"].queryset = item_queryset or ItemCotacaoCompra.objects.none()

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("disponivel") and cleaned_data.get("custo_unitario") is None:
            self.add_error("custo_unitario", "Informe o custo do item disponivel.")
        return cleaned_data


PrecoRespostaCotacaoFormSet = formset_factory(PrecoRespostaCotacaoForm, extra=0)


class PedidoCompraForm(forms.ModelForm):
    class Meta:
        model = PedidoCompra
        fields = ["fornecedor", "filial", "referencia", "previsao_entrega", "observacoes"]
        widgets = {
            "previsao_entrega": forms.DateInput(attrs={"type": "date"}),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        aplicar_select2(
            self,
            ["fornecedor", "filial"],
            ajax_urls={"fornecedor": "/fornecedores/busca.json", "filial": "/empresas/filiais/busca.json"},
        )


class ItemPedidoCompraForm(forms.ModelForm):
    class Meta:
        model = ItemPedidoCompra
        fields = ["produto", "quantidade", "custo_unitario_previsto"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        aplicar_select2(self, ["produto"], ajax_urls={"produto": "/estoque/produtos/busca.json"})


ItemPedidoCompraFormSet = inlineformset_factory(
    PedidoCompra,
    ItemPedidoCompra,
    form=ItemPedidoCompraForm,
    extra=3,
    can_delete=True,
)


class EntradaCompraForm(forms.ModelForm):
    class Meta:
        model = EntradaCompra
        fields = ["fornecedor", "filial", "numero_documento", "data_emissao", "vencimento_financeiro", "total_documento", "gerar_conta_financeira", "observacoes"]
        widgets = {
            "data_emissao": forms.DateInput(attrs={"type": "date"}),
            "vencimento_financeiro": forms.DateInput(attrs={"type": "date"}),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not (self.instance and self.instance.chave_acesso_xml):
            self.fields.pop("total_documento", None)
        elif "total_documento" in self.fields:
            for nome_campo in ("numero_documento", "data_emissao", "total_documento"):
                self.fields[nome_campo].disabled = True
        aplicar_select2(
            self,
            ["fornecedor", "filial"],
            ajax_urls={"fornecedor": "/fornecedores/busca.json", "filial": "/empresas/filiais/busca.json"},
        )

    def clean(self):
        cleaned_data = super().clean()
        if self.instance and self.instance.pedido_origem_id:
            if cleaned_data.get("fornecedor") != self.instance.pedido_origem.fornecedor:
                self.add_error("fornecedor", "O fornecedor deve permanecer igual ao pedido de origem.")
            if cleaned_data.get("filial") != self.instance.pedido_origem.filial:
                self.add_error("filial", "A filial deve permanecer igual ao pedido de origem.")
        if self.instance and self.instance.pk and self.instance.chave_acesso_xml:
            original = EntradaCompra.objects.only("fornecedor_id", "filial_id").get(pk=self.instance.pk)
            if cleaned_data.get("fornecedor") and cleaned_data["fornecedor"].pk != original.fornecedor_id:
                self.add_error("fornecedor", "O fornecedor identificado pelo XML nao pode ser alterado.")
            if cleaned_data.get("filial") and cleaned_data["filial"].pk != original.filial_id:
                self.add_error("filial", "A filial destinataria identificada pelo XML nao pode ser alterada.")
        return cleaned_data


class ImportarXMLEntradaForm(forms.Form):
    arquivo_xml = forms.FileField(
        label="Arquivo XML da NF-e",
        help_text="Envie uma NF-e autorizada de ate 5 MB.",
    )
    gerar_conta_financeira = forms.BooleanField(
        label="Gerar conta financeira ao finalizar",
        required=False,
        initial=True,
    )

    def clean_arquivo_xml(self):
        arquivo = self.cleaned_data["arquivo_xml"]
        if arquivo.size > 5 * 1024 * 1024:
            raise forms.ValidationError("O arquivo XML deve ter no maximo 5 MB.")
        if not arquivo.name.lower().endswith(".xml"):
            raise forms.ValidationError("Envie um arquivo com extensao .xml.")
        return arquivo


class ItemEntradaCompraForm(forms.ModelForm):
    class Meta:
        model = ItemEntradaCompra
        fields = [
            "produto",
            "quantidade",
            "custo_unitario",
            "codigo_lote",
            "fabricacao",
            "validade",
            "atualizar_preco_custo",
        ]
        widgets = {
            "fabricacao": forms.DateInput(attrs={"type": "date"}),
            "validade": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        aplicar_select2(self, ["produto"], ajax_urls={"produto": "/estoque/produtos/busca.json"})

    def clean(self):
        cleaned_data = super().clean()
        fabricacao = cleaned_data.get("fabricacao")
        validade = cleaned_data.get("validade")
        codigo_lote = (cleaned_data.get("codigo_lote") or "").strip()
        produto = cleaned_data.get("produto")
        if produto and produto.exige_lote and not codigo_lote:
            self.add_error("codigo_lote", "Este produto exige lote nas novas entradas.")
        if (fabricacao or validade) and not codigo_lote:
            self.add_error("codigo_lote", "Informe o lote ao preencher fabricacao ou validade.")
        if fabricacao and validade and fabricacao > validade:
            self.add_error("validade", "A validade nao pode ser anterior a fabricacao.")
        return cleaned_data


ItemEntradaCompraFormSet = inlineformset_factory(
    EntradaCompra,
    ItemEntradaCompra,
    form=ItemEntradaCompraForm,
    extra=3,
    can_delete=True,
)
