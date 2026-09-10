from datetime import timedelta

from django import forms
from django.utils import timezone

from apps.vendas.models import TipoDocumentoConsumidor

from .models import Caixa, Sangria, Suprimento


class AdicionarItemForm(forms.Form):
    busca = forms.CharField(
        label="Produto",
        max_length=255,
        widget=forms.TextInput(attrs={"autofocus": "autofocus", "autocomplete": "off", "placeholder": "Código de barras ou nome"}),
    )
    quantidade = forms.DecimalField(
        label="Quantidade",
        max_digits=12,
        decimal_places=3,
        min_value=0.001,
        initial=1,
        widget=forms.NumberInput(attrs={"step": "0.001", "inputmode": "decimal"}),
    )


class AbrirCaixaForm(forms.ModelForm):
    class Meta:
        model = Caixa
        fields = ["filial", "valor_inicial"]

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.accounts.permissions import ADMINISTRACAO, has_role
        from apps.empresas.models import Filial

        filiais = Filial.objects.filter(is_active=True)
        if user and not user.is_superuser:
            perfil = getattr(user, "perfil_supermercado", None)
            if not perfil or not perfil.is_active or not perfil.filial_id:
                filiais = filiais.none()
            elif has_role(user, ADMINISTRACAO):
                filiais = filiais.filter(empresa_id=perfil.filial.empresa_id)
            else:
                filiais = filiais.filter(id=perfil.filial_id)
        self.fields["filial"].queryset = filiais
        self.fields["valor_inicial"].widget.attrs.update(
            {
                "step": "0.01",
                "min": "0",
                "inputmode": "decimal",
                "data-pdv-modal-autofocus": "true",
            }
        )


