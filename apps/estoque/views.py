import csv
from decimal import Decimal, ROUND_DOWN

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db.models import Count, F, Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_GET
from django.views.generic import CreateView, ListView, UpdateView

from apps.accounts.permissions import ESTOQUE, RoleRequiredMixin, role_required, supervisor_from_request
from apps.auditoria.models import LogAuditoria
from apps.produtos.models import Produto

from .forms import (
    ComposicaoProdutoForm,
    DesmembramentoDestinoFormSet,
    DesmembramentoProdutoForm,
    InventarioEstoqueForm,
    ItemComposicaoProdutoFormSet,
    ItemInventarioEstoqueForm,
    MovimentacaoEstoqueForm,
    PerdaEstoqueForm,
    ProducaoComposicaoForm,
    ReceitaDesmembramentoForm,
)
from .models import (
    ComposicaoProduto,
    DesmembramentoProduto,
    Estoque,
    InventarioEstoque,
    ItemDesmembramentoProduto,
    PerdaEstoque,
    ProducaoComposicaoProduto,
    ReceitaDesmembramento,
    StatusInventario,
    StatusProducaoComposicao,
    TipoDesmembramentoProduto,
    TipoSaidaDesmembramento,
    movimentar_estoque,
)
from .services import (
    aplicar_inventario,
    cancelar_producao_composicao,
    cancelar_desmembramento_produto,
    confirmar_desmembramento_multidestino,
    confirmar_desmembramento_simples,
    confirmar_producao_composicao,
    registrar_perda_estoque,
    simular_desmembramento_multidestino,
    simular_desmembramento_simples,
)


def _decimal_zero():
    return Decimal("0.000")


def _resumo_visual_composicao(composicao):
    componentes = []
    custo_previsto = Decimal("0.00")
    capacidade_maxima = None
    estoque_final_qs = Estoque.objects.filter(produto=composicao.produto_final)
    if composicao.filial_id:
        estoque_final_qs = estoque_final_qs.filter(filial=composicao.filial)
    else:
        estoque_final_qs = estoque_final_qs.filter(filial__empresa=composicao.empresa)
    estoque_final = estoque_final_qs.aggregate(total=Sum("quantidade_atual"))["total"] or _decimal_zero()

    for item in composicao.itens.all():
        estoque_qs = Estoque.objects.filter(produto=item.produto_componente)
        if composicao.filial_id:
            estoque_qs = estoque_qs.filter(filial=composicao.filial)
        else:
            estoque_qs = estoque_qs.filter(filial__empresa=composicao.empresa)
        saldo = estoque_qs.aggregate(total=Sum("quantidade_atual"))["total"] or _decimal_zero()
        custo_item = item.quantidade * item.produto_componente.preco_custo
        custo_previsto += custo_item
        capacidade_item = _decimal_zero()
        if item.quantidade > 0:
            capacidade_item = ((saldo / item.quantidade) * composicao.quantidade_final).quantize(Decimal("0.001"), rounding=ROUND_DOWN)
            capacidade_maxima = capacidade_item if capacidade_maxima is None else min(capacidade_maxima, capacidade_item)
        componentes.append(
            {
                "item": item,
                "saldo": saldo,
                "custo_total": custo_item,
                "capacidade": capacidade_item,
                "suficiente": saldo >= item.quantidade,
            }
        )

    return {
        "componentes": componentes,
        "custo_previsto": custo_previsto,
        "estoque_final": estoque_final,
        "capacidade_maxima": capacidade_maxima if capacidade_maxima is not None else _decimal_zero(),
    }


class EstoqueListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    required_roles = ESTOQUE
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
@role_required(*ESTOQUE)
def movimentar(request):
    if request.method == "POST":
        form = MovimentacaoEstoqueForm(request.POST)
        if form.is_valid():
            try:
                supervisor = supervisor_from_request(request)
                movimentacao = movimentar_estoque(usuario=request.user, **form.cleaned_data)
                LogAuditoria.objects.create(
                    usuario=request.user,
                    modulo="estoque",
                    acao="MOVIMENTACAO_MANUAL",
                    descricao=(
                        f"Movimentacao {movimentacao.id}: {movimentacao.tipo} {movimentacao.quantidade} "
                        f"do produto {movimentacao.produto}. Motivo: {movimentacao.motivo or '-'}. "
                        f"Autorizado por: {supervisor}."
                    ),
                    objeto_tipo="MovimentacaoEstoque",
                    objeto_id=str(movimentacao.id),
                    ip=request.META.get("REMOTE_ADDR"),
                )
            except ValidationError as exc:
                messages.error(request, " ".join(exc.messages))
            else:
                messages.success(request, "Movimentacao registrada com sucesso.")
                return redirect("estoque:lista")
    else:
        form = MovimentacaoEstoqueForm()

    return render(request, "estoque/movimentacao_form.html", {"form": form})


class InventarioListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    required_roles = ESTOQUE
    model = InventarioEstoque
    template_name = "estoque/inventario_list.html"
    context_object_name = "inventarios"
    paginate_by = 25

    def get_queryset(self):
        return InventarioEstoque.objects.select_related("filial", "usuario").order_by("-criado_em")


class CriarInventarioView(LoginRequiredMixin, RoleRequiredMixin, CreateView):
    required_roles = ESTOQUE
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
@role_required(*ESTOQUE)
def inventario_detalhe(request, pk):
    inventario = get_object_or_404(
        InventarioEstoque.objects.select_related("filial", "usuario").prefetch_related("itens__produto"),
        pk=pk,
    )
    return render(request, "estoque/inventario_detalhe.html", {"inventario": inventario})


@login_required
@role_required(*ESTOQUE)
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
@role_required(*ESTOQUE)
def aplicar_inventario_view(request, pk):
    inventario = get_object_or_404(InventarioEstoque, pk=pk)
    if request.method != "POST":
        return redirect("estoque:inventario_detalhe", pk=inventario.pk)
    try:
        supervisor = supervisor_from_request(request)
        aplicar_inventario(inventario=inventario, usuario=request.user, supervisor=supervisor, ip=request.META.get("REMOTE_ADDR"))
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(request, "Inventario aplicado e estoque ajustado.")
    return redirect("estoque:inventario_detalhe", pk=inventario.pk)


class PerdaEstoqueListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    required_roles = ESTOQUE
    model = PerdaEstoque
    template_name = "estoque/perda_list.html"
    context_object_name = "perdas"
    paginate_by = 30

    def get_queryset(self):
        return PerdaEstoque.objects.select_related("produto", "filial", "usuario").order_by("-data")


@login_required
@role_required(*ESTOQUE)
def registrar_perda(request):
    if request.method == "POST":
        form = PerdaEstoqueForm(request.POST)
        if form.is_valid():
            try:
                supervisor = supervisor_from_request(request)
                registrar_perda_estoque(usuario=request.user, supervisor=supervisor, ip=request.META.get("REMOTE_ADDR"), **form.cleaned_data)
            except ValidationError as exc:
                messages.error(request, " ".join(exc.messages))
            else:
                messages.success(request, "Perda registrada e estoque baixado.")
                return redirect("estoque:perdas")
    else:
        form = PerdaEstoqueForm()
    return render(request, "estoque/perda_form.html", {"form": form})


class DesmembramentoProdutoListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    required_roles = ESTOQUE
    model = DesmembramentoProduto
    template_name = "estoque/desmembramento_list.html"
    context_object_name = "desmembramentos"
    paginate_by = 30

    def get_queryset(self):
        return _desmembramentos_filtrados(self.request)


def _desmembramentos_filtrados(request):
    queryset = DesmembramentoProduto.objects.select_related(
        "filial", "empresa", "produto_origem", "usuario"
    ).prefetch_related("itens__produto_destino")
    termo = (request.GET.get("q") or "").strip()
    if termo:
        queryset = queryset.filter(
            Q(produto_origem__nome__icontains=termo)
            | Q(produto_origem__codigo_barras__icontains=termo)
            | Q(produto_origem__codigo_interno__icontains=termo)
            | Q(itens__produto_destino__nome__icontains=termo)
            | Q(itens__produto_destino__codigo_barras__icontains=termo)
            | Q(itens__produto_destino__codigo_interno__icontains=termo)
        ).distinct()
    return queryset.order_by("-criado_em")


class ReceitaDesmembramentoListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    required_roles = ESTOQUE
    model = ReceitaDesmembramento
    template_name = "estoque/receita_desmembramento_list.html"
    context_object_name = "receitas"
    paginate_by = 30

    def get_queryset(self):
        queryset = ReceitaDesmembramento.objects.select_related(
            "empresa", "filial", "produto_origem", "produto_destino"
        )
        termo = (self.request.GET.get("q") or "").strip()
        if termo:
            queryset = queryset.filter(
                Q(produto_origem__nome__icontains=termo)
                | Q(produto_origem__codigo_barras__icontains=termo)
                | Q(produto_origem__codigo_interno__icontains=termo)
                | Q(produto_destino__nome__icontains=termo)
                | Q(produto_destino__codigo_barras__icontains=termo)
                | Q(produto_destino__codigo_interno__icontains=termo)
            )
        return queryset.order_by("produto_origem__nome", "produto_destino__nome")


class ReceitaDesmembramentoCreateView(LoginRequiredMixin, RoleRequiredMixin, CreateView):
    required_roles = ESTOQUE
    model = ReceitaDesmembramento
    form_class = ReceitaDesmembramentoForm
    template_name = "estoque/receita_desmembramento_form.html"
    success_url = reverse_lazy("estoque:receitas_desmembramento")

    def form_valid(self, form):
        messages.success(self.request, "Receita de desmembramento cadastrada.")
        return super().form_valid(form)


class ReceitaDesmembramentoUpdateView(LoginRequiredMixin, RoleRequiredMixin, UpdateView):
    required_roles = ESTOQUE
    model = ReceitaDesmembramento
    form_class = ReceitaDesmembramentoForm
    template_name = "estoque/receita_desmembramento_form.html"
    success_url = reverse_lazy("estoque:receitas_desmembramento")

    def form_valid(self, form):
        messages.success(self.request, "Receita de desmembramento atualizada.")
        return super().form_valid(form)


class ComposicaoProdutoListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    required_roles = ESTOQUE
    model = ComposicaoProduto
    template_name = "estoque/composicao_list.html"
    context_object_name = "composicoes"
    paginate_by = 30

    def get_queryset(self):
        queryset = ComposicaoProduto.objects.select_related("empresa", "filial", "produto_final").prefetch_related(
            "itens__produto_componente"
        )
        termo = (self.request.GET.get("q") or "").strip()
        if termo:
            queryset = queryset.filter(
                Q(produto_final__nome__icontains=termo)
                | Q(produto_final__codigo_barras__icontains=termo)
                | Q(produto_final__codigo_interno__icontains=termo)
                | Q(itens__produto_componente__nome__icontains=termo)
                | Q(itens__produto_componente__codigo_barras__icontains=termo)
                | Q(itens__produto_componente__codigo_interno__icontains=termo)
            ).distinct()
        return queryset.order_by("produto_final__nome")


def _salvar_composicao_com_itens(request, composicao=None):
    form = ComposicaoProdutoForm(request.POST or None, instance=composicao)
    formset = ItemComposicaoProdutoFormSet(request.POST or None, instance=composicao, prefix="componentes")
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        composicao = form.save()
        formset.instance = composicao
        formset.save()
        messages.success(request, "Composicao salva com sucesso.")
        return composicao, form, formset
    return None, form, formset


@login_required
@role_required(*ESTOQUE)
def composicao_nova(request):
    composicao, form, formset = _salvar_composicao_com_itens(request)
    if composicao:
        return redirect("estoque:composicao_detalhe", pk=composicao.pk)
    return render(request, "estoque/composicao_form.html", {"form": form, "formset": formset})


@login_required
@role_required(*ESTOQUE)
def composicao_editar(request, pk):
    objeto = get_object_or_404(ComposicaoProduto, pk=pk)
    composicao, form, formset = _salvar_composicao_com_itens(request, objeto)
    if composicao:
        return redirect("estoque:composicao_detalhe", pk=composicao.pk)
    return render(request, "estoque/composicao_form.html", {"form": form, "formset": formset, "object": objeto})


