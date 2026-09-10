from django import forms
from django.core.exceptions import ValidationError

from apps.clientes.escopo import empresa_id_do_usuario
from apps.empresas.models import Empresa

from .models import Fornecedor


class FornecedorForm(forms.ModelForm):
    class Meta:
        model = Fornecedor
        fields = [
            "empresa",
            "razao_social",
            "nome_fantasia",
            "cnpj",
            "telefone",
            "email",
            "endereco",
            "indicador_ie",
            "inscricao_estadual",
            "logradouro",
            "numero",
            "complemento",
            "bairro",
            "codigo_municipio_ibge",
            "municipio",
            "uf",
            "cep",
            "condicao_pagamento",
            "prazo_entrega_dias",
            "is_active",
        ]
        labels = {
            "razao_social": "Razão social",
            "cnpj": "CNPJ",
            "endereco": "Endereço",
            "condicao_pagamento": "Condição de pagamento",
            "prazo_entrega_dias": "Prazo de entrega (dias)",
            "is_active": "Ativo",
        }
        widgets = {
            "cnpj": forms.TextInput(attrs={"class": "mask-cpf-cnpj"}),
            "telefone": forms.TextInput(attrs={"class": "mask-phone"}),
            "endereco": forms.Textarea(attrs={"rows": 3}),
            "cep": forms.TextInput(attrs={"class": "mask-cep"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        self.fields["empresa"].queryset = Empresa.objects.filter(is_active=True).order_by("nome_fantasia")
        self.fields["empresa"].required = True
        empresa_id = empresa_id_do_usuario(user) if user else None
        if empresa_id is not None:
            self.fields["empresa"].queryset = self.fields["empresa"].queryset.filter(pk=empresa_id)
            self.fields["empresa"].initial = empresa_id or None
            self.fields["empresa"].widget = forms.HiddenInput()

    def clean_empresa(self):
        empresa = self.cleaned_data.get("empresa")
        if not self.user or self.user.is_superuser:
            return empresa
        empresa_id = empresa_id_do_usuario(self.user)
        if not empresa_id or not empresa or empresa.pk != empresa_id:
            raise ValidationError("Empresa do fornecedor não corresponde ao usuário autenticado.")
        return empresa