class FinalizarVendaForm(forms.Form):
    caixa = forms.ModelChoiceField(label="Caixa", queryset=Caixa.objects.none())
    cliente = forms.ModelChoiceField(label="Cliente", queryset=None, required=False, empty_label="Cliente avulso")
    cpf_na_nota = forms.ChoiceField(
        label="CPF na nota?",
        choices=(("NAO", "Não"), ("SIM", "Sim")),
        required=False,
        widget=forms.RadioSelect(attrs={"class": "pdv-cpf-choice"}),
    )
    documento_consumidor_tipo = forms.ChoiceField(
        label="Documento na nota",
        choices=TipoDocumentoConsumidor.choices,
        required=False,
        initial=TipoDocumentoConsumidor.NAO_IDENTIFICADO,
        widget=forms.HiddenInput(),
    )
    documento_consumidor = forms.CharField(
        label="CPF na nota",
        required=False,
        max_length=32,
        widget=forms.TextInput(attrs={"autocomplete": "off", "inputmode": "numeric", "placeholder": "Digite os 11 números"}),
    )
    desconto = forms.DecimalField(label="Desconto", max_digits=12, decimal_places=2, min_value=0, initial=0)
    vencimento_financeiro = forms.DateField(
        label="Vencimento crediario",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    valor_recebido = forms.DecimalField(
        label="Pago pelo cliente",
        max_digits=12,
        decimal_places=2,
        min_value=0,
        required=False,
        widget=forms.NumberInput(attrs={"step": "0.01", "inputmode": "decimal"}),
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.clientes.escopo import clientes_para_usuario
        from apps.clientes.models import Cliente
        from apps.vendas.models import FormaPagamento

        self.fields["caixa"].queryset = Caixa.objects.filter(status="ABERTO")
        if user and not user.is_superuser:
            perfil = getattr(user, "perfil_supermercado", None)
            if perfil and perfil.is_active and perfil.filial_id:
                self.fields["caixa"].queryset = self.fields["caixa"].queryset.filter(
                    filial__empresa_id=perfil.filial.empresa_id,
                    usuario_abertura=user,
                )
            else:
                self.fields["caixa"].queryset = self.fields["caixa"].queryset.none()
        primeiro_caixa = self.fields["caixa"].queryset.first()
        if primeiro_caixa:
            self.fields["caixa"].initial = primeiro_caixa
        self.fields["cliente"].queryset = clientes_para_usuario(user, Cliente.objects.filter(is_active=True))
        self.fields["vencimento_financeiro"].initial = timezone.localdate() + timedelta(days=30)

    def clean(self):
        dados = super().clean()
        decisao = dados.get("cpf_na_nota")
        if decisao == "SIM":
            dados["documento_consumidor_tipo"] = TipoDocumentoConsumidor.CPF
            if not str(dados.get("documento_consumidor") or "").strip():
                self.add_error("documento_consumidor", "Informe o CPF solicitado pelo consumidor.")
        else:
            dados["documento_consumidor_tipo"] = TipoDocumentoConsumidor.NAO_IDENTIFICADO
            dados["documento_consumidor"] = ""
        return dados


class PreVendaForm(forms.Form):
    filial = forms.ModelChoiceField(label="Filial", queryset=None)
    cliente = forms.ModelChoiceField(label="Cliente", queryset=None, required=False, empty_label="Cliente avulso")
    desconto = forms.DecimalField(label="Desconto", max_digits=12, decimal_places=2, min_value=0, initial=0)
    validade = forms.DateField(label="Validade", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    observacao = forms.CharField(label="Observacao", required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.clientes.escopo import clientes_para_usuario
        from apps.clientes.models import Cliente
        from apps.empresas.models import Filial

        self.fields["filial"].queryset = Filial.objects.filter(is_active=True)
        if user and not user.is_superuser:
            perfil = getattr(user, "perfil_supermercado", None)
            if perfil and perfil.filial_id:
                self.fields["filial"].queryset = self.fields["filial"].queryset.filter(empresa_id=perfil.filial.empresa_id)
        primeira_filial = self.fields["filial"].queryset.first()
        if primeira_filial:
            self.fields["filial"].initial = primeira_filial
        self.fields["cliente"].queryset = clientes_para_usuario(user, Cliente.objects.filter(is_active=True))
        self.fields["validade"].initial = timezone.localdate() + timedelta(days=7)


class EntregaPdvForm(forms.Form):
    cliente = forms.ModelChoiceField(label="Cliente", queryset=None, required=False, widget=forms.HiddenInput(attrs={"id": "id_entrega_cliente"}))
    nome_cliente = forms.CharField(
        label="Nome do cliente",
        max_length=150,
        widget=forms.TextInput(
            attrs={
                "autocomplete": "off",
                "data-delivery-client-search": "1",
                "role": "combobox",
                "aria-autocomplete": "list",
                "aria-expanded": "false",
                "aria-controls": "pdv-delivery-client-results",
            }
        ),
    )
    telefone = forms.CharField(label="Telefone", max_length=30, required=False)
    endereco_entrega = forms.CharField(
        label="Endereço de entrega", required=False, widget=forms.Textarea(attrs={"rows": 2})
    )
    bairro_entrega = forms.CharField(label="Bairro", max_length=120, required=False)
    distancia_entrega_km = forms.DecimalField(
        label="Distância até o cliente (km)", max_digits=7, decimal_places=2, min_value=0, required=False
    )
    observacoes = forms.CharField(label="Observações", required=False, widget=forms.Textarea(attrs={"rows": 2}))
    salvar_cliente = forms.BooleanField(
        label="Salvar cliente para próximas entregas",
        required=False,
        help_text="Opcional. Sem marcar, o pedido será criado como cliente avulso.",
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.clientes.escopo import clientes_para_usuario
        from apps.clientes.models import Cliente

        self.fields["cliente"].queryset = clientes_para_usuario(user, Cliente.objects.filter(is_active=True))

    def clean(self):
        cleaned_data = super().clean()
        cliente = cleaned_data.get("cliente")
        if cliente:
            cleaned_data["nome_cliente"] = cliente.nome
            cleaned_data["telefone"] = cleaned_data.get("telefone") or cliente.telefone
            cleaned_data["endereco_entrega"] = cleaned_data.get("endereco_entrega") or cliente.endereco
            cleaned_data["salvar_cliente"] = False
        if not (cleaned_data.get("endereco_entrega") or "").strip():
            self.add_error("endereco_entrega", "Informe o endereço para o pedido de entrega.")
        return cleaned_data

class SangriaForm(forms.ModelForm):
    class Meta:
        model = Sangria
        fields = ["valor", "motivo"]


class SuprimentoForm(forms.ModelForm):
    class Meta:
        model = Suprimento
        fields = ["valor", "motivo"]


class FecharCaixaForm(forms.ModelForm):
    class Meta:
        model = Caixa
        fields = ["valor_final"]


class ConferirCaixaForm(forms.ModelForm):
    class Meta:
        model = Caixa
        fields = ["valor_conferido", "observacao_conferencia"]
