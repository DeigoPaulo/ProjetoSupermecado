from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView

from .forms import InventarioEstoqueForm, ItemInventarioEstoqueForm, MovimentacaoEstoqueForm, PerdaEstoqueForm
from .models import Estoque, InventarioEstoque, PerdaEstoque, StatusInventario, movimentar_estoque
from .services import aplicar_inventario, registrar_perda_estoque


class EstoqueListView(LoginRequiredMixin, ListView):
    model = Estoque
    template_name = "estoque/estoque_list.html"
    context_object_name = "estoques"
    paginate_by = 30

    def get_queryset(self):
        queryset = Estoque.objects.select_related("produto", "filial", "filial__empresa").order_by("produto__nome")
        termo = self.request.GET.get("q")
        if termo:
            queryset = queryset.filter(produto__nome__icontains=termo) | queryset.filter(produto__codigo_barras__icontains=termo)
        return queryset


@login_required
def movimentar(request):
    if request.method == "POST":
        form = MovimentacaoEstoqueForm(request.POST)
        if form.is_valid():
            movimentar_estoque(usuario=request.user, **form.cleaned_data)
            messages.success(request, "Movimentacao registrada com sucesso.")
            return redirect("estoque:lista")
    else:
        form = MovimentacaoEstoqueForm()

    return render(request, "estoque/movimentacao_form.html", {"form": form})


class InventarioListView(LoginRequiredMixin, ListView):
    model = InventarioEstoque
    template_name = "estoque/inventario_list.html"
    context_object_name = "inventarios"
    paginate_by = 25

    def get_queryset(self):
        return InventarioEstoque.objects.select_related("filial", "usuario").order_by("-criado_em")


class CriarInventarioView(LoginRequiredMixin, CreateView):
    model = InventarioEstoque
    form_class = InventarioEstoqueForm
    template_name = "estoque/inventario_form.html"

    def form_valid(self, form):
        form.instance.usuario = self.request.user
        messages.success(self.request, "Inventario criado com sucesso.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy("estoque:inventario_detalhe", args=[self.object.pk])


@login_required
def inventario_detalhe(request, pk):
    inventario = get_object_or_404(
        InventarioEstoque.objects.select_related("filial", "usuario").prefetch_related("itens__produto"),
        pk=pk,
    )
    return render(request, "estoque/inventario_detalhe.html", {"inventario": inventario})


@login_required
def adicionar_item_inventario(request, pk):
    inventario = get_object_or_404(InventarioEstoque, pk=pk)
    if inventario.status != StatusInventario.ABERTO:
        messages.error(request, "Nao e possivel editar inventario aplicado ou cancelado.")
        return redirect("estoque:inventario_detalhe", pk=inventario.pk)

    if request.method == "POST":
        form = ItemInventarioEstoqueForm(request.POST)
        if form.is_valid():
            item = form.save(commit=False)
            item.inventario = inventario
            estoque = Estoque.objects.filter(produto=item.produto, filial=inventario.filial).first()
            item.quantidade_sistema = estoque.quantidade_atual if estoque else 0
            item.diferenca = item.quantidade_contada - item.quantidade_sistema
            item.save()
            messages.success(request, "Item contado adicionado.")
            return redirect("estoque:inventario_detalhe", pk=inventario.pk)
    else:
        form = ItemInventarioEstoqueForm()

    return render(request, "estoque/inventario_item_form.html", {"form": form, "inventario": inventario})


@login_required
def aplicar_inventario_view(request, pk):
    inventario = get_object_or_404(InventarioEstoque, pk=pk)
    if request.method != "POST":
        return redirect("estoque:inventario_detalhe", pk=inventario.pk)
    try:
        aplicar_inventario(inventario=inventario, usuario=request.user, ip=request.META.get("REMOTE_ADDR"))
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(request, "Inventario aplicado e estoque ajustado.")
    return redirect("estoque:inventario_detalhe", pk=inventario.pk)


class PerdaEstoqueListView(LoginRequiredMixin, ListView):
    model = PerdaEstoque
    template_name = "estoque/perda_list.html"
    context_object_name = "perdas"
    paginate_by = 30

    def get_queryset(self):
        return PerdaEstoque.objects.select_related("produto", "filial", "usuario").order_by("-data")


@login_required
def registrar_perda(request):
    if request.method == "POST":
        form = PerdaEstoqueForm(request.POST)
        if form.is_valid():
            try:
                registrar_perda_estoque(usuario=request.user, ip=request.META.get("REMOTE_ADDR"), **form.cleaned_data)
            except ValidationError as exc:
                messages.error(request, " ".join(exc.messages))
            else:
                messages.success(request, "Perda registrada e estoque baixado.")
                return redirect("estoque:perdas")
    else:
        form = PerdaEstoqueForm()
    return render(request, "estoque/perda_form.html", {"form": form})

# Create your views here.