@login_required
@role_required(*ESTOQUE)
def composicao_detalhe(request, pk):
    composicao = get_object_or_404(
        ComposicaoProduto.objects.select_related("empresa", "filial", "produto_final").prefetch_related(
            "itens__produto_componente",
            "producoes__filial",
            "producoes__usuario",
        ),
        pk=pk,
    )
    producao_form = ProducaoComposicaoForm(composicao=composicao)
    producoes = composicao.producoes.select_related("filial", "usuario").order_by("-criado_em")[:20]
    resumo_visual = _resumo_visual_composicao(composicao)
    return render(
        request,
        "estoque/composicao_detalhe.html",
        {
            "composicao": composicao,
            "producao_form": producao_form,
            "producoes": producoes,
            "resumo_visual": resumo_visual,
        },
    )


@login_required
@role_required(*ESTOQUE)
def composicao_produzir(request, pk):
    composicao = get_object_or_404(ComposicaoProduto, pk=pk)
    if request.method != "POST":
        return redirect("estoque:composicao_detalhe", pk=composicao.pk)
    form = ProducaoComposicaoForm(request.POST, composicao=composicao)
    if form.is_valid():
        try:
            supervisor = supervisor_from_request(request)
            producao = confirmar_producao_composicao(
                composicao=composicao,
                usuario=request.user,
                supervisor=supervisor,
                ip=request.META.get("REMOTE_ADDR"),
                **form.cleaned_data,
            )
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        else:
            messages.success(request, f"Composicao {producao.id} produzida e estoque atualizado.")
    else:
        messages.error(request, "Confira os dados da producao.")
    return redirect("estoque:composicao_detalhe", pk=composicao.pk)


@login_required
@role_required(*ESTOQUE)
def composicao_cancelar_producao(request, pk):
    producao = get_object_or_404(ProducaoComposicaoProduto.objects.select_related("composicao"), pk=pk)
    if request.method != "POST":
        return redirect("estoque:composicao_detalhe", pk=producao.composicao_id)
    try:
        supervisor = supervisor_from_request(request)
        cancelar_producao_composicao(
            producao=producao,
            usuario=request.user,
            motivo=request.POST.get("motivo", "").strip(),
            supervisor=supervisor,
            ip=request.META.get("REMOTE_ADDR"),
        )
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(request, "Producao cancelada e estoque revertido.")
    return redirect("estoque:composicao_detalhe", pk=producao.composicao_id)


@login_required
@role_required(*ESTOQUE)
def desmembramentos_csv(request):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="desmembramentos_produtos.csv"'
    response.write("\ufeff")
    writer = csv.writer(response, delimiter=";")
    writer.writerow(
        [
            "ID",
            "Data",
            "Filial",
            "Status",
            "Produto origem",
            "Codigo origem",
            "Qtd origem",
            "Produto destino",
            "Codigo destino",
            "Qtd destino",
            "Tipo destino",
            "Lote",
            "Validade",
            "Rendimento esperado %",
            "Rendimento real %",
            "Alerta rendimento",
            "Unidade",
            "Custo unitario destino",
            "Custo total",
            "Usuario",
            "Motivo",
        ]
    )
    for desmembramento in _desmembramentos_filtrados(request):
        for item in desmembramento.itens.all():
            writer.writerow(
                [
                    desmembramento.id,
                    desmembramento.criado_em.strftime("%d/%m/%Y %H:%M"),
                    desmembramento.filial.nome,
                    desmembramento.get_status_display(),
                    desmembramento.produto_origem.nome,
                    desmembramento.produto_origem.codigo_barras,
                    desmembramento.quantidade_origem,
                    item.produto_destino.nome,
                    item.produto_destino.codigo_barras,
                    item.quantidade_gerada,
                    item.get_tipo_saida_display(),
                    item.lote,
                    item.validade.strftime("%d/%m/%Y") if item.validade else "",
                    item.percentual_rendimento_esperado or "",
                    item.percentual_rendimento,
                    "Abaixo do esperado" if item.rendimento_abaixo_esperado else "",
                    item.unidade,
                    item.custo_unitario_calculado,
                    item.custo_total,
                    desmembramento.usuario.username,
                    desmembramento.motivo,
                ]
            )
    return response


