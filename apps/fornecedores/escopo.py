from apps.clientes.escopo import empresa_id_do_usuario

from .models import Fornecedor


def fornecedores_para_usuario(user, queryset=None):
    queryset = queryset if queryset is not None else Fornecedor.objects.all()
    empresa_id = empresa_id_do_usuario(user)
    if empresa_id is None:
        return queryset
    return queryset.filter(empresa_id=empresa_id)