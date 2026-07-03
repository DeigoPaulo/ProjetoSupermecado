from django import forms
from django.contrib.auth.models import User
from django.db import transaction

from .models import PerfilUsuario, TipoPerfil


class UsuarioPerfilForm(forms.Form):
    username = forms.CharField(label="Usuario", max_length=150, widget=forms.TextInput(attrs={"class": "no-upper"}))
    first_name = forms.CharField(label="Nome", max_length=150, required=False)
    last_name = forms.CharField(label="Sobrenome", max_length=150, required=False)
    email = forms.EmailField(label="Email", required=False)
    password = forms.CharField(label="Senha", required=False, widget=forms.PasswordInput)
    tipo = forms.ChoiceField(label="Perfil", choices=TipoPerfil.choices)
    filial = forms.ModelChoiceField(
        label="Filial",
        queryset=None,
        required=False,
        widget=forms.Select(attrs={"class": "select2-field", "data-placeholder": "Pesquise a filial"}),
    )
    telefone = forms.CharField(label="Telefone", max_length=30, required=False, widget=forms.TextInput(attrs={"class": "mask-phone"}))
    is_active = forms.BooleanField(label="Ativo", required=False, initial=True)
    is_staff = forms.BooleanField(label="Acesso ao admin Django", required=False)

    def __init__(self, *args, instance=None, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.empresas.models import Filial

        self.instance = instance
        self.fields["filial"].queryset = Filial.objects.filter(is_active=True)

        if instance:
            perfil = getattr(instance, "perfil_supermercado", None)
            self.fields["password"].help_text = "Deixe em branco para manter a senha atual."
            self.initial.update(
                {
                    "username": instance.username,
                    "first_name": instance.first_name,
                    "last_name": instance.last_name,
                    "email": instance.email,
                    "is_active": instance.is_active,
                    "is_staff": instance.is_staff,
                    "tipo": perfil.tipo if perfil else TipoPerfil.OPERADOR_CAIXA,
                    "filial": perfil.filial if perfil else None,
                    "telefone": perfil.telefone if perfil else "",
                }
            )
        else:
            self.fields["password"].required = True

    def clean_username(self):
        username = self.cleaned_data["username"]
        qs = User.objects.filter(username=username)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Ja existe um usuario com este login.")
        return username

    @transaction.atomic
    def save(self):
        user = self.instance or User()
        user.username = self.cleaned_data["username"]
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        user.email = self.cleaned_data["email"]
        user.is_active = self.cleaned_data["is_active"]
        user.is_staff = self.cleaned_data["is_staff"]
        if self.cleaned_data["password"]:
            user.set_password(self.cleaned_data["password"])
        user.save()

        perfil, _ = PerfilUsuario.objects.get_or_create(usuario=user)
        perfil.tipo = self.cleaned_data["tipo"]
        perfil.filial = self.cleaned_data["filial"]
        perfil.telefone = self.cleaned_data["telefone"]
        perfil.is_active = self.cleaned_data["is_active"]
        perfil.save()
        return user
