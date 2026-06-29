from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

from .forms import FornecedorForm
from .models import Fornecedor


class FornecedorListView(LoginRequiredMixin, ListView):
    model = Fornecedor
    template_name = "fornecedores/fornecedor_list.html"
    context_object_name = "fornecedores"
    paginate_by = 30

    def get_queryset(self):
        queryset = Fornecedor.objects.order_by("razao_social")
        termo = self.request.GET.get("q")
        if termo:
            queryset = queryset.filter(razao_social__icontains=termo) | queryset.filter(nome_fantasia__icontains=termo) | queryset.filter(cnpj__icontains=termo)
        return queryset


class FornecedorCreateView(LoginRequiredMixin, CreateView):
    model = Fornecedor
    form_class = FornecedorForm
    template_name = "fornecedores/fornecedor_form.html"
    success_url = reverse_lazy("fornecedores:lista")

    def form_valid(self, form):
        messages.success(self.request, "Fornecedor cadastrado com sucesso.")
        return super().form_valid(form)


class FornecedorUpdateView(LoginRequiredMixin, UpdateView):
    model = Fornecedor
    form_class = FornecedorForm
    template_name = "fornecedores/fornecedor_form.html"
    success_url = reverse_lazy("fornecedores:lista")

    def form_valid(self, form):
        messages.success(self.request, "Fornecedor atualizado com sucesso.")
        return super().form_valid(form)

# Create your views here.
