from django import forms

from apps.clientes.escopo import clientes_para_usuario, empresa_id_do_usuario
from apps.core_forms import aplicar_select2
from apps.fornecedores.escopo import fornecedores_para_usuario

from .models import CategoriaFinanceira, ContaFinanceira, ContaMovimentoFinanceiro, TransferenciaFinanceira


class CategoriaFinanceiraForm(forms.ModelForm):
    class Meta:
        model = CategoriaFinanceira
        fields = ["nome", "tipo", "is_active"]


class ContaFinanceiraForm(forms.ModelForm):
    class Meta:
        model = ContaFinanceira
        fields = [
            "tipo",
            "descricao",
            "categoria",
            "filial",
            "fornecedor",
            "cliente",
            "valor",
            "vencimento",
            "observacoes",
        ]
        widgets = {
            "vencimento": forms.DateInput(attrs={"type": "date"}),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        empresa_id = empresa_id_do_usuario(user) if user else None
        if empresa_id is not None:
            self.fields["filial"].queryset = self.fields["filial"].queryset.filter(empresa_id=empresa_id)
        self.fields["cliente"].queryset = clientes_para_usuario(user, self.fields["cliente"].queryset)
        self.fields["fornecedor"].queryset = fornecedores_para_usuario(user, self.fields["fornecedor"].queryset)
        aplicar_select2(
            self,
            ["categoria", "filial", "fornecedor", "cliente"],
            ajax_urls={
                "filial": "/empresas/filiais/busca.json",
                "fornecedor": "/fornecedores/busca.json",
                "cliente": "/clientes/busca.json",
            },
        )

    def clean(self):
        cleaned_data = super().clean()
        fornecedor = cleaned_data.get("fornecedor")
        filial = cleaned_data.get("filial")
        if fornecedor and fornecedor.empresa_id and filial and fornecedor.empresa_id != filial.empresa_id:
            self.add_error("fornecedor", "Fornecedor informado pertence a outra empresa.")
        return cleaned_data


class BaixaContaForm(forms.Form):
    data_pagamento = forms.DateField(label="Data do pagamento", widget=forms.DateInput(attrs={"type": "date"}))
    valor_pago = forms.DecimalField(label="Valor pago/recebido", max_digits=12, decimal_places=2)
    forma_pagamento = forms.CharField(label="Forma", max_length=80, required=False)
    conta_movimento = forms.ModelChoiceField(
        label="Conta de movimento",
        queryset=ContaMovimentoFinanceiro.objects.none(),
        required=False,
        help_text="Selecione para registrar a entrada ou saida no livro financeiro.",
    )

    def __init__(self, *args, filial=None, **kwargs):
        super().__init__(*args, **kwargs)
        queryset = ContaMovimentoFinanceiro.objects.filter(ativa=True)
        if filial:
            queryset = queryset.filter(filial=filial)
        self.fields["conta_movimento"].queryset = queryset.select_related("filial")
        self.fields["conta_movimento"].widget.attrs["class"] = "select2-field"


class ContaMovimentoFinanceiroForm(forms.ModelForm):
    class Meta:
        model = ContaMovimentoFinanceiro
        fields = ["filial", "nome", "tipo", "saldo_inicial", "ativa"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        aplicar_select2(self, ["filial"], ajax_urls={"filial": "/empresas/filiais/busca.json"})


class TransferenciaFinanceiraForm(forms.ModelForm):
    class Meta:
        model = TransferenciaFinanceira
        fields = ["conta_origem", "conta_destino", "valor", "data", "descricao"]
        widgets = {
            "data": forms.DateInput(attrs={"type": "date"}),
            "valor": forms.NumberInput(attrs={"step": "0.01", "min": "0.01"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        contas = ContaMovimentoFinanceiro.objects.filter(ativa=True).select_related("filial", "filial__empresa")
        self.fields["conta_origem"].queryset = contas
        self.fields["conta_destino"].queryset = contas
        self.fields["descricao"].required = False
        aplicar_select2(self, ["conta_origem", "conta_destino"])

    def clean(self):
        cleaned = super().clean()
        origem = cleaned.get("conta_origem")
        destino = cleaned.get("conta_destino")
        if origem and destino and origem.pk == destino.pk:
            raise forms.ValidationError("As contas de origem e destino devem ser diferentes.")
        if origem and destino and origem.filial.empresa_id != destino.filial.empresa_id:
            raise forms.ValidationError("Transferencias entre empresas diferentes nao sao permitidas.")
        return cleaned
