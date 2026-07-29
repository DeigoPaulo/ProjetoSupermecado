from apps.clientes.escopo import empresa_id_do_usuario

from .models import IntegracaoMarketplace, PedidoOnline, PoliticaEntrega


def _por_empresa_do_usuario(user, queryset, lookup_empresa):
    empresa_id = empresa_id_do_usuario(user)
    if empresa_id is None:
        return queryset
    return queryset.filter(**{lookup_empresa: empresa_id})


def pedidos_para_usuario(user, queryset=None):
    queryset = queryset if queryset is not None else PedidoOnline.objects.all()
    return _por_empresa_do_usuario(user, queryset, "filial__empresa_id")


def integracoes_para_usuario(user, queryset=None):
    queryset = queryset if queryset is not None else IntegracaoMarketplace.objects.all()
    return _por_empresa_do_usuario(user, queryset, "filial__empresa_id")


def politicas_para_usuario(user, queryset=None):
    queryset = queryset if queryset is not None else PoliticaEntrega.objects.all()
    return _por_empresa_do_usuario(user, queryset, "filial__empresa_id")