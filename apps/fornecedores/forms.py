from django import forms
from django.core.exceptions import ValidationError

from apps.clientes.escopo import empresa_id_do_usuario
from apps.empresas.models import Empresa
from apps.fiscal.validacao_escrita_cnpj import (
    ErroValidacaoEscritaCNPJ,
    existe_colisao_cnpj,
    validar_proposta_cnpj,
)

from .models import Fornecedor


MENSAGENS_CNPJ = {
    "cnpj_invalido": "Informe um CNPJ no formato oficial e com dígitos verificadores válidos.",
    "cnpj_legado_invalido": "O CNPJ atual é legado inválido e exige revisão manual antes da atualização.",
    "cnpj_troca_identidade": "A troca do CNPJ exige revisão de identidade e não pode ser feita por este formulário.",
    "cnpj_nao_validado": "Não foi possível validar o CNPJ neste cadastro.",
}


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
            "cnpj": forms.TextInput(attrs={"class": "mask-cnpj"}),
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

    def clean_cnpj(self):
        valor = str(self.cleaned_data.get("cnpj") or "").strip()
        if not valor:
            return ""
        empresa = self.cleaned_data.get("empresa")
        if empresa is None:
            return valor
        try:
            canonico = validar_proposta_cnpj(
                valor,
                fronteira="FORNECEDOR_PJ",
                instance=self.instance,
                empresa_id=empresa.pk,
            )
        except ErroValidacaoEscritaCNPJ as exc:
            raise ValidationError(MENSAGENS_CNPJ[exc.codigo], code=exc.codigo) from exc
        if existe_colisao_cnpj(
            Fornecedor.objects.filter(empresa=empresa),
            canonico,
            excluir_pk=getattr(self.instance, "pk", None),
        ):
            raise ValidationError(
                "Já existe um fornecedor desta empresa com este CNPJ.",
                code="cnpj_colisao_canonica",
            )
        return canonico