def _itens_desmembramento_relatorio(request):
    queryset = ItemDesmembramentoProduto.objects.select_related(
        "desmembramento",
        "desmembramento__filial",
        "desmembramento__empresa",
        "desmembramento__produto_origem",
        "desmembramento__usuario",
        "produto_destino",
    )
    termo = (request.GET.get("q") or "").strip()
    data_inicio = (request.GET.get("inicio") or "").strip()
    data_fim = (request.GET.get("fim") or "").strip()
    filial_id = (request.GET.get("filial") or "").strip()
    tipo = (request.GET.get("tipo") or "").strip()
    tipo_saida = (request.GET.get("tipo_saida") or "").strip()
    alerta = (request.GET.get("alerta") or "").strip()

    if termo:
        queryset = queryset.filter(
            Q(desmembramento__produto_origem__nome__icontains=termo)
            | Q(desmembramento__produto_origem__codigo_barras__icontains=termo)
            | Q(desmembramento__produto_origem__codigo_interno__icontains=termo)
            | Q(produto_destino__nome__icontains=termo)
            | Q(produto_destino__codigo_barras__icontains=termo)
            | Q(produto_destino__codigo_interno__icontains=termo)
            | Q(lote__icontains=termo)
        )
    if data_inicio:
        queryset = queryset.filter(desmembramento__criado_em__date__gte=data_inicio)
    if data_fim:
        queryset = queryset.filter(desmembramento__criado_em__date__lte=data_fim)
    if filial_id:
        queryset = queryset.filter(desmembramento__filial_id=filial_id)
    if tipo:
        queryset = queryset.filter(desmembramento__tipo=tipo)
    if tipo_saida:
        queryset = queryset.filter(tipo_saida=tipo_saida)
    if alerta == "abaixo":
        queryset = queryset.filter(percentual_rendimento_esperado__isnull=False).filter(
            percentual_rendimento__lt=F("percentual_rendimento_esperado")
        )
    return queryset.order_by("-desmembramento__criado_em", "id")


@login_required
@role_required(*ESTOQUE)
def desmembramento_relatorio(request):
    from apps.empresas.models import Filial

    itens = _itens_desmembramento_relatorio(request)
    totais = itens.aggregate(
        itens=Count("id"),
        quantidade_gerada=Sum("quantidade_gerada"),
        custo_total=Sum("custo_total"),
        operacoes=Count("desmembramento", distinct=True),
    )
    total_alertas = itens.filter(
        percentual_rendimento_esperado__isnull=False,
        percentual_rendimento__lt=F("percentual_rendimento_esperado"),
    ).count()
    destino_agrupado = list(
        itens.values("tipo_saida")
        .annotate(total=Count("id"), custo=Sum("custo_total"))
        .order_by("tipo_saida")
    )
    tipo_agrupado = list(
        itens.values("desmembramento__tipo")
        .annotate(total=Count("id"))
        .order_by("desmembramento__tipo")
    )
    tipo_saida_labels = dict(TipoSaidaDesmembramento.choices)
    tipo_labels = dict(TipoDesmembramentoProduto.choices)
    graficos = {
        "destinos": {
            "labels": [tipo_saida_labels.get(item["tipo_saida"], item["tipo_saida"]) for item in destino_agrupado],
            "values": [item["total"] for item in destino_agrupado],
        },
        "custos": {
            "labels": [tipo_saida_labels.get(item["tipo_saida"], item["tipo_saida"]) for item in destino_agrupado],
            "values": [float(item["custo"] or 0) for item in destino_agrupado],
        },
        "tipos": {
            "labels": [tipo_labels.get(item["desmembramento__tipo"], item["desmembramento__tipo"]) for item in tipo_agrupado],
            "values": [item["total"] for item in tipo_agrupado],
        },
        "alertas": {
            "labels": ["Dentro do esperado", "Abaixo do esperado"],
            "values": [max((totais["itens"] or 0) - total_alertas, 0), total_alertas],
        },
    }
    context = {
        "itens": itens[:200],
        "total_quantidade": totais["quantidade_gerada"] or 0,
        "total_custo": totais["custo_total"] or 0,
        "total_operacoes": totais["operacoes"] or 0,
        "total_alertas": total_alertas,
        "graficos_rendimento": graficos,
        "filiais": Filial.objects.filter(is_active=True).order_by("nome"),
        "tipos": TipoDesmembramentoProduto.choices,
        "tipos_saida": TipoSaidaDesmembramento.choices,
    }
    return render(request, "estoque/desmembramento_relatorio.html", context)


@login_required
@role_required(*ESTOQUE)
def desmembramento_relatorio_csv(request):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="relatorio_rendimento_desmembramento.csv"'
    response.write("\ufeff")
    writer = csv.writer(response, delimiter=";")
    writer.writerow(
        [
            "Data",
            "Filial",
            "Tipo",
            "Origem",
            "Qtd origem",
            "Destino",
            "Qtd destino",
            "Tipo destino",
            "Lote",
            "Validade",
            "Rendimento esperado %",
            "Rendimento real %",
            "Diferenca %",
            "Alerta",
            "Custo total",
            "Responsavel",
            "Motivo",
        ]
    )
    for item in _itens_desmembramento_relatorio(request):
        desmembramento = item.desmembramento
        writer.writerow(
            [
                desmembramento.criado_em.strftime("%d/%m/%Y %H:%M"),
                desmembramento.filial.nome,
                desmembramento.get_tipo_display(),
                desmembramento.produto_origem.nome,
                desmembramento.quantidade_origem,
                item.produto_destino.nome,
                item.quantidade_gerada,
                item.get_tipo_saida_display(),
                item.lote,
                item.validade.strftime("%d/%m/%Y") if item.validade else "",
                item.percentual_rendimento_esperado or "",
                item.percentual_rendimento,
                item.diferenca_rendimento if item.diferenca_rendimento is not None else "",
                "Abaixo do esperado" if item.rendimento_abaixo_esperado else "",
                item.custo_total,
                desmembramento.usuario.username,
                desmembramento.motivo,
            ]
        )
    return response


def _produto_busca_payload(produto):
    return {
        "id": produto.id,
        "text": f"{produto.nome} | {produto.codigo_barras or 'sem EAN'}",
        "nome": produto.nome,
        "codigo_barras": produto.codigo_barras,
        "codigo_interno": produto.codigo_interno,
        "unidade": produto.unidade,
        "preco_custo": str(produto.preco_custo),
    }


def _receita_payload(receita):
    return {
        "id": receita.id,
        "empresa_id": receita.empresa_id,
        "filial_id": receita.filial_id,
        "produto_origem_id": receita.produto_origem_id,
        "produto_origem_text": f"{receita.produto_origem.nome} | {receita.produto_origem.codigo_barras or 'sem EAN'}",
        "quantidade_origem": str(receita.quantidade_origem),
        "produto_destino_id": receita.produto_destino_id,
        "produto_destino_text": f"{receita.produto_destino.nome} | {receita.produto_destino.codigo_barras or 'sem EAN'}",
        "quantidade_destino": str(receita.quantidade_destino),
        "tipo": receita.tipo,
        "tipo_saida": receita.tipo_saida,
        "observacao": receita.observacao,
    }


@login_required
@role_required(*ESTOQUE)
@require_GET
def produtos_busca(request):
    termo = (request.GET.get("q") or request.GET.get("term") or "").strip()
    if not termo:
        return JsonResponse({"results": []})
    base_qs = Produto.objects.all()
    if request.GET.get("marketplace") == "1":
        base_qs = base_qs.filter(vendido_no_marketplace=True)

    exatos = list(
        base_qs.filter(Q(codigo_barras__iexact=termo) | Q(codigo_interno__iexact=termo)).select_related(
            "categoria", "marca"
        )[:10]
    )
    parciais = list(
        base_qs.filter(
            Q(codigo_barras__icontains=termo) | Q(codigo_interno__icontains=termo) | Q(nome__icontains=termo)
        )
        .exclude(pk__in=[produto.pk for produto in exatos])
        .select_related("categoria", "marca")
        .order_by("nome")[:20]
    )
    return JsonResponse({"results": [_produto_busca_payload(produto) for produto in exatos + parciais]})


@login_required
@role_required(*ESTOQUE)
@require_GET
def receita_desmembramento_json(request, pk):
    receita = get_object_or_404(
        ReceitaDesmembramento.objects.select_related("empresa", "filial", "produto_origem", "produto_destino"),
        pk=pk,
        is_active=True,
    )
    return JsonResponse({"status": "ok", "receita": _receita_payload(receita)})


def _destino_formset_initial(receita_id=None):
    if not receita_id:
        return [{"tipo_saida_destino": "VENDAVEL"}]
    try:
        receita = ReceitaDesmembramento.objects.get(pk=receita_id, is_active=True)
    except (ReceitaDesmembramento.DoesNotExist, ValueError, TypeError):
        return [{"tipo_saida_destino": "VENDAVEL"}]
    return [
        {
            "produto_destino": receita.produto_destino,
            "quantidade_destino": receita.quantidade_destino,
            "tipo_saida_destino": receita.tipo_saida,
        }
    ]


def _destinos_from_formset(formset, produto_origem):
    destinos = []
    for destino_form in formset:
        if not destino_form.cleaned_data or destino_form.cleaned_data.get("DELETE"):
            continue
        produto_destino = destino_form.cleaned_data["produto_destino"]
        if produto_destino == produto_origem:
            raise ValidationError("Produto origem e produto destino devem ser diferentes.")
        destinos.append(
            {
                "produto": produto_destino,
                "quantidade": destino_form.cleaned_data["quantidade_destino"],
                "tipo_saida": destino_form.cleaned_data["tipo_saida_destino"],
                "percentual_rendimento_esperado": destino_form.cleaned_data.get("percentual_rendimento_esperado"),
                "lote": destino_form.cleaned_data.get("lote", ""),
                "validade": destino_form.cleaned_data.get("validade"),
            }
        )
    if not destinos:
        raise ValidationError("Inclua ao menos um produto destino no desmembramento.")
    return destinos


@login_required
@role_required(*ESTOQUE)
def desmembramento_novo(request):
    previa = None
    if request.method == "POST":
        form = DesmembramentoProdutoForm(request.POST)
        destino_formset = DesmembramentoDestinoFormSet(request.POST, prefix="destinos")
        if form.is_valid() and destino_formset.is_valid():
            dados = form.cleaned_data.copy()
            dados.pop("receita", None)
            try:
                destinos = _destinos_from_formset(destino_formset, dados["produto_origem"])
                if request.POST.get("acao") == "simular":
                    previa = simular_desmembramento_multidestino(destinos=destinos, **dados)
                else:
                    supervisor = supervisor_from_request(request)
                    desmembramento = confirmar_desmembramento_multidestino(
                        usuario=request.user,
                        supervisor=supervisor,
                        ip=request.META.get("REMOTE_ADDR"),
                        destinos=destinos,
                        **dados,
                    )
            except ValidationError as exc:
                messages.error(request, " ".join(exc.messages))
            else:
                if previa is None:
                    messages.success(request, f"Desmembramento {desmembramento.id} confirmado e estoque atualizado.")
                    return redirect("estoque:desmembramentos")
    else:
        receita_id = request.GET.get("receita")
        form = DesmembramentoProdutoForm(initial={"receita": receita_id})
        destino_formset = DesmembramentoDestinoFormSet(initial=_destino_formset_initial(receita_id), prefix="destinos")
    return render(
        request,
        "estoque/desmembramento_form.html",
        {"form": form, "destino_formset": destino_formset, "previa": previa},
    )


@login_required
@role_required(*ESTOQUE)
def desmembramento_detalhe(request, pk):
    desmembramento = get_object_or_404(
        DesmembramentoProduto.objects.select_related("filial", "empresa", "produto_origem", "usuario").prefetch_related(
            "itens__produto_destino"
        ),
        pk=pk,
    )
    return render(request, "estoque/desmembramento_detalhe.html", {"desmembramento": desmembramento})


@login_required
@role_required(*ESTOQUE)
def desmembramento_cancelar(request, pk):
    desmembramento = get_object_or_404(DesmembramentoProduto, pk=pk)
    if request.method != "POST":
        return redirect("estoque:desmembramento_detalhe", pk=desmembramento.pk)
    try:
        supervisor = supervisor_from_request(request)
        cancelar_desmembramento_produto(
            desmembramento=desmembramento,
            usuario=request.user,
            motivo=request.POST.get("motivo", "").strip(),
            supervisor=supervisor,
            ip=request.META.get("REMOTE_ADDR"),
        )
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(request, "Desmembramento cancelado e estoque revertido.")
    return redirect("estoque:desmembramento_detalhe", pk=desmembramento.pk)

# Create your views here.
