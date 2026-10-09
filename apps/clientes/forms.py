from django import forms
from django.core.exceptions import ValidationError
import re

from apps.empresas.models import Empresa
from apps.fiscal.validacao_escrita_cnpj import (
    ErroValidacaoEscritaCNPJ,
    existe_colisao_cnpj,
    validar_proposta_cnpj,
)

from .escopo import empresa_id_do_usuario
from .models import Cliente


PADRAO_CPF = re.compile(r"^(?:\d{11}|\d{3}\.\d{3}\.\d{3}-\d{2})$")
MENSAGENS_CNPJ = {
    "cnpj_invalido": "Informe um CNPJ no formato oficial e com dígitos verificadores válidos.",
    "cnpj_legado_invalido": "O documento atual é legado inválido e exige revisão manual antes da atualização.",
    "cnpj_troca_identidade": "A troca de CPF/CNPJ exige revisão de identidade e não pode ser feita por este formulário.",
    "cnpj_nao_validado": "Não foi possível validar o CNPJ neste cadastro.",
}


class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = [
            "empresa", "nome", "cpf_cnpj", "telefone", "email",
            "indicador_ie", "inscricao_estadual", "logradouro", "numero",
            "complemento", "bairro", "codigo_municipio_ibge", "municipio", "uf", "cep",
            "is_active",
        ]
        labels = {
            "cpf_cnpj": "CPF/CNPJ",
            "is_active": "Ativo",
        }
        widgets = {
            "nome": forms.TextInput(attrs={"class": "no-upper"}),
            "cpf_cnpj": forms.TextInput(attrs={"class": "mask-cpf-cnpj"}),
            "telefone": forms.TextInput(attrs={"class": "mask-phone"}),
            "cep": forms.TextInput(attrs={"class": "mask-cep"}),
        }

    def __init__(self, *args, user=None, empresa_id_contexto=None, **kwargs):
        self.user = user
        self.empresa_id_contexto = empresa_id_contexto
        super().__init__(*args, **kwargs)
        self.fields["empresa"].queryset = Empresa.objects.filter(is_active=True).order_by("nome_fantasia")
        self.fields["empresa"].required = True
        empresa_id = empresa_id_do_usuario(user) if user else None
        empresa_fixa = empresa_id_contexto if empresa_id_contexto is not None else empresa_id
        if empresa_fixa is not None:
            self.fields["empresa"].queryset = self.fields["empresa"].queryset.filter(pk=empresa_fixa)
            self.fields["empresa"].initial = empresa_fixa or None
            self.fields["empresa"].required = False
            self.fields["empresa"].widget = forms.HiddenInput()

    def clean_empresa(self):
        empresa = self.cleaned_data.get("empresa")
        if self.empresa_id_contexto is not None:
            empresa_usuario = empresa_id_do_usuario(self.user)
            if empresa_usuario is not None and empresa_usuario != self.empresa_id_contexto:
                raise ValidationError("Empresa do cliente não corresponde ao usuário autenticado.")
            if empresa and empresa.pk != self.empresa_id_contexto:
                raise ValidationError("Empresa do cliente não corresponde ao contexto operacional.")
            empresa_contexto = Empresa.objects.filter(pk=self.empresa_id_contexto, is_active=True).first()
            if not empresa_contexto:
                raise ValidationError("Empresa do contexto operacional não está ativa.")
            return empresa_contexto
        if not self.user or self.user.is_superuser:
            return empresa
        empresa_id = empresa_id_do_usuario(self.user)
        if not empresa_id:
            raise ValidationError("Empresa do cliente não corresponde ao usuário autenticado.")
        if empresa and empresa.pk != empresa_id:
            raise ValidationError("Empresa do cliente não corresponde ao usuário autenticado.")
        return Empresa.objects.filter(pk=empresa_id, is_active=True).first()

    def clean_cpf_cnpj(self):
        valor = str(self.cleaned_data.get("cpf_cnpj") or "").strip()
        if not valor:
            return ""
        if PADRAO_CPF.fullmatch(valor):
            atual = str(getattr(self.instance, "cpf_cnpj", "") or "").strip()
            if self.instance.pk and atual != valor:
                raise ValidationError(
                    MENSAGENS_CNPJ["cnpj_troca_identidade"],
                    code="cnpj_troca_identidade",
                )
            return valor
        empresa = self.cleaned_data.get("empresa")
        if empresa is None:
            return valor
        try:
            canonico = validar_proposta_cnpj(
                valor,
                fronteira="CLIENTE_PJ",
                instance=self.instance,
                empresa_id=empresa.pk,
            )
        except ErroValidacaoEscritaCNPJ as exc:
            raise ValidationError(MENSAGENS_CNPJ[exc.codigo], code=exc.codigo) from exc
        if existe_colisao_cnpj(
            Cliente.objects.filter(empresa=empresa),
            canonico,
            campo="cpf_cnpj",
            excluir_pk=getattr(self.instance, "pk", None),
        ):
            raise ValidationError(
                "Já existe um cliente desta empresa com este CNPJ.",
                code="cnpj_colisao_canonica",
            )
        return canonico
