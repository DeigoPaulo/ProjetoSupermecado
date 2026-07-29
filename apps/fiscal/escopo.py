from apps.clientes.escopo import empresa_id_do_usuario
from apps.empresas.models import Filial
from apps.vendas.models import Venda

from .models import ConfiguracaoFiscal, DocumentoFiscal, SerieFiscal


def _por_empresa_do_usuario(user, queryset, lookup_empresa):
    empresa_id = empresa_id_do_usuario(user)
    if empresa_id is None:
        return queryset
    return queryset.filter(**{lookup_empresa: empresa_id})


def filiais_para_usuario(user, queryset=None):
    queryset = queryset if queryset is not None else Filial.objects.all()
    return _por_empresa_do_usuario(user, queryset, "empresa_id")


def configuracoes_para_usuario(user, queryset=None):
    queryset = queryset if queryset is not None else ConfiguracaoFiscal.objects.all()
    return _por_empresa_do_usuario(user, queryset, "filial__empresa_id")


def series_para_usuario(user, queryset=None):
    queryset = queryset if queryset is not None else SerieFiscal.objects.all()
    return _por_empresa_do_usuario(user, queryset, "filial__empresa_id")


def documentos_para_usuario(user, queryset=None):
    queryset = queryset if queryset is not None else DocumentoFiscal.objects.all()
    return _por_empresa_do_usuario(user, queryset, "filial__empresa_id")


def vendas_para_usuario(user, queryset=None):
    queryset = queryset if queryset is not None else Venda.objects.all()
    return _por_empresa_do_usuario(user, queryset, "filial__empresa_id")
