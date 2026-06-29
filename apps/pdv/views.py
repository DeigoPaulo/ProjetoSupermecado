from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, ListView

from apps.produtos.models import Produto
from apps.vendas.models import Venda
from apps.vendas.services import calcular_item, cancelar_venda, finalizar_venda

from .forms import AbrirCaixaForm, AdicionarItemForm, FecharCaixaForm, FinalizarVendaForm, SangriaForm, SuprimentoForm
from .models import Caixa, Sangria, StatusCaixa, Suprimento


CART_SESSION_KEY = "pdv_cart"


def _get_cart(request):
    return request.session.get(CART_SESSION_KEY, {})


def _save_cart(request, cart):
    request.session[CART_SESSION_KEY] = cart
    request.session.modified = True


def _cart_items(cart):
    produtos = Produto.objects.filter(id__in=cart.keys()).select_related("categoria", "marca")
    produtos_map = {str(produto.id): produto for produto in produtos}
    items = []
    total = Decimal("0.00")
    for produto_id, quantidade_texto in cart.items():
        produto = produtos_map.get(str(produto_id))
        if not produto:
            continue
        quantidade = Decimal(quantidade_texto)
        subtotal = calcular_item(produto, quantidade)
        total += subtotal
        items.append({"produto": produto, "quantidade": quantidade, "subtotal": subtotal})
    return items, total


@login_required
def pdv(request):
    cart = _get_cart(request)

    if request.method == "POST" and request.POST.get("action") == "add":
        add_form = AdicionarItemForm(request.POST)
        finish_form = FinalizarVendaForm()
        if add_form.is_valid():
            busca = add_form.cleaned_data["busca"].strip()
            quantidade = add_form.cleaned_data["quantidade"]
            produto = Produto.objects.filter(Q(codigo_barras=busca) | Q(nome__icontains=busca)).first()
            if produto:
                produto_id = str(produto.id)
                atual = Decimal(cart.get(produto_id, "0"))
                cart[produto_id] = str(atual + quantidade)
                _save_cart(request, cart)
                messages.success(request, "Item incluido no carrinho.")
                return redirect("pdv:pdv")
            messages.error(request, "Produto nao encontrado.")
    elif request.method == "POST" and request.POST.get("action") == "finish":
        add_form = AdicionarItemForm()
        finish_form = FinalizarVendaForm(request.POST)
        if finish_form.is_valid():
            items, _ = _cart_items(cart)
            try:
                venda = finalizar_venda(usuario=request.user, itens=items, **finish_form.cleaned_data)
            except ValidationError as exc:
                messages.error(request, " ".join(exc.messages))
            else:
                _save_cart(request, {})
                messages.success(request, f"Venda {venda.id} finalizada com sucesso.")
                return redirect("pdv:venda_detalhe", venda_id=venda.id)
    else:
        add_form = AdicionarItemForm()
        finish_form = FinalizarVendaForm()

    items, total = _cart_items(cart)
    return render(
        request,
        "pdv/pdv.html",
        {
            "add_form": add_form,
            "finish_form": finish_form,
            "items": items,
            "total": total,
        },
    )


@login_required
def remover_item(request, produto_id):
    cart = _get_cart(request)
    cart.pop(str(produto_id), None)
    _save_cart(request, cart)
    messages.success(request, "Item removido.")
    return redirect("pdv:pdv")


@login_required
def limpar_carrinho(request):
    _save_cart(request, {})
    messages.success(request, "Carrinho limpo.")
    return redirect("pdv:pdv")


@login_required
def venda_detalhe(request, venda_id):
    venda = get_object_or_404(
        Venda.objects.select_related("filial", "caixa", "usuario").prefetch_related("itens__produto", "pagamentos__forma_pagamento"),
        id=venda_id,
    )
    return render(request, "pdv/venda_detalhe.html", {"venda": venda})


@login_required
def recibo_venda(request, venda_id):
    venda = get_object_or_404(
        Venda.objects.select_related("filial", "filial__empresa", "caixa", "usuario", "cliente").prefetch_related("itens__produto", "pagamentos__forma_pagamento"),
        id=venda_id,
    )
    return render(request, "pdv/recibo_venda.html", {"venda": venda})


@login_required
def cancelar_venda_view(request, venda_id):
    venda = get_object_or_404(Venda, id=venda_id)
    if request.method != "POST":
        return redirect("pdv:venda_detalhe", venda_id=venda.id)
    motivo = request.POST.get("motivo", "").strip()
    try:
        cancelar_venda(venda=venda, usuario=request.user, motivo=motivo, ip=request.META.get("REMOTE_ADDR"))
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(request, "Venda cancelada e estoque devolvido.")
    return redirect("pdv:venda_detalhe", venda_id=venda.id)


