from django import forms
from django.core.exceptions import ValidationError

from apps.empresas.models import Empresa

from .escopo import empresa_id_do_usuario
from .models import Cliente


class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ["empresa", "nome", "cpf_cnpj", "telefone", "email", "endereco", "is_active"]
        widgets = {
            "nome": forms.TextInput(attrs={"class": "no-upper"}),
            "cpf_cnpj": forms.TextInput(attrs={"class": "mask-cpf-cnpj"}),
            "telefone": forms.TextInput(attrs={"class": "mask-phone"}),
            "endereco": forms.Textarea(attrs={"rows": 3}),
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
            raise ValidationError("Empresa do cliente nao corresponde ao usuario autenticado.")
        return empresa