from apps.clientes.escopo import empresa_id_do_usuario

from .models import CotacaoCompra, EntradaCompra, PedidoCompra, RespostaCotacaoFornecedor


def _por_empresa_do_usuario(user, queryset, lookup_empresa):
    empresa_id = empresa_id_do_usuario(user)
    if empresa_id is None:
        return queryset
    return queryset.filter(**{lookup_empresa: empresa_id})


def cotacoes_para_usuario(user, queryset=None):
    queryset = queryset if queryset is not None else CotacaoCompra.objects.all()
    return _por_empresa_do_usuario(user, queryset, "filial__empresa_id")


def respostas_para_usuario(user, queryset=None):
    queryset = queryset if queryset is not None else RespostaCotacaoFornecedor.objects.all()
    return _por_empresa_do_usuario(user, queryset, "cotacao__filial__empresa_id")


def pedidos_para_usuario(user, queryset=None):
    queryset = queryset if queryset is not None else PedidoCompra.objects.all()
    return _por_empresa_do_usuario(user, queryset, "filial__empresa_id")


def entradas_para_usuario(user, queryset=None):
    queryset = queryset if queryset is not None else EntradaCompra.objects.all()
    return _por_empresa_do_usuario(user, queryset, "filial__empresa_id")