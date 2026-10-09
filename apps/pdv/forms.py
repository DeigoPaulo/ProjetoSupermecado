from datetime import timedelta

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.core_forms import QuantidadeNumberInput
from apps.clientes.models import IndicadorInscricaoEstadual
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
        widget=QuantidadeNumberInput(attrs={"step": "0.001", "inputmode": "decimal"}),
    )


class AlterarQuantidadeItemForm(forms.Form):
    quantidade = forms.DecimalField(
        label="Nova quantidade",
        max_digits=12,
        decimal_places=3,
        min_value=0.001,
        error_messages={
            "required": "Informe a nova quantidade.",
            "invalid": "Informe uma quantidade válida.",
            "min_value": "A quantidade deve ser maior que zero.",
        },
        widget=QuantidadeNumberInput(attrs={"step": "0.001", "min": "0.001", "inputmode": "decimal"}),
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
        if filiais.count() == 1:
            self.fields["filial"].initial = filiais.first()
            self.fields["filial"].widget = forms.HiddenInput()
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
        choices=(("NAO", "Não"), ("CPF", "CPF"), ("CNPJ", "CNPJ")),
        required=True,
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
        label="CPF ou CNPJ na nota",
        required=False,
        max_length=32,
        widget=forms.TextInput(attrs={"autocomplete": "off", "inputmode": "text", "placeholder": "Digite CPF ou CNPJ"}),
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
        if decisao in {"CPF", "CNPJ"}:
            tipo = (
                TipoDocumentoConsumidor.CNPJ
                if decisao == "CNPJ"
                else TipoDocumentoConsumidor.CPF
            )
            dados["documento_consumidor_tipo"] = tipo
            if not str(dados.get("documento_consumidor") or "").strip():
                self.add_error(
                    "documento_consumidor",
                    f"Informe o {tipo} solicitado pelo consumidor.",
                )
            else:
                from apps.vendas.services import _normalizar_documento_consumidor

                try:
                    _normalizar_documento_consumidor(
                        tipo,
                        dados["documento_consumidor"],
                        preparar_fiscal=True,
                    )
                except ValidationError as exc:
                    self.add_error("documento_consumidor", exc)
        elif decisao == "NAO":
            dados["documento_consumidor_tipo"] = TipoDocumentoConsumidor.NAO_IDENTIFICADO
            dados["documento_consumidor"] = ""
        return dados


class PreVendaForm(forms.Form):
    filial = forms.ModelChoiceField(label="Filial", queryset=None)
    cliente = forms.ModelChoiceField(label="Cliente", queryset=None, required=False, empty_label="Cliente avulso")
    desconto = forms.DecimalField(label="Desconto", max_digits=12, decimal_places=2, min_value=0, initial=0)
    validade = forms.DateField(label="Validade", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    observacao = forms.CharField(label="Observação", required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, user=None, filial_contexto=None, **kwargs):
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
        if filial_contexto is not None:
            self.fields["filial"].queryset = self.fields["filial"].queryset.filter(pk=filial_contexto.pk)
            self.fields["filial"].initial = filial_contexto
            self.fields["filial"].widget = forms.HiddenInput()
        self.fields["cliente"].queryset = clientes_para_usuario(user, Cliente.objects.filter(is_active=True))
        self.fields["validade"].initial = timezone.localdate() + timedelta(days=7)


class EntregaPdvForm(forms.Form):
    delivery_address_mode = forms.ChoiceField(
        choices=(("saved", "Usar endereço cadastrado"), ("other", "Informar outro endereço")), required=False,
    )
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
    entrega_cep = forms.CharField(label="CEP", max_length=9, required=False)
    entrega_logradouro = forms.CharField(label="Logradouro", max_length=120, required=False)
    entrega_numero = forms.CharField(label="Número", max_length=60, required=False)
    entrega_complemento = forms.CharField(label="Complemento", max_length=60, required=False)
    entrega_bairro = forms.CharField(label="Bairro", max_length=60, required=False)
    entrega_municipio = forms.CharField(label="Município", max_length=60, required=False)
    entrega_uf = forms.CharField(label="UF", max_length=2, required=False)
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
    documento_cliente_tipo = forms.ChoiceField(
        label="Documento na nota", choices=TipoDocumentoConsumidor.choices,
        initial=TipoDocumentoConsumidor.NAO_IDENTIFICADO,
    )
    documento_cliente = forms.CharField(label="CPF/CNPJ na nota", max_length=32, required=False)
    destinatario_indicador_ie = forms.ChoiceField(
        label="Indicador de IE", choices=[("", "Não informado"), *IndicadorInscricaoEstadual.choices], required=False
    )
    destinatario_inscricao_estadual = forms.CharField(label="Inscrição estadual", max_length=20, required=False)
    destinatario_logradouro = forms.CharField(label="Logradouro", max_length=120, required=False)
    destinatario_numero = forms.CharField(label="Número", max_length=60, required=False)
    destinatario_complemento = forms.CharField(label="Complemento", max_length=60, required=False)
    destinatario_bairro = forms.CharField(label="Bairro fiscal", max_length=60, required=False)
    destinatario_codigo_municipio_ibge = forms.CharField(label="Código IBGE", max_length=7, required=False)
    destinatario_municipio = forms.CharField(label="Município", max_length=60, required=False)
    destinatario_uf = forms.CharField(label="UF", max_length=2, required=False)
    destinatario_cep = forms.CharField(label="CEP", max_length=9, required=False)
    modo_pagamento = forms.ChoiceField(
        label="Como o cliente vai pagar?",
        choices=(("PAGAR_AGORA", "Pagar agora"), ("NA_ENTREGA", "Pagar na entrega")),
        required=False,
        initial="NA_ENTREGA",
        widget=forms.RadioSelect(),
    )
    idempotency_key = forms.CharField(widget=forms.HiddenInput(), max_length=80, required=False)

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
            if cleaned_data.get("delivery_address_mode") == "saved":
                if not cliente.endereco_principal:
                    self.add_error("delivery_address_mode", "Cliente sem endereço cadastrado.")
                cleaned_data["endereco_entrega"] = cliente.endereco_principal
                cleaned_data["bairro_entrega"] = cliente.bairro or cleaned_data.get("bairro_entrega") or ""
            elif not cleaned_data.get("delivery_address_mode"):
                cleaned_data["endereco_entrega"] = cleaned_data.get("endereco_entrega") or cliente.endereco_principal
            cleaned_data["salvar_cliente"] = False
            for destino, origem in {
                "documento_cliente": "cpf_cnpj",
                "destinatario_indicador_ie": "indicador_ie",
                "destinatario_inscricao_estadual": "inscricao_estadual",
                "destinatario_logradouro": "logradouro",
                "destinatario_numero": "numero",
                "destinatario_complemento": "complemento",
                "destinatario_bairro": "bairro",
                "destinatario_codigo_municipio_ibge": "codigo_municipio_ibge",
                "destinatario_municipio": "municipio",
                "destinatario_uf": "uf",
                "destinatario_cep": "cep",
            }.items():
                if not cleaned_data.get(destino):
                    cleaned_data[destino] = getattr(cliente, origem, "") or ""
        if cleaned_data.get("delivery_address_mode") == "other":
            campos = ("entrega_cep", "entrega_logradouro", "entrega_numero", "entrega_bairro", "entrega_municipio", "entrega_uf")
            for campo in campos:
                if not str(cleaned_data.get(campo) or "").strip():
                    self.add_error(campo, "Informe este campo do endereço de entrega.")
            if not any(campo in self.errors for campo in campos):
                partes = [
                    f"{cleaned_data['entrega_logradouro'].strip()}, {cleaned_data['entrega_numero'].strip()}",
                    cleaned_data.get("entrega_complemento", "").strip(),
                    cleaned_data["entrega_bairro"].strip(),
                    f"{cleaned_data['entrega_municipio'].strip()}/{cleaned_data['entrega_uf'].strip().upper()}",
                    f"CEP {cleaned_data['entrega_cep'].strip()}",
                ]
                cleaned_data["endereco_entrega"] = " - ".join(parte for parte in partes if parte)
                cleaned_data["bairro_entrega"] = cleaned_data["entrega_bairro"].strip()
        from apps.marketplace.documentos_destinatario import normalizar_documento_cliente

        try:
            tipo, documento = normalizar_documento_cliente(
                cleaned_data.get("documento_cliente_tipo"), cleaned_data.get("documento_cliente"),
                inferir=cleaned_data.get("documento_cliente_tipo") == TipoDocumentoConsumidor.NAO_IDENTIFICADO,
            )
            cleaned_data["documento_cliente_tipo"] = tipo
            cleaned_data["documento_cliente"] = documento
        except ValidationError as exc:
            self.add_error("documento_cliente", exc)
        cleaned_data["modo_pagamento"] = cleaned_data.get("modo_pagamento") or "NA_ENTREGA"
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