def _resumo_caixa(caixa):
    total_vendas = caixa.vendas.filter(status="FINALIZADA").aggregate(total=Sum("total_liquido"))["total"] or Decimal("0.00")
    total_sangrias = caixa.sangrias.aggregate(total=Sum("valor"))["total"] or Decimal("0.00")
    total_suprimentos = caixa.suprimentos.aggregate(total=Sum("valor"))["total"] or Decimal("0.00")
    total_esperado = caixa.valor_inicial + total_vendas + total_suprimentos - total_sangrias
    return {
        "total_vendas": total_vendas,
        "total_sangrias": total_sangrias,
        "total_suprimentos": total_suprimentos,
        "total_esperado": total_esperado,
    }


@login_required
def caixa_detalhe(request, caixa_id):
    caixa = get_object_or_404(
        Caixa.objects.select_related("filial", "usuario_abertura", "usuario_fechamento").prefetch_related("vendas", "sangrias", "suprimentos"),
        id=caixa_id,
    )
    context = {
        "caixa": caixa,
        "resumo": _resumo_caixa(caixa),
        "sangria_form": SangriaForm(),
        "suprimento_form": SuprimentoForm(),
        "fechar_form": FecharCaixaForm(instance=caixa),
        "has_movimentos": caixa.suprimentos.exists() or caixa.sangrias.exists(),
    }
    return render(request, "pdv/caixa_detalhe.html", context)


def _caixa_aberto_or_redirect(request, caixa_id):
    caixa = get_object_or_404(Caixa, id=caixa_id)
    if caixa.status != StatusCaixa.ABERTO:
        messages.error(request, "Este caixa nao esta aberto.")
        return caixa, False
    return caixa, True


@login_required
def registrar_sangria(request, caixa_id):
    caixa, ok = _caixa_aberto_or_redirect(request, caixa_id)
    if not ok:
        return redirect("pdv:caixa_detalhe", caixa_id=caixa.id)
    if request.method == "POST":
        form = SangriaForm(request.POST)
        if form.is_valid():
            sangria = form.save(commit=False)
            sangria.caixa = caixa
            sangria.usuario = request.user
            sangria.save()
            messages.success(request, "Sangria registrada com sucesso.")
    return redirect("pdv:caixa_detalhe", caixa_id=caixa.id)


@login_required
def registrar_suprimento(request, caixa_id):
    caixa, ok = _caixa_aberto_or_redirect(request, caixa_id)
    if not ok:
        return redirect("pdv:caixa_detalhe", caixa_id=caixa.id)
    if request.method == "POST":
        form = SuprimentoForm(request.POST)
        if form.is_valid():
            suprimento = form.save(commit=False)
            suprimento.caixa = caixa
            suprimento.usuario = request.user
            suprimento.save()
            messages.success(request, "Suprimento registrado com sucesso.")
    return redirect("pdv:caixa_detalhe", caixa_id=caixa.id)


@login_required
def fechar_caixa(request, caixa_id):
    caixa, ok = _caixa_aberto_or_redirect(request, caixa_id)
    if not ok:
        return redirect("pdv:caixa_detalhe", caixa_id=caixa.id)
    if request.method == "POST":
        form = FecharCaixaForm(request.POST, instance=caixa)
        if form.is_valid():
            caixa = form.save(commit=False)
            caixa.usuario_fechamento = request.user
            caixa.data_fechamento = timezone.now()
            caixa.status = StatusCaixa.FECHADO
            caixa.save()
            messages.success(request, "Caixa fechado com sucesso.")
    return redirect("pdv:caixa_detalhe", caixa_id=caixa.id)


class CaixaListView(LoginRequiredMixin, ListView):
    model = Caixa
    template_name = "pdv/caixa_list.html"
    context_object_name = "caixas"
    paginate_by = 25

    def get_queryset(self):
        return Caixa.objects.select_related("filial", "usuario_abertura", "usuario_fechamento").order_by("-data_abertura")


class AbrirCaixaView(LoginRequiredMixin, CreateView):
    model = Caixa
    form_class = AbrirCaixaForm
    template_name = "pdv/caixa_form.html"
    success_url = reverse_lazy("pdv:caixas")

    def form_valid(self, form):
        form.instance.usuario_abertura = self.request.user
        messages.success(self.request, "Caixa aberto com sucesso.")
        return super().form_valid(form)

# Create your views here.
