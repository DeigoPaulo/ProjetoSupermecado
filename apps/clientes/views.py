from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import JsonResponse
from django.urls import reverse_lazy
from django.views.decorators.http import require_GET
from django.views.generic import CreateView, ListView, UpdateView

from apps.accounts.permissions import CLIENTES, RoleRequiredMixin, role_required

from .forms import ClienteForm
from .models import Cliente


class ClienteListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    required_roles = CLIENTES
    model = Cliente
    template_name = "clientes/cliente_list.html"
    context_object_name = "clientes"
    paginate_by = 30

    def get_queryset(self):
        queryset = Cliente.objects.order_by("nome")
        termo = self.request.GET.get("q")
        if termo:
            queryset = queryset.filter(nome__icontains=termo) | queryset.filter(cpf_cnpj__icontains=termo)
        return queryset


class ClienteCreateView(LoginRequiredMixin, RoleRequiredMixin, CreateView):
    required_roles = CLIENTES
    model = Cliente
    form_class = ClienteForm
    template_name = "clientes/cliente_form.html"
    success_url = reverse_lazy("clientes:lista")

    def form_valid(self, form):
        messages.success(self.request, "Cliente cadastrado com sucesso.")
        return super().form_valid(form)


class ClienteUpdateView(LoginRequiredMixin, RoleRequiredMixin, UpdateView):
    required_roles = CLIENTES
    model = Cliente
    form_class = ClienteForm
    template_name = "clientes/cliente_form.html"
    success_url = reverse_lazy("clientes:lista")

    def form_valid(self, form):
        messages.success(self.request, "Cliente atualizado com sucesso.")
        return super().form_valid(form)


@role_required(*CLIENTES)
@require_GET
def clientes_busca(request):
    termo = (request.GET.get("q") or request.GET.get("term") or "").strip()
    if not termo:
        return JsonResponse({"results": []})
    clientes = (
        Cliente.objects.filter(Q(nome__icontains=termo) | Q(cpf_cnpj__icontains=termo) | Q(telefone__icontains=termo))
        .order_by("nome")[:20]
    )
    return JsonResponse(
        {
            "results": [
                {
                    "id": cliente.pk,
                    "text": f"{cliente.nome} | {cliente.cpf_cnpj or cliente.telefone or 'sem documento'}",
                    "nome": cliente.nome,
                    "cpf_cnpj": cliente.cpf_cnpj,
                    "telefone": cliente.telefone,
                }
                for cliente in clientes
            ]
        }
    )

# Create your views here.
