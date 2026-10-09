from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.urls import reverse_lazy
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import CreateView, ListView, UpdateView

from apps.accounts.permissions import CLIENTES, RoleRequiredMixin, role_required

from .escopo import clientes_para_usuario, empresa_id_do_usuario
from .forms import ClienteForm
from .models import Cliente


def _tipo_documento_fiscal_cliente(cliente):
    from apps.marketplace.documentos_destinatario import normalizar_documento_cliente
    from apps.vendas.models import TipoDocumentoConsumidor

    tipo, _ = normalizar_documento_cliente(
        TipoDocumentoConsumidor.NAO_IDENTIFICADO, cliente.cpf_cnpj, inferir=True,
    )
    return tipo


class ClienteListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    required_roles = CLIENTES
    model = Cliente
    template_name = "clientes/cliente_list.html"
    context_object_name = "clientes"
    paginate_by = 30

    def get_queryset(self):
        queryset = clientes_para_usuario(self.request.user, Cliente.objects.select_related("empresa")).order_by("nome")
        termo = self.request.GET.get("q")
        if termo:
            queryset = queryset.filter(Q(nome__icontains=termo) | Q(cpf_cnpj__icontains=termo))
        return queryset


class ClienteFormMixin:
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        empresa_id = empresa_id_do_usuario(self.request.user)
        if empresa_id is not None:
            form.instance.empresa_id = empresa_id
        return super().form_valid(form)


class ClienteCreateView(ClienteFormMixin, LoginRequiredMixin, RoleRequiredMixin, CreateView):
    required_roles = CLIENTES
    model = Cliente
    form_class = ClienteForm
    template_name = "clientes/cliente_form.html"
    success_url = reverse_lazy("clientes:lista")

    def form_valid(self, form):
        messages.success(self.request, "Cliente cadastrado com sucesso.")
        return super().form_valid(form)


class ClienteUpdateView(ClienteFormMixin, LoginRequiredMixin, RoleRequiredMixin, UpdateView):
    required_roles = CLIENTES
    model = Cliente
    form_class = ClienteForm
    template_name = "clientes/cliente_form.html"
    success_url = reverse_lazy("clientes:lista")

    def get_queryset(self):
        return clientes_para_usuario(self.request.user, Cliente.objects.all())

    def form_valid(self, form):
        messages.success(self.request, "Cliente atualizado com sucesso.")
        return super().form_valid(form)


@role_required(*CLIENTES)
@require_POST
def criar_cliente_pdv(request):
    from apps.pdv.views import _filial_entrega_pdv

    filial = _filial_entrega_pdv(request)
    form = ClienteForm(
        request.POST, user=request.user,
        empresa_id_contexto=filial.empresa_id if filial else None,
    )
    if not form.is_valid():
        return JsonResponse({"errors": form.errors.get_json_data()}, status=400)
    cliente = form.save()
    return JsonResponse({"id": cliente.pk, "nome": cliente.nome, "telefone": cliente.telefone, "endereco": cliente.endereco_principal})


@role_required(*CLIENTES)
@require_GET
def clientes_busca(request):
    termo = (request.GET.get("q") or request.GET.get("term") or "").strip()
    clientes = clientes_para_usuario(request.user, Cliente.objects.filter(is_active=True))
    if termo:
        clientes = clientes.filter(
            Q(nome__icontains=termo) | Q(cpf_cnpj__icontains=termo) | Q(telefone__icontains=termo)
        )
    pagina = Paginator(clientes.order_by("nome"), 20).get_page(request.GET.get("page"))
    return JsonResponse(
        {
            "results": [
                {
                    "id": cliente.pk,
                    "text": f"{cliente.nome} | {cliente.cpf_cnpj or cliente.telefone or 'sem documento'}",
                    "nome": cliente.nome,
                    "cpf_cnpj": cliente.cpf_cnpj,
                    "documento_fiscal_tipo": _tipo_documento_fiscal_cliente(cliente),
                    "telefone": cliente.telefone,
                    "email": cliente.email,
                    "endereco": cliente.endereco_principal,
                    "endereco_legado": bool(cliente.endereco.strip() and not cliente.logradouro.strip()),
                    "indicador_ie": cliente.indicador_ie,
                    "inscricao_estadual": cliente.inscricao_estadual,
                    "logradouro": cliente.logradouro,
                    "numero": cliente.numero,
                    "complemento": cliente.complemento,
                    "bairro": cliente.bairro,
                    "codigo_municipio_ibge": cliente.codigo_municipio_ibge,
                    "municipio": cliente.municipio,
                    "uf": cliente.uf,
                    "cep": cliente.cep,
                }
                for cliente in pagina.object_list
            ],
            "pagination": {"more": pagina.has_next()},
        }
    )
