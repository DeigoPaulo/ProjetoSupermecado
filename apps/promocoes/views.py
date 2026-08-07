from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

from apps.accounts.permissions import CADASTROS, RoleRequiredMixin

from .forms import PromocaoProdutoForm
from .models import PromocaoProduto


class PromocaoListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    required_roles = CADASTROS
    model = PromocaoProduto
    template_name = "promocoes/promocao_list.html"
    context_object_name = "promocoes"
    paginate_by = 30

    def get_queryset(self):
        queryset = PromocaoProduto.objects.select_related("produto", "criado_por").order_by("-inicio")
        termo = self.request.GET.get("q")
        if termo:
            queryset = queryset.filter(nome__icontains=termo) | queryset.filter(produto__nome__icontains=termo)
        return queryset


class PromocaoCreateView(LoginRequiredMixin, RoleRequiredMixin, CreateView):
    required_roles = CADASTROS
    model = PromocaoProduto
    form_class = PromocaoProdutoForm
    template_name = "promocoes/promocao_form.html"
    success_url = reverse_lazy("promocoes:lista")

    def form_valid(self, form):
        form.instance.criado_por = self.request.user
        messages.success(self.request, "Promoção criada com sucesso.")
        return super().form_valid(form)


class PromocaoUpdateView(LoginRequiredMixin, RoleRequiredMixin, UpdateView):
    required_roles = CADASTROS
    model = PromocaoProduto
    form_class = PromocaoProdutoForm
    template_name = "promocoes/promocao_form.html"
    success_url = reverse_lazy("promocoes:lista")

    def form_valid(self, form):
        messages.success(self.request, "Promoção atualizada com sucesso.")
        return super().form_valid(form)
