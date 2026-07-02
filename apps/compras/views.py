from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views.generic import DetailView, ListView
from django.views.generic.base import TemplateResponseMixin
from django.views.generic.edit import ModelFormMixin, ProcessFormView

from apps.accounts.permissions import COMPRAS, RoleRequiredMixin, role_required, supervisor_from_request

from .forms import EntradaCompraForm, ItemEntradaCompraFormSet
from .models import EntradaCompra, StatusEntradaCompra
from .services import finalizar_entrada_compra


class EntradaCompraListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    required_roles = COMPRAS
    model = EntradaCompra
    template_name = "compras/entrada_list.html"
    context_object_name = "entradas"
    paginate_by = 25

    def get_queryset(self):
        queryset = EntradaCompra.objects.select_related("fornecedor", "filial", "usuario").order_by("-data_recebimento")
        termo = self.request.GET.get("q")
        if termo:
            queryset = queryset.filter(numero_documento__icontains=termo) | queryset.filter(fornecedor__razao_social__icontains=termo) | queryset.filter(fornecedor__nome_fantasia__icontains=termo)
        return queryset


class EntradaCompraDetailView(LoginRequiredMixin, RoleRequiredMixin, DetailView):
    required_roles = COMPRAS
    model = EntradaCompra
    template_name = "compras/entrada_detalhe.html"
    context_object_name = "entrada"

    def get_queryset(self):
        return EntradaCompra.objects.select_related("fornecedor", "filial", "usuario").prefetch_related("itens__produto")


class EntradaCompraFormMixin(LoginRequiredMixin, RoleRequiredMixin, TemplateResponseMixin, ModelFormMixin, ProcessFormView):
    required_roles = COMPRAS
    model = EntradaCompra
    form_class = EntradaCompraForm
    template_name = "compras/entrada_form.html"

    def get(self, request, *args, **kwargs):
        self.object = self.get_object() if self.kwargs.get("pk") else None
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self.object = self.get_object() if self.kwargs.get("pk") else None
        return super().post(request, *args, **kwargs)

    def get_success_url(self):
        return reverse("compras:detalhe", args=[self.object.pk])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.method == "POST":
            context["formset"] = ItemEntradaCompraFormSet(self.request.POST, instance=self.object)
        else:
            context["formset"] = ItemEntradaCompraFormSet(instance=self.object)
        return context

    def form_valid(self, form):
        context = self.get_context_data(form=form)
        formset = context["formset"]
        if not formset.is_valid():
            return self.form_invalid(form)

        with transaction.atomic():
            self.object = form.save(commit=False)
            if not self.object.pk:
                self.object.usuario = self.request.user
            self.object.save()
            formset.instance = self.object
            itens = formset.save(commit=False)
            for item in itens:
                item.total = item.quantidade * item.custo_unitario
                item.save()
            for deleted in formset.deleted_objects:
                deleted.delete()
            formset.save_m2m()

        messages.success(self.request, "Entrada de compra salva com sucesso.")
        return redirect(self.get_success_url())


class EntradaCompraCreateView(EntradaCompraFormMixin):
    pass


class EntradaCompraUpdateView(EntradaCompraFormMixin):
    def get_queryset(self):
        return EntradaCompra.objects.filter(status=StatusEntradaCompra.RASCUNHO)


@login_required
@role_required(*COMPRAS)
def finalizar_entrada(request, pk):
    entrada = get_object_or_404(EntradaCompra.objects.prefetch_related("itens__produto"), pk=pk)
    if request.method != "POST":
        return redirect("compras:detalhe", pk=entrada.pk)

    try:
        supervisor = supervisor_from_request(request)
        finalizar_entrada_compra(entrada, supervisor=supervisor, ip=request.META.get("REMOTE_ADDR"))
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(request, "Entrada finalizada e estoque atualizado.")

    return redirect("compras:detalhe", pk=entrada.pk)

# Create your views here.
