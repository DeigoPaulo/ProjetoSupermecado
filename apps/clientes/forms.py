from django import forms

from .models import Cliente


class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ["nome", "cpf_cnpj", "telefone", "email", "endereco", "is_active"]
        widgets = {
            "nome": forms.TextInput(attrs={"class": "no-upper"}),
            "cpf_cnpj": forms.TextInput(attrs={"class": "mask-cpf-cnpj"}),
            "telefone": forms.TextInput(attrs={"class": "mask-phone"}),
            "endereco": forms.Textarea(attrs={"rows": 3}),
        }
