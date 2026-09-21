from decimal import Decimal

from apps.marketplace.models import PedidoOnline
from apps.pdv.models import Caixa
from apps.vendas.models import StatusVenda, Venda

from .models import TipoDocumentoFiscal


def origem_documento_fiscal_teste(
    *,
    filial,
    usuario,
    tipo_documento,
    valor=Decimal("0.00"),
    venda_data=None,
):
    """Cria uma origem comercial mínima e explícita para fixtures fiscais."""
    if tipo_documento == TipoDocumentoFiscal.NFE:
        return {
            "pedido_online": PedidoOnline.objects.create(
                filial=filial,
                nome_cliente="Cliente de teste da origem fiscal",
                total=valor,
                usuario=usuario,
            )
        }

    caixa = Caixa.objects.create(
        filial=filial,
        usuario_abertura=usuario,
        valor_inicial=Decimal("0.00"),
    )
    venda = Venda.objects.create(
        filial=filial,
        caixa=caixa,
        usuario=usuario,
        total_bruto=valor,
        total_liquido=valor,
        status=StatusVenda.FINALIZADA,
    )
    if venda_data is not None:
        Venda.objects.filter(pk=venda.pk).update(data=venda_data)
        venda.refresh_from_db()
    return {"venda": venda}
