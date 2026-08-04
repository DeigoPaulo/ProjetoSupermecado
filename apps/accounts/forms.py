from django import forms
from django.contrib.auth.models import User
from django.db import transaction

from apps.empresas.models import AcaoPinSupervisor, Empresa

from .models import CredencialAutorizacao, PerfilUsuario, TipoPerfil, TipoCredencialAutorizacao


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

    def __init__(self, *args, instance=None, filiais_queryset=None, permite_staff=True, exige_filial=False, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.empresas.models import Filial

        self.instance = instance
        self.fields["filial"].queryset = filiais_queryset if filiais_queryset is not None else Filial.objects.filter(is_active=True)
        self.fields["filial"].required = exige_filial
        if not permite_staff:
            self.fields.pop("is_staff")

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
            raise forms.ValidationError("Ja existe um usuário com este login.")
        return username

    @transaction.atomic
    def save(self):
        user = self.instance or User()
        user.username = self.cleaned_data["username"]
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        user.email = self.cleaned_data["email"]
        user.is_active = self.cleaned_data["is_active"]
        if "is_staff" in self.cleaned_data:
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

class CredencialAutorizacaoForm(forms.ModelForm):
    identificador = forms.CharField(
        label="Leitura do cartão ou crachá",
        max_length=255,
        widget=forms.PasswordInput(
            render_value=True,
            attrs={"autocomplete": "off", "autofocus": True, "class": "no-upper"},
        ),
        help_text="Aproxime, passe ou leia a credencial. O valor original não será armazenado.",
    )
    pin = forms.CharField(
        label="PIN adicional",
        required=False,
        max_length=20,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password", "inputmode": "numeric"}),
        help_text="Opcional. Recomendado para estornos e operações de maior risco.",
    )

    class Meta:
        model = CredencialAutorizacao
        fields = ["usuario", "tipo", "nome", "valida_ate"]
        widgets = {"valida_ate": forms.DateTimeInput(attrs={"type": "datetime-local"})}

    def __init__(self, *args, usuarios_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        if usuarios_queryset is not None:
            self.fields["usuario"].queryset = usuarios_queryset

    def clean_identificador(self):
        identificador = self.cleaned_data["identificador"].strip()
        identificador_hash = CredencialAutorizacao.calcular_hash(identificador)
        if CredencialAutorizacao.objects.filter(identificador_hash=identificador_hash).exists():
            raise forms.ValidationError("Esta credencial já está cadastrada.")
        return identificador

    def save(self, *, criada_por, commit=True):
        credencial = super().save(commit=False)
        credencial.definir_identificador(self.cleaned_data["identificador"])
        credencial.definir_pin(self.cleaned_data.get("pin"))
        credencial.criada_por = criada_por
        if commit:
            credencial.save()
        return credencial


class PoliticaPinSupervisorForm(forms.ModelForm):
    acoes_credencial_exigem_pin = forms.MultipleChoiceField(
        label="Exigir cartão e PIN nestas operações",
        choices=AcaoPinSupervisor.choices,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Login e senha de supervisor continuam disponíveis como contingência.",
    )

    class Meta:
        model = Empresa
        fields = ["acoes_credencial_exigem_pin"]

    def clean_acoes_credencial_exigem_pin(self):
        validas = {valor for valor, _rotulo in AcaoPinSupervisor.choices}
        selecionadas = set(self.cleaned_data["acoes_credencial_exigem_pin"])
        invalidas = selecionadas - validas
        if invalidas:
            raise forms.ValidationError("A política contém uma operação de autorização inválida.")
        return [valor for valor, _rotulo in AcaoPinSupervisor.choices if valor in selecionadas]
