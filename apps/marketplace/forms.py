from django import forms
from django.forms import inlineformset_factory

from apps.produtos.models import Produto

from .models import FaixaTaxaEntrega, FormaPagamentoPedido, IntegracaoMarketplace, ItemPedidoOnline, PedidoOnline, PoliticaEntrega


class PedidoOnlineForm(forms.ModelForm):
    class Meta:
        model = PedidoOnline
        fields = ["filial", "cliente", "nome_cliente", "telefone", "canal", "tipo_entrega", "endereco_entrega", "referencia_externa", "taxa_entrega", "desconto", "observacoes"]
        widgets = {
            "endereco_entrega": forms.Textarea(attrs={"rows": 2}),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }


class ItemPedidoOnlineForm(forms.ModelForm):
    class Meta:
        model = ItemPedidoOnline
        fields = ["produto", "quantidade", "preco_unitario"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["produto"].queryset = Produto.objects.filter(vendido_no_marketplace=True).order_by("nome")


class PagamentoPedidoForm(forms.Form):
    forma_pagamento = forms.ChoiceField(choices=FormaPagamentoPedido.choices)
    valor_pago = forms.DecimalField(max_digits=12, decimal_places=2, min_value=0.01)


class IntegracaoMarketplaceForm(forms.ModelForm):
    class Meta:
        model = IntegracaoMarketplace
        fields = ["nome", "filial", "is_active"]


class PoliticaEntregaForm(forms.ModelForm):
    class Meta:
        model = PoliticaEntrega
        fields = ["filial", "raio_maximo_km", "valor_minimo_pedido", "frete_gratis_acima", "bairros_atendidos", "bairros_bloqueados", "horarios_entrega", "permite_retirada", "is_active"]
        widgets = {
            "bairros_atendidos": forms.Textarea(attrs={"rows": 2}),
            "bairros_bloqueados": forms.Textarea(attrs={"rows": 2}),
            "horarios_entrega": forms.Textarea(attrs={"rows": 2}),
        }


FaixaTaxaEntregaFormSet = inlineformset_factory(
    PoliticaEntrega,
    FaixaTaxaEntrega,
    fields=["distancia_inicial_km", "distancia_final_km", "taxa"],
    extra=4,
    can_delete=True,
)


class CalcularEntregaForm(forms.Form):
    distancia_entrega_km = forms.DecimalField(label="Distancia ate o cliente (km)", max_digits=7, decimal_places=2, min_value=0)
