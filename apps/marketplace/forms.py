from django import forms
from django.forms import inlineformset_factory

from apps.clientes.escopo import clientes_para_usuario, empresa_id_do_usuario
from apps.core_forms import aplicar_select2
from apps.produtos.models import Produto

from .models import (
    FaixaTaxaEntrega,
    FormaPagamentoPedido,
    IntegracaoMarketplace,
    ItemPedidoOnline,
    PedidoOnline,
    PoliticaEntrega,
    StatusPedido,
    TipoEntrega,
)


class PedidoOnlineForm(forms.ModelForm):
    class Meta:
        model = PedidoOnline
        fields = [
            "filial", "cliente", "nome_cliente", "documento_cliente_tipo", "documento_cliente",
            "destinatario_indicador_ie", "destinatario_inscricao_estadual",
            "destinatario_logradouro", "destinatario_numero", "destinatario_complemento",
            "destinatario_bairro", "destinatario_codigo_municipio_ibge",
            "destinatario_municipio", "destinatario_uf", "destinatario_cep",
            "telefone", "canal", "tipo_entrega", "endereco_entrega", "bairro_entrega", "referencia_externa",
            "taxa_entrega", "desconto", "observacoes",
        ]
        widgets = {
            "endereco_entrega": forms.Textarea(attrs={"rows": 2}),
            "destinatario_cep": forms.TextInput(attrs={"class": "mask-cep"}),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        empresa_id = empresa_id_do_usuario(user) if user else None
        if empresa_id is not None:
            self.fields["filial"].queryset = self.fields["filial"].queryset.filter(empresa_id=empresa_id)
        self.fields["cliente"].queryset = clientes_para_usuario(user, self.fields["cliente"].queryset)
        aplicar_select2(
            self,
            ["filial", "cliente"],
            ajax_urls={"filial": "/empresas/filiais/busca.json", "cliente": "/clientes/busca.json"},
        )

    def save(self, commit=True):
        pedido = super().save(commit=False)
        pedido.preencher_destinatario_do_cliente()
        if commit:
            pedido.save()
            self.save_m2m()
        return pedido


class ItemPedidoOnlineForm(forms.ModelForm):
    class Meta:
        model = ItemPedidoOnline
        fields = ["produto", "quantidade", "preco_unitario"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["produto"].queryset = Produto.objects.filter(vendido_no_marketplace=True).order_by("nome")
        aplicar_select2(self, ["produto"], ajax_urls={"produto": "/estoque/produtos/busca.json?marketplace=1"})


class PagamentoPedidoForm(forms.Form):
    forma_pagamento = forms.ChoiceField(choices=FormaPagamentoPedido.choices)
    valor_pago = forms.DecimalField(max_digits=12, decimal_places=2, min_value=0.01)
    referencia_pagamento = forms.CharField(
        label="NSU ou referência da transação", max_length=120, required=False,
        help_text="Obrigatório para cartão cobrado na entrega.",
    )

    def __init__(self, *args, pedido=None, **kwargs):
        super().__init__(*args, **kwargs)
        cartoes_na_entrega = {
            FormaPagamentoPedido.CARTAO_CREDITO_ENTREGA,
            FormaPagamentoPedido.CARTAO_DEBITO_ENTREGA,
        }
        pode_confirmar_cartao_entrega = (
            pedido
            and pedido.tipo_entrega == TipoEntrega.ENTREGA
            and pedido.status == StatusPedido.SAIU_ENTREGA
        )
        if not pode_confirmar_cartao_entrega:
            self.fields["forma_pagamento"].choices = [
                escolha
                for escolha in FormaPagamentoPedido.choices
                if escolha[0] not in cartoes_na_entrega
            ]


class IntegracaoMarketplaceForm(forms.ModelForm):
    class Meta:
        model = IntegracaoMarketplace
        fields = ["nome", "provedor", "filial", "is_active"]

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        empresa_id = empresa_id_do_usuario(user) if user else None
        if empresa_id is not None:
            self.fields["filial"].queryset = self.fields["filial"].queryset.filter(empresa_id=empresa_id)
        aplicar_select2(self, ["filial"], ajax_urls={"filial": "/empresas/filiais/busca.json"})


class PoliticaEntregaForm(forms.ModelForm):
    class Meta:
        model = PoliticaEntrega
        fields = [
            "filial", "raio_maximo_km", "valor_minimo_pedido", "frete_gratis_acima",
            "bairros_atendidos", "bairros_bloqueados", "horarios_entrega", "permite_retirada", "is_active",
        ]
        widgets = {
            "bairros_atendidos": forms.Textarea(attrs={"rows": 2}),
            "bairros_bloqueados": forms.Textarea(attrs={"rows": 2}),
            "horarios_entrega": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        empresa_id = empresa_id_do_usuario(user) if user else None
        if empresa_id is not None:
            self.fields["filial"].queryset = self.fields["filial"].queryset.filter(empresa_id=empresa_id)
        aplicar_select2(self, ["filial"])


FaixaTaxaEntregaFormSet = inlineformset_factory(
    PoliticaEntrega,
    FaixaTaxaEntrega,
    fields=["distancia_inicial_km", "distancia_final_km", "taxa"],
    extra=4,
    can_delete=True,
)


class CalcularEntregaForm(forms.Form):
    distancia_entrega_km = forms.DecimalField(
        label="Distância até o cliente (km)", max_digits=7, decimal_places=2, min_value=0
    )
    bairro_entrega = forms.CharField(label="Bairro", max_length=120, required=False)