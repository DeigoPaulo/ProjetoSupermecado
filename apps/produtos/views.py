from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

from .forms import CategoriaForm, EtiquetaProdutoForm, MarcaForm, ProdutoForm, ProdutoImportCSVForm, ReajustePrecoForm
from .models import Categoria, Marca, Produto
from .services import aplicar_reajuste_precos, importar_produtos_csv, simular_reajuste_precos


class ProdutoListView(LoginRequiredMixin, ListView):
    model = Produto
    template_name = "produtos/produto_list.html"
    context_object_name = "produtos"
    paginate_by = 25

    def get_queryset(self):
        queryset = Produto.all_objects.select_related("categoria", "marca").order_by("nome")
        termo = self.request.GET.get("q")
        if termo:
            queryset = queryset.filter(nome__icontains=termo) | queryset.filter(codigo_barras__icontains=termo)
        return queryset


class ProdutoCreateView(LoginRequiredMixin, CreateView):
    model = Produto
    form_class = ProdutoForm
    template_name = "produtos/produto_form.html"
    success_url = reverse_lazy("produtos:lista")

    def form_valid(self, form):
        messages.success(self.request, "Produto cadastrado com sucesso.")
        return super().form_valid(form)


class ProdutoUpdateView(LoginRequiredMixin, UpdateView):
    model = Produto
    form_class = ProdutoForm
    template_name = "produtos/produto_form.html"
    success_url = reverse_lazy("produtos:lista")

    def get_queryset(self):
        return Produto.all_objects.all()

    def form_valid(self, form):
        messages.success(self.request, "Produto atualizado com sucesso.")
        return super().form_valid(form)


class CategoriaCreateView(LoginRequiredMixin, CreateView):
    model = Categoria
    form_class = CategoriaForm
    template_name = "produtos/categoria_form.html"
    success_url = reverse_lazy("produtos:lista")

    def form_valid(self, form):
        messages.success(self.request, "Categoria cadastrada com sucesso.")
        return super().form_valid(form)


class MarcaCreateView(LoginRequiredMixin, CreateView):
    model = Marca
    form_class = MarcaForm
    template_name = "produtos/marca_form.html"
    success_url = reverse_lazy("produtos:lista")

    def form_valid(self, form):
        messages.success(self.request, "Marca cadastrada com sucesso.")
        return super().form_valid(form)


@login_required
def importar_csv(request):
    resultado = None
    if request.method == "POST":
        form = ProdutoImportCSVForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                resultado = importar_produtos_csv(
                    form.cleaned_data["arquivo"],
                    atualizar_existentes=form.cleaned_data["atualizar_existentes"],
                )
            except ValueError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(
                    request,
                    f"Importacao concluida: {resultado['criados']} criados, {resultado['atualizados']} atualizados, {resultado['ignorados']} ignorados.",
                )
                if not resultado["erros"]:
                    return redirect("produtos:lista")
    else:
        form = ProdutoImportCSVForm()

    return render(request, "produtos/importar_csv.html", {"form": form, "resultado": resultado})


@login_required
def reajustar_precos(request):
    preview = []
    total_afetado = 0
    form = ReajustePrecoForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        dados = form.cleaned_data
        if request.POST.get("confirmar") == "1":
            total = aplicar_reajuste_precos(
                usuario=request.user,
                categoria=dados["categoria"],
                marca=dados["marca"],
                percentual=dados["percentual"],
                motivo=dados["motivo"],
                aplicar_em_promocional=dados["aplicar_em_promocional"],
                ip=request.META.get("REMOTE_ADDR"),
            )
            messages.success(request, f"Reajuste aplicado em {total} produto(s).")
            return redirect("produtos:lista")

        preview, total_afetado = simular_reajuste_precos(
            categoria=dados["categoria"],
            marca=dados["marca"],
            percentual=dados["percentual"],
            aplicar_em_promocional=dados["aplicar_em_promocional"],
        )

    return render(
        request,
        "produtos/reajuste_precos.html",
        {
            "form": form,
            "preview": preview,
            "total_afetado": total_afetado,
        },
    )


@login_required
def etiquetas(request):
    form = EtiquetaProdutoForm(request.GET or None)
    produtos = []
    etiquetas_lista = []
    if form.is_valid() and request.GET:
        dados = form.cleaned_data
        queryset = Produto.all_objects.select_related("categoria", "marca").order_by("nome")
        if not dados["incluir_inativos"]:
            queryset = queryset.filter(is_active=True)
        if dados["busca"]:
            queryset = queryset.filter(nome__icontains=dados["busca"]) | queryset.filter(codigo_barras__icontains=dados["busca"])
        if dados["categoria"]:
            queryset = queryset.filter(categoria=dados["categoria"])
        if dados["marca"]:
            queryset = queryset.filter(marca=dados["marca"])
        produtos = list(queryset[:200])
        for produto in produtos:
            for _ in range(dados["quantidade_copias"]):
                etiquetas_lista.append(produto)

    return render(
        request,
        "produtos/etiquetas.html",
        {
            "form": form,
            "produtos": produtos,
            "etiquetas": etiquetas_lista,
        },
    )

# Create your views here.
