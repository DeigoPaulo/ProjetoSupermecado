from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

from apps.accounts.permissions import CADASTROS, RoleRequiredMixin, role_required, supervisor_from_request
from apps.estoque.models import Estoque, MovimentacaoEstoque, TipoMovimentacaoEstoque
from apps.promocoes.services import preco_atual_produto

from .forms import CategoriaForm, EtiquetaProdutoForm, MarcaForm, ProdutoForm, ProdutoImportCSVForm, ReajustePrecoForm
from .models import Categoria, Marca, Produto
from .services import aplicar_reajuste_precos, importar_produtos_csv, simular_reajuste_precos


class ProdutoListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    required_roles = CADASTROS
    model = Produto
    template_name = "produtos/produto_list.html"
    context_object_name = "produtos"
    paginate_by = 25

    def get_queryset(self):
        queryset = Produto.all_objects.select_related("categoria", "marca").order_by("nome")
        termo = self.request.GET.get("q")
        if termo:
            queryset = queryset.filter(Q(nome__icontains=termo) | Q(codigo_barras__icontains=termo))
        return queryset


class ProdutoCreateView(LoginRequiredMixin, RoleRequiredMixin, CreateView):
    required_roles = CADASTROS
    model = Produto
    form_class = ProdutoForm
    template_name = "produtos/produto_form.html"
    success_url = reverse_lazy("produtos:lista")

    def form_valid(self, form):
        messages.success(self.request, "Produto cadastrado com sucesso.")
        return super().form_valid(form)


class ProdutoUpdateView(LoginRequiredMixin, RoleRequiredMixin, UpdateView):
    required_roles = CADASTROS
    model = Produto
    form_class = ProdutoForm
    template_name = "produtos/produto_form.html"
    success_url = reverse_lazy("produtos:lista")

    def get_queryset(self):
        return Produto.all_objects.all()

    def form_valid(self, form):
        messages.success(self.request, "Produto atualizado com sucesso.")
        return super().form_valid(form)


class CategoriaCreateView(LoginRequiredMixin, RoleRequiredMixin, CreateView):
    required_roles = CADASTROS
    model = Categoria
    form_class = CategoriaForm
    template_name = "produtos/categoria_form.html"
    success_url = reverse_lazy("produtos:lista")

    def form_valid(self, form):
        messages.success(self.request, "Categoria cadastrada com sucesso.")
        return super().form_valid(form)


class MarcaCreateView(LoginRequiredMixin, RoleRequiredMixin, CreateView):
    required_roles = CADASTROS
    model = Marca
    form_class = MarcaForm
    template_name = "produtos/marca_form.html"
    success_url = reverse_lazy("produtos:lista")

    def form_valid(self, form):
        messages.success(self.request, "Marca cadastrada com sucesso.")
        return super().form_valid(form)


@login_required
@role_required(*CADASTROS)
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
@role_required(*CADASTROS)
def reajustar_precos(request):
    preview = []
    total_afetado = 0
    form = ReajustePrecoForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        dados = form.cleaned_data
        if request.POST.get("confirmar") == "1":
            try:
                supervisor = supervisor_from_request(request)
                total = aplicar_reajuste_precos(
                    usuario=request.user,
                    categoria=dados["categoria"],
                    marca=dados["marca"],
                    percentual=dados["percentual"],
                    motivo=dados["motivo"],
                    aplicar_em_promocional=dados["aplicar_em_promocional"],
                    supervisor=supervisor,
                    ip=request.META.get("REMOTE_ADDR"),
                )
            except ValidationError as exc:
                messages.error(request, " ".join(exc.messages))
            else:
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
@role_required(*CADASTROS)
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
            queryset = queryset.filter(Q(nome__icontains=dados["busca"]) | Q(codigo_barras__icontains=dados["busca"]))
        if dados["categoria"]:
            queryset = queryset.filter(categoria=dados["categoria"])
        if dados["marca"]:
            queryset = queryset.filter(marca=dados["marca"])
        produtos = list(queryset[:200])
        for produto in produtos:
            produto.preco_etiqueta = preco_atual_produto(produto)
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


@login_required
@role_required(*CADASTROS)
def kardex(request, pk):
    produto = get_object_or_404(Produto.all_objects.select_related("categoria", "marca"), pk=pk)
    movimentacoes = MovimentacaoEstoque.objects.filter(produto=produto).select_related("filial", "usuario").order_by("-data")
    estoques = Estoque.objects.filter(produto=produto).select_related("filial").order_by("filial__nome")
    entradas = movimentacoes.filter(tipo__in=[TipoMovimentacaoEstoque.ENTRADA, TipoMovimentacaoEstoque.DEVOLUCAO, TipoMovimentacaoEstoque.AJUSTE]).aggregate(total=Sum("quantidade"))["total"] or 0
    saidas = movimentacoes.filter(tipo__in=[TipoMovimentacaoEstoque.SAIDA, TipoMovimentacaoEstoque.VENDA, TipoMovimentacaoEstoque.PERDA]).aggregate(total=Sum("quantidade"))["total"] or 0

    return render(
        request,
        "produtos/kardex.html",
        {
            "produto": produto,
            "movimentacoes": movimentacoes[:200],
            "estoques": estoques,
            "entradas": entradas,
            "saidas": saidas,
            "saldo_total": estoques.aggregate(total=Sum("quantidade_atual"))["total"] or 0,
            "reservado_total": estoques.aggregate(total=Sum("quantidade_reservada"))["total"] or 0,
        },
    )

# Create your views here.
