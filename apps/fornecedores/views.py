from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.urls import reverse_lazy
from django.views.decorators.http import require_GET
from django.views.generic import CreateView, ListView, UpdateView

from apps.accounts.permissions import COMPRAS, RoleRequiredMixin, role_required
from apps.clientes.escopo import empresa_id_do_usuario

from .escopo import fornecedores_para_usuario
from .forms import FornecedorForm
from .models import Fornecedor


class FornecedorListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    required_roles = COMPRAS
    model = Fornecedor
    template_name = "fornecedores/fornecedor_list.html"
    context_object_name = "fornecedores"
    paginate_by = 30

    def get_queryset(self):
        queryset = fornecedores_para_usuario(
            self.request.user,
            Fornecedor.objects.select_related("empresa"),
        ).order_by("razao_social")
        termo = (self.request.GET.get("q") or "").strip()
        if termo:
            queryset = queryset.filter(
                Q(razao_social__icontains=termo)
                | Q(nome_fantasia__icontains=termo)
                | Q(cnpj__icontains=termo)
            )
        return queryset


class FornecedorFormMixin:
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        empresa_id = empresa_id_do_usuario(self.request.user)
        if empresa_id is not None:
            form.instance.empresa_id = empresa_id
        return super().form_valid(form)


class FornecedorCreateView(FornecedorFormMixin, LoginRequiredMixin, RoleRequiredMixin, CreateView):
    required_roles = COMPRAS
    model = Fornecedor
    form_class = FornecedorForm
    template_name = "fornecedores/fornecedor_form.html"
    success_url = reverse_lazy("fornecedores:lista")

    def form_valid(self, form):
        messages.success(self.request, "Fornecedor cadastrado com sucesso.")
        return super().form_valid(form)


class FornecedorUpdateView(FornecedorFormMixin, LoginRequiredMixin, RoleRequiredMixin, UpdateView):
    required_roles = COMPRAS
    model = Fornecedor
    form_class = FornecedorForm
    template_name = "fornecedores/fornecedor_form.html"
    success_url = reverse_lazy("fornecedores:lista")

    def get_queryset(self):
        return fornecedores_para_usuario(self.request.user, Fornecedor.objects.all())

    def form_valid(self, form):
        messages.success(self.request, "Fornecedor atualizado com sucesso.")
        return super().form_valid(form)


@role_required(*COMPRAS)
@require_GET
def fornecedores_busca(request):
    termo = (request.GET.get("q") or request.GET.get("term") or "").strip()
    fornecedores = fornecedores_para_usuario(request.user, Fornecedor.objects.all())
    if termo:
        fornecedores = fornecedores.filter(
            Q(razao_social__icontains=termo)
            | Q(nome_fantasia__icontains=termo)
            | Q(cnpj__icontains=termo)
        )
    pagina = Paginator(fornecedores.order_by("razao_social"), 20).get_page(request.GET.get("page"))
    return JsonResponse(
        {
            "results": [
                {
                    "id": fornecedor.pk,
                    "text": f"{fornecedor.nome_fantasia or fornecedor.razao_social} | {fornecedor.cnpj or 'sem CNPJ'}",
                    "razao_social": fornecedor.razao_social,
                    "nome_fantasia": fornecedor.nome_fantasia,
                    "cnpj": fornecedor.cnpj,
                }
                for fornecedor in pagina.object_list
            ],
            "pagination": {"more": pagina.has_next()},
        }
    )