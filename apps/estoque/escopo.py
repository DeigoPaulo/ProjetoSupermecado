from django.contrib.auth import get_user_model

from apps.clientes.escopo import empresa_id_do_usuario

from apps.empresas.models import Filial

from .models import (
    AlertaSLAOrdemProducao,
    ComposicaoProduto,
    ConfiguracaoSLASetorProducao,
    DesmembramentoProduto,
    Estoque,
    InventarioEstoque,
    ItemDesmembramentoProduto,
    OrdemProducaoComposicao,
    LoteEstoque,
    MovimentacaoEstoque,
    PerdaEstoque,
    ProducaoComposicaoProduto,
    ReceitaDesmembramento,
)


def _por_empresa_do_usuario(user, queryset, lookup_empresa="filial__empresa_id"):
    empresa_id = empresa_id_do_usuario(user)
    if empresa_id is None:
        return queryset
    return queryset.filter(**{lookup_empresa: empresa_id})


def estoques_para_usuario(user, queryset=None):
    queryset = queryset if queryset is not None else Estoque.objects.all()
    return _por_empresa_do_usuario(user, queryset)


def lotes_para_usuario(user, queryset=None):
    queryset = queryset if queryset is not None else LoteEstoque.objects.all()
    return _por_empresa_do_usuario(user, queryset)


def movimentacoes_para_usuario(user, queryset=None):
    queryset = queryset if queryset is not None else MovimentacaoEstoque.objects.all()
    return _por_empresa_do_usuario(user, queryset)


def inventarios_para_usuario(user, queryset=None):
    queryset = queryset if queryset is not None else InventarioEstoque.objects.all()
    return _por_empresa_do_usuario(user, queryset)


def perdas_para_usuario(user, queryset=None):
    queryset = queryset if queryset is not None else PerdaEstoque.objects.all()
    return _por_empresa_do_usuario(user, queryset)


def filiais_para_usuario(user, queryset=None):
    queryset = queryset if queryset is not None else Filial.objects.all()
    return _por_empresa_do_usuario(user, queryset, "empresa_id")


def desmembramentos_para_usuario(user, queryset=None):
    queryset = queryset if queryset is not None else DesmembramentoProduto.objects.all()
    return _por_empresa_do_usuario(user, queryset, "empresa_id")


def itens_desmembramento_para_usuario(user, queryset=None):
    queryset = queryset if queryset is not None else ItemDesmembramentoProduto.objects.all()
    return _por_empresa_do_usuario(user, queryset, "desmembramento__empresa_id")


def receitas_desmembramento_para_usuario(user, queryset=None):
    queryset = queryset if queryset is not None else ReceitaDesmembramento.objects.all()
    return _por_empresa_do_usuario(user, queryset, "empresa_id")


def composicoes_para_usuario(user, queryset=None):
    queryset = queryset if queryset is not None else ComposicaoProduto.objects.all()
    return _por_empresa_do_usuario(user, queryset, "empresa_id")


def producoes_composicao_para_usuario(user, queryset=None):
    queryset = queryset if queryset is not None else ProducaoComposicaoProduto.objects.all()
    return _por_empresa_do_usuario(user, queryset, "empresa_id")


def ordens_producao_para_usuario(user, queryset=None):
    queryset = queryset if queryset is not None else OrdemProducaoComposicao.objects.all()
    return _por_empresa_do_usuario(user, queryset, "empresa_id")


def configuracoes_sla_para_usuario(user, queryset=None):
    queryset = queryset if queryset is not None else ConfiguracaoSLASetorProducao.objects.all()
    return _por_empresa_do_usuario(user, queryset, "empresa_id")


def alertas_sla_para_usuario(user, queryset=None):
    queryset = queryset if queryset is not None else AlertaSLAOrdemProducao.objects.all()
    return _por_empresa_do_usuario(user, queryset, "ordem__empresa_id")


def usuarios_para_usuario(user, queryset=None):
    queryset = queryset if queryset is not None else get_user_model().objects.all()
    empresa_id = empresa_id_do_usuario(user)
    if empresa_id is None:
        return queryset
    return queryset.filter(
        perfil_supermercado__is_active=True,
        perfil_supermercado__filial__empresa_id=empresa_id,
    )