import csv
from collections import OrderedDict
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_DOWN

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Case, Count, F, IntegerField, Q, Sum, Value, When
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import CreateView, ListView, UpdateView

from apps.accounts.models import PerfilUsuario, TipoPerfil
from apps.accounts.permissions import ESTOQUE, RoleRequiredMixin, role_required, supervisor_from_request
from apps.auditoria.models import LogAuditoria
from apps.empresas.models import AcaoPinSupervisor
from apps.produtos.models import Produto

from .escopo import (
    alertas_sla_para_usuario,
    composicoes_para_usuario,
    configuracoes_sla_para_usuario,
    desmembramentos_para_usuario,
    estoques_para_usuario,
    filiais_para_usuario,
    inventarios_para_usuario,
    itens_desmembramento_para_usuario,
    lotes_para_usuario,
    ordens_producao_para_usuario,
    perdas_para_usuario,
    producoes_composicao_para_usuario,
    receitas_desmembramento_para_usuario,
    usuarios_para_usuario,
)
from .forms import (
    ComposicaoProdutoForm,
    ConfiguracaoSLASetorProducaoForm,
    AtribuirSaldoLoteForm,
    DesmembramentoDestinoFormSet,
    DesmembramentoProdutoForm,
    InventarioEstoqueForm,
    ItemComposicaoProdutoFormSet,
    ItemInventarioEstoqueForm,
    MovimentacaoEstoqueForm,
    OrdemProducaoComposicaoForm,
    PerdaEstoqueForm,
    ProducaoComposicaoForm,
    ReceitaDesmembramentoForm,
)
from .models import (
    ComposicaoProduto,
    AlertaSLAOrdemProducao,
    ConfiguracaoSLASetorProducao,
    DesmembramentoProduto,
    Estoque,
    HistoricoEtapaOrdemProducaoComposicao,
    InventarioEstoque,
    ItemDesmembramentoProduto,
    LoteEstoque,
    OrdemProducaoComposicao,
    PerdaEstoque,
    ProducaoComposicaoProduto,
    ReceitaDesmembramento,
    StatusInventario,
    StatusOrdemProducaoComposicao,
    StatusProducaoComposicao,
    TipoDesmembramentoProduto,
    TipoSaidaDesmembramento,
    movimentar_estoque,
)
from .services import (
    aplicar_inventario,
    atribuir_saldo_historico_lote,
    cancelar_producao_composicao,
    cancelar_ordem_producao_composicao,
    cancelar_desmembramento_produto,
    confirmar_desmembramento_multidestino,
    confirmar_ordem_producao_composicao,
    confirmar_desmembramento_simples,
    confirmar_producao_composicao,
    registrar_perda_estoque,
    saldo_rastreado_lotes,
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

    capacidade_maxima = capacidade_maxima if capacidade_maxima is not None else _decimal_zero()
    estoque_minimo = composicao.produto_final.estoque_minimo or _decimal_zero()
    demanda_reposicao = max(estoque_minimo - estoque_final, _decimal_zero())
    producao_sugerida = min(demanda_reposicao, capacidade_maxima)

    return {
        "componentes": componentes,
        "custo_previsto": custo_previsto,
        "estoque_final": estoque_final,
        "estoque_minimo": estoque_minimo,
        "demanda_reposicao": demanda_reposicao,
        "producao_sugerida": producao_sugerida,
        "capacidade_maxima": capacidade_maxima,
    }


def _programar_ordens_por_sugestao(*, composicoes, usuario, data_programada, ip=None):
    criadas = []
    ignoradas = []
    for composicao in composicoes:
        resumo = _resumo_visual_composicao(composicao)
        quantidade = resumo["producao_sugerida"]
        if quantidade <= 0:
            ignoradas.append((composicao, "sem_demanda"))
            continue
        if not composicao.filial_id:
            ignoradas.append((composicao, "sem_filial"))
            continue
        if OrdemProducaoComposicao.objects.filter(
            composicao=composicao,
            filial=composicao.filial,
            data_programada=data_programada,
            status=StatusOrdemProducaoComposicao.PLANEJADA,
        ).exists():
            ignoradas.append((composicao, "duplicada"))
            continue
        ordem = OrdemProducaoComposicao.objects.create(
            composicao=composicao,
            empresa=composicao.empresa,
            filial=composicao.filial,
            produto_final=composicao.produto_final,
            quantidade_planejada=quantidade,
            data_programada=data_programada,
            prioridade="NORMAL",
            setor_responsavel="Produção interna",
            etapa_operacional="AGUARDANDO",
            usuario=usuario,
            motivo="Reposicao automática ate estoque mínimo",
            observacao=(
                f"Gerada pelo planejamento: estoque final {resumo['estoque_final']}, "
                f"minimo {resumo['estoque_minimo']}, demanda {resumo['demanda_reposicao']}."
            ),
        )
        criadas.append(ordem)
        LogAuditoria.objects.create(
            usuario=usuario,
            modulo="estoque",
            acao="ORDEM_PRODUCAO_COMPOSICAO_SUGERIDA",
            descricao=f"Ordem de producao {ordem.id} gerada automaticamente pela demanda minima.",
            objeto_tipo="OrdemProducaoComposicao",
            objeto_id=str(ordem.id),
            ip=ip,
        )
    return criadas, ignoradas


class EstoqueListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    required_roles = ESTOQUE
    model = Estoque
    template_name = "estoque/estoque_list.html"
    context_object_name = "estoques"
    paginate_by = 30

    def get_queryset(self):
        queryset = estoques_para_usuario(
            self.request.user,
            Estoque.objects.select_related("produto", "filial", "filial__empresa"),
        ).order_by("produto__nome")
        termo = self.request.GET.get("q")
        if termo:
            queryset = queryset.filter(produto__nome__icontains=termo) | queryset.filter(produto__codigo_barras__icontains=termo)
        return queryset


class LoteEstoqueListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    required_roles = ESTOQUE
    model = LoteEstoque
    template_name = "estoque/lote_list.html"
    context_object_name = "lotes"
    paginate_by = 40

    def get_queryset(self):
        queryset = lotes_para_usuario(
            self.request.user,
            LoteEstoque.objects.select_related("produto", "filial", "filial__empresa"),
        )
        termo = (self.request.GET.get("q") or "").strip()
        if termo:
            queryset = queryset.filter(
                Q(codigo__icontains=termo)
                | Q(produto__nome__icontains=termo)
                | Q(produto__codigo_barras__icontains=termo)
            )
        situacao = self.request.GET.get("situacao")
        hoje = timezone.localdate()
        if situacao == "VENCIDO":
            queryset = queryset.filter(validade__lt=hoje, quantidade_atual__gt=0)
        elif situacao == "PROXIMO":
            queryset = queryset.filter(
                validade__gte=hoje,
                validade__lte=hoje + timedelta(days=30),
                quantidade_atual__gt=0,
            )
        elif situacao == "COM_SALDO":
            queryset = queryset.filter(quantidade_atual__gt=0)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        hoje = timezone.localdate()
        base = lotes_para_usuario(self.request.user, LoteEstoque.objects.filter(quantidade_atual__gt=0))
        context["resumo_lotes"] = {
            "com_saldo": base.count(),
            "vencidos": base.filter(validade__lt=hoje).count(),
            "proximos": base.filter(validade__gte=hoje, validade__lte=hoje + timedelta(days=30)).count(),
            "sem_validade": base.filter(validade__isnull=True).count(),
        }
        return context


@login_required
@role_required(*ESTOQUE)
def reconciliacao_lotes(request):
    estoques = list(
        estoques_para_usuario(
            request.user,
            Estoque.objects.select_related("produto", "filial", "filial__empresa"),
        ).order_by("produto__nome", "filial__nome")
    )
    termo = (request.GET.get("q") or "").strip()
    if termo:
        termo_normalizado = termo.casefold()
        estoques = [
            estoque
            for estoque in estoques
            if termo_normalizado in estoque.produto.nome.casefold()
            or termo_normalizado in estoque.produto.codigo_barras.casefold()
            or termo_normalizado in estoque.filial.nome.casefold()
        ]
    linhas = []
    for estoque in estoques:
        rastreado = saldo_rastreado_lotes(produto=estoque.produto, filial=estoque.filial)
        sem_lote = estoque.quantidade_atual - rastreado
        if sem_lote > 0:
            linhas.append({"estoque": estoque, "rastreado": rastreado, "sem_lote": sem_lote})
    return render(request, "estoque/reconciliacao_lotes.html", {"linhas": linhas})


@login_required
@role_required(*ESTOQUE)
def atribuir_saldo_lote(request, pk):
    estoque = get_object_or_404(
        estoques_para_usuario(
            request.user, Estoque.objects.select_related("produto", "filial", "filial__empresa")
        ),
        pk=pk,
    )
    rastreado = saldo_rastreado_lotes(produto=estoque.produto, filial=estoque.filial)
    saldo_sem_lote = estoque.quantidade_atual - rastreado
    if request.method == "POST":
        form = AtribuirSaldoLoteForm(request.POST)
        if form.is_valid():
            try:
                supervisor = supervisor_from_request(request, acao=AcaoPinSupervisor.ESTOQUE_AJUSTE)
                lote = atribuir_saldo_historico_lote(
                    estoque=estoque,
                    usuario=request.user,
                    supervisor=supervisor,
                    ip=request.META.get("REMOTE_ADDR"),
                    **form.cleaned_data,
                )
            except ValidationError as exc:
                for mensagem in exc.messages:
                    form.add_error(None, mensagem)
            else:
                messages.success(request, f"Saldo atribuido ao lote {lote.codigo} sem alterar o estoque agregado.")
                return redirect("estoque:reconciliacao_lotes")
    else:
        form = AtribuirSaldoLoteForm(initial={"custo_unitario": estoque.produto.preco_custo})
    return render(
        request,
        "estoque/atribuicao_lote_form.html",
        {
            "estoque": estoque,
            "saldo_rastreado": rastreado,
            "saldo_sem_lote": saldo_sem_lote,
            "form": form,
        },
    )


@login_required
@role_required(*ESTOQUE)
def movimentar(request):
    if request.method == "POST":
        form = MovimentacaoEstoqueForm(request.POST, user=request.user)
        if form.is_valid():
            try:
                supervisor = supervisor_from_request(request, acao=AcaoPinSupervisor.ESTOQUE_AJUSTE)
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
                messages.success(request, "Movimentação registrada com sucesso.")
                return redirect("estoque:lista")
    else:
        form = MovimentacaoEstoqueForm(user=request.user)

    return render(request, "estoque/movimentacao_form.html", {"form": form})


class InventarioListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    required_roles = ESTOQUE
    model = InventarioEstoque
    template_name = "estoque/inventario_list.html"
    context_object_name = "inventarios"
    paginate_by = 25

    def get_queryset(self):
        return inventarios_para_usuario(
            self.request.user, InventarioEstoque.objects.select_related("filial", "usuario")
        ).order_by("-criado_em")


class CriarInventarioView(LoginRequiredMixin, RoleRequiredMixin, CreateView):
    required_roles = ESTOQUE
    model = InventarioEstoque
    form_class = InventarioEstoqueForm
    template_name = "estoque/inventario_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

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
        inventarios_para_usuario(
            request.user,
            InventarioEstoque.objects.select_related("filial", "usuario").prefetch_related("itens__produto"),
        ),
        pk=pk,
    )
    return render(request, "estoque/inventario_detalhe.html", {"inventario": inventario})


@login_required
@role_required(*ESTOQUE)
def adicionar_item_inventario(request, pk):
    inventario = get_object_or_404(inventarios_para_usuario(request.user), pk=pk)
    if inventario.status != StatusInventario.ABERTO:
        messages.error(request, "Não e possível editar inventario aplicado ou cancelado.")
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
    inventario = get_object_or_404(inventarios_para_usuario(request.user), pk=pk)
    if request.method != "POST":
        return redirect("estoque:inventario_detalhe", pk=inventario.pk)
    try:
        supervisor = supervisor_from_request(request, acao=AcaoPinSupervisor.ESTOQUE_AJUSTE)
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
        return perdas_para_usuario(
            self.request.user, PerdaEstoque.objects.select_related("produto", "filial", "usuario")
        ).order_by("-data")


@login_required
@role_required(*ESTOQUE)
def registrar_perda(request):
    if request.method == "POST":
        form = PerdaEstoqueForm(request.POST, user=request.user)
        if form.is_valid():
            try:
                supervisor = supervisor_from_request(request, acao=AcaoPinSupervisor.ESTOQUE_AJUSTE)
                registrar_perda_estoque(usuario=request.user, supervisor=supervisor, ip=request.META.get("REMOTE_ADDR"), **form.cleaned_data)
            except ValidationError as exc:
                messages.error(request, " ".join(exc.messages))
            else:
                messages.success(request, "Perda registrada e estoque baixado.")
                return redirect("estoque:perdas")
    else:
        form = PerdaEstoqueForm(user=request.user)
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
    queryset = desmembramentos_para_usuario(
        request.user,
        DesmembramentoProduto.objects.select_related(
            "filial", "empresa", "produto_origem", "usuario"
        ).prefetch_related("itens__produto_destino"),
    )
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
        queryset = receitas_desmembramento_para_usuario(
            self.request.user,
            ReceitaDesmembramento.objects.select_related(
                "empresa", "filial", "produto_origem", "produto_destino"
            ),
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

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Receita de desmembramento cadastrada.")
        return super().form_valid(form)


class ReceitaDesmembramentoUpdateView(LoginRequiredMixin, RoleRequiredMixin, UpdateView):
    required_roles = ESTOQUE
    model = ReceitaDesmembramento
    form_class = ReceitaDesmembramentoForm
    template_name = "estoque/receita_desmembramento_form.html"
    success_url = reverse_lazy("estoque:receitas_desmembramento")

    def get_queryset(self):
        return receitas_desmembramento_para_usuario(self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

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
        queryset = composicoes_para_usuario(self.request.user, queryset)
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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        composicoes = list(context["composicoes"])
        total_capacidade = Decimal("0.000")
        total_demanda = Decimal("0.000")
        total_sugestao = Decimal("0.000")
        total_alertas = 0
        total_alertas_demanda = 0
        for composicao in composicoes:
            resumo = _resumo_visual_composicao(composicao)
            composicao.resumo_visual = resumo
            composicao.tem_alerta_insumo = (
                composicao.is_active
                and bool(resumo["componentes"])
                and (
                    resumo["capacidade_maxima"] <= 0
                    or any(not componente["suficiente"] for componente in resumo["componentes"])
                )
            )
            if composicao.tem_alerta_insumo:
                total_alertas += 1
            composicao.tem_demanda_producao = resumo["demanda_reposicao"] > 0
            if composicao.tem_demanda_producao:
                total_alertas_demanda += 1
            total_capacidade += resumo["capacidade_maxima"]
            total_demanda += resumo["demanda_reposicao"]
            total_sugestao += resumo["producao_sugerida"]
            composicao.pode_produzir_capacidade = resumo["capacidade_maxima"] > 0
            quantidade_planejada = resumo["producao_sugerida"] or resumo["capacidade_maxima"]
            composicao.quantidade_planejada = f"{quantidade_planejada:.3f}"
            composicao.rotulo_producao_planejada = "Produzir sugestão" if resumo["producao_sugerida"] > 0 else "Produzir capacidade"
        context["composicoes"] = composicoes
        context["total_composicoes"] = len(composicoes)
        context["total_capacidade"] = total_capacidade
        context["total_demanda_producao"] = total_demanda
        context["total_producao_sugerida"] = total_sugestao
        context["total_alertas_insumo"] = total_alertas
        context["total_alertas_demanda"] = total_alertas_demanda
        return context


def _composicoes_filtradas(request):
    queryset = composicoes_para_usuario(
        request.user,
        ComposicaoProduto.objects.select_related("empresa", "filial", "produto_final").prefetch_related(
            "itens__produto_componente"
        ),
    )
    termo = (request.GET.get("q") or "").strip()
    if termo:
        queryset = queryset.filter(
            Q(produto_final__nome__icontains=termo)
            | Q(produto_final__codigo_barras__icontains=termo)
            | Q(itens__produto_componente__nome__icontains=termo)
            | Q(itens__produto_componente__codigo_barras__icontains=termo)
        ).distinct()
    return queryset.order_by("produto_final__nome")


@login_required
@role_required(*ESTOQUE)
def composicoes_csv(request):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="planejamento_composicoes.csv"'
    response.write("\ufeff")
    writer = csv.writer(response, delimiter=";")
    writer.writerow(
        [
            "ID",
            "Empresa",
            "Filial",
            "Produto final",
            "Código produto final",
            "Tipo",
            "Qtd receita",
            "Componentes",
            "Estoque final",
            "Estoque mínimo",
            "Demanda reposicao",
            "Capacidade componentes",
            "Produção sugerida",
            "Custo previsto",
            "Status planejamento",
        ]
    )
    for composicao in _composicoes_filtradas(request):
        resumo = _resumo_visual_composicao(composicao)
        tem_insumo_baixo = (
            composicao.is_active
            and bool(resumo["componentes"])
            and (
                resumo["capacidade_maxima"] <= 0
                or any(not componente["suficiente"] for componente in resumo["componentes"])
            )
        )
        if tem_insumo_baixo:
            status = "Insumo baixo"
        elif resumo["demanda_reposicao"] > 0:
            status = "Produzir"
        elif composicao.is_active:
            status = "Ativa"
        else:
            status = "Inativa"
        writer.writerow(
            [
                composicao.id,
                composicao.empresa.nome_fantasia or composicao.empresa.razao_social,
                composicao.filial.nome if composicao.filial_id else "Todas",
                composicao.produto_final.nome,
                composicao.produto_final.codigo_barras,
                composicao.get_tipo_display(),
                composicao.quantidade_final,
                len(resumo["componentes"]),
                resumo["estoque_final"],
                resumo["estoque_minimo"],
                resumo["demanda_reposicao"],
                resumo["capacidade_maxima"],
                resumo["producao_sugerida"],
                resumo["custo_previsto"],
                status,
            ]
        )
    return response


@login_required
@role_required(*ESTOQUE)
@require_POST
def composicoes_programar_sugestoes(request):
    data_programada = timezone.localdate()
    data_informada = (request.POST.get("data_programada") or "").strip()
    if data_informada:
        try:
            data_programada = date.fromisoformat(data_informada)
        except ValueError:
            messages.error(request, "Data de programacao inválida.")
            return redirect("estoque:composicoes")
    composicoes = list(_composicoes_filtradas(request).filter(is_active=True))
    criadas, ignoradas = _programar_ordens_por_sugestao(
        composicoes=composicoes,
        usuario=request.user,
        data_programada=data_programada,
        ip=request.META.get("REMOTE_ADDR"),
    )
    if criadas:
        messages.success(request, f"{len(criadas)} ordem(ns) de produção programada(s) por demanda.")
    else:
        messages.info(request, "Nenhuma ordem nova foi gerada pelas sugestoes atuais.")
    duplicadas = sum(1 for _, motivo in ignoradas if motivo == "duplicada")
    sem_filial = sum(1 for _, motivo in ignoradas if motivo == "sem_filial")
    if duplicadas:
        messages.info(request, f"{duplicadas} composicao(oes) ja tinham ordem planejada para a data.")
    if sem_filial:
        messages.warning(request, f"{sem_filial} composicao(oes) sem filial fixa nao foram programadas automaticamente.")
    return redirect("estoque:ordens_producao_composicao")


def _producoes_composicao_filtradas(request):
    queryset = producoes_composicao_para_usuario(
        request.user,
        ProducaoComposicaoProduto.objects.select_related(
            "empresa",
            "filial",
            "produto_final",
            "composicao",
            "usuario",
        ).prefetch_related("itens__produto_componente"),
    )
    termo = (request.GET.get("q") or "").strip()
    data_inicio = request.GET.get("inicio")
    data_fim = request.GET.get("fim")
    filial_id = request.GET.get("filial")
    status = request.GET.get("status")
    if termo:
        queryset = queryset.filter(
            Q(produto_final__nome__icontains=termo)
            | Q(produto_final__codigo_barras__icontains=termo)
            | Q(motivo__icontains=termo)
            | Q(itens__produto_componente__nome__icontains=termo)
            | Q(itens__produto_componente__codigo_barras__icontains=termo)
        ).distinct()
    if data_inicio:
        queryset = queryset.filter(criado_em__date__gte=data_inicio)
    if data_fim:
        queryset = queryset.filter(criado_em__date__lte=data_fim)
    if filial_id:
        queryset = queryset.filter(filial_id=filial_id)
    if status:
        queryset = queryset.filter(status=status)
    return queryset.order_by("-criado_em")


def _ordens_producao_composicao_relatorio(request):
    termo = (request.GET.get("q") or "").strip()
    data_inicio = request.GET.get("inicio")
    data_fim = request.GET.get("fim")
    filial_id = request.GET.get("filial")
    status = request.GET.get("status")
    queryset = ordens_producao_para_usuario(
        request.user,
        OrdemProducaoComposicao.objects.select_related(
            "filial",
            "produto_final",
            "responsavel_operacional",
            "usuario",
        ).prefetch_related("historico_etapas"),
    )
    if termo:
        queryset = queryset.filter(
            Q(produto_final__nome__icontains=termo)
            | Q(produto_final__codigo_barras__icontains=termo)
            | Q(motivo__icontains=termo)
            | Q(responsavel_operacional__username__icontains=termo)
            | Q(usuario__username__icontains=termo)
        )
    if data_inicio:
        queryset = queryset.filter(data_programada__gte=data_inicio)
    if data_fim:
        queryset = queryset.filter(data_programada__lte=data_fim)
    if filial_id:
        queryset = queryset.filter(filial_id=filial_id)
    if status == StatusProducaoComposicao.CONFIRMADO:
        queryset = queryset.filter(status=StatusOrdemProducaoComposicao.PRODUZIDA)
    elif status == StatusProducaoComposicao.CANCELADO:
        queryset = queryset.filter(status=StatusOrdemProducaoComposicao.CANCELADA)
    return list(queryset.order_by("data_programada", "produto_final__nome"))


def _formatar_duracao_minutos(minutos):
    minutos = max(int(minutos), 0)
    if minutos < 60:
        return f"{minutos} min"
    horas, resto = divmod(minutos, 60)
    if horas < 24:
        return f"{horas}h {resto:02d}min"
    dias, horas = divmod(horas, 24)
    return f"{dias}d {horas:02d}h"


def _resumo_duracao_etapas_ordens(ordens):
    agora = timezone.now()
    escolhas = dict(OrdemProducaoComposicao._meta.get_field("etapa_operacional").choices)
    resumo = OrderedDict(
        (
            codigo,
            {
                "codigo": codigo,
                "etapa": rotulo,
                "apontamentos": 0,
                "minutos_total": 0,
                "maior_minutos": 0,
                "ordem_maior": None,
            },
        )
        for codigo, rotulo in escolhas.items()
    )
    for ordem in ordens:
        inicio_segmento = ordem.criado_em
        eventos = sorted(ordem.historico_etapas.all(), key=lambda item: item.criado_em)
        etapa_atual = ordem.etapa_operacional
        for evento in eventos:
            etapa_segmento = evento.etapa_anterior or etapa_atual
            minutos = max(int((evento.criado_em - inicio_segmento).total_seconds() // 60), 0)
            item = resumo.get(etapa_segmento)
            if item is not None:
                item["apontamentos"] += 1
                item["minutos_total"] += minutos
                if minutos >= item["maior_minutos"]:
                    item["maior_minutos"] = minutos
                    item["ordem_maior"] = ordem
            etapa_atual = evento.etapa_nova
            inicio_segmento = evento.criado_em
        fim_segmento = ordem.concluido_em or agora
        minutos = max(int((fim_segmento - inicio_segmento).total_seconds() // 60), 0)
        item = resumo.get(etapa_atual)
        if item is not None:
            item["apontamentos"] += 1
            item["minutos_total"] += minutos
            if minutos >= item["maior_minutos"]:
                item["maior_minutos"] = minutos
                item["ordem_maior"] = ordem
    linhas = []
    for item in resumo.values():
        if not item["apontamentos"]:
            continue
        media = item["minutos_total"] // item["apontamentos"]
        item["media_label"] = _formatar_duracao_minutos(media)
        item["total_label"] = _formatar_duracao_minutos(item["minutos_total"])
        item["maior_label"] = _formatar_duracao_minutos(item["maior_minutos"])
        linhas.append(item)
    return linhas


SLA_SETOR_PRODUCAO_MINUTOS = {
    "Padaria": 180,
    "Acougue": 120,
    "Açougue": 120,
    "Hortifruti": 90,
    "Cozinha": 240,
    "Sem setor": 240,
}


def _metas_sla_setor_producao(ordens):
    empresas = {ordem.empresa_id for ordem in ordens if ordem.empresa_id}
    filiais = {ordem.filial_id for ordem in ordens if ordem.filial_id}
    metas = {}
    configuracoes = ConfiguracaoSLASetorProducao.objects.filter(
        is_active=True,
        empresa_id__in=empresas,
    ).filter(Q(filial_id__in=filiais) | Q(filial__isnull=True))
    for configuracao in configuracoes:
        chave = (configuracao.empresa_id, configuracao.filial_id, configuracao.setor.strip().lower())
        metas[chave] = configuracao.meta_minutos
    return metas


def _meta_sla_para_ordem(ordem, setor, metas):
    setor_chave = setor.strip().lower()
    return (
        metas.get((ordem.empresa_id, ordem.filial_id, setor_chave))
        or metas.get((ordem.empresa_id, None, setor_chave))
        or SLA_SETOR_PRODUCAO_MINUTOS.get(setor)
        or 240
    )


def _duracao_total_ordem_minutos(ordem, agora):
    fim = ordem.concluido_em or agora
    return max(int((fim - ordem.criado_em).total_seconds() // 60), 0)


def _resumo_sla_setores_ordens(ordens):
    agora = timezone.now()
    metas = _metas_sla_setor_producao(ordens)
    resumo = OrderedDict()
    for ordem in ordens:
        setor = ordem.setor_responsavel or "Sem setor"
        meta_minutos = _meta_sla_para_ordem(ordem, setor, metas)
        duracao_minutos = _duracao_total_ordem_minutos(ordem, agora)
        if setor not in resumo:
            resumo[setor] = {
                "setor": setor,
                "meta_minutos": meta_minutos,
                "meta_label": _formatar_duracao_minutos(meta_minutos),
                "ordens": 0,
                "dentro": 0,
                "fora": 0,
                "minutos_total": 0,
                "maior_minutos": 0,
                "ordem_critica": None,
            }
        item = resumo[setor]
        item["ordens"] += 1
        item["minutos_total"] += duracao_minutos
        if duracao_minutos <= meta_minutos:
            item["dentro"] += 1
        else:
            item["fora"] += 1
        if duracao_minutos >= item["maior_minutos"]:
            item["maior_minutos"] = duracao_minutos
            item["ordem_critica"] = ordem
    linhas = []
    for item in resumo.values():
        media = item["minutos_total"] // item["ordens"] if item["ordens"] else 0
        item["media_label"] = _formatar_duracao_minutos(media)
        item["maior_label"] = _formatar_duracao_minutos(item["maior_minutos"])
        item["aderencia"] = round((item["dentro"] / item["ordens"]) * 100) if item["ordens"] else 0
        item["status"] = "Dentro da meta" if item["fora"] == 0 else "Fora da meta"
        linhas.append(item)
    return sorted(linhas, key=lambda item: (-item["fora"], item["aderencia"], item["setor"]))


@login_required
@role_required(*ESTOQUE)
def composicao_producoes_relatorio(request):
    from apps.empresas.models import Filial

    producoes = _producoes_composicao_filtradas(request)
    ordens_relatorio = _ordens_producao_composicao_relatorio(request)
    duracao_etapas = _resumo_duracao_etapas_ordens(ordens_relatorio)
    sla_setores = _resumo_sla_setores_ordens(ordens_relatorio)
    totais = producoes.aggregate(
        operacoes=Count("id"),
        quantidade=Sum("quantidade_final"),
        custo=Sum("custo_total"),
    )
    total_canceladas = producoes.filter(status=StatusProducaoComposicao.CANCELADO).count()
    agrupado_status = list(producoes.values("status").annotate(total=Count("id")).order_by("status"))
    status_labels = dict(StatusProducaoComposicao.choices)
    graficos = {
        "status": {
            "labels": [status_labels.get(item["status"], item["status"]) for item in agrupado_status],
            "values": [item["total"] for item in agrupado_status],
        }
    }
    return render(
        request,
        "estoque/composicao_producoes_relatorio.html",
        {
            "producoes": Paginator(producoes, 50).get_page(request.GET.get("page")),
            "total_operacoes": totais["operacoes"] or 0,
            "total_quantidade": totais["quantidade"] or 0,
            "total_custo": totais["custo"] or 0,
            "total_canceladas": total_canceladas,
            "graficos_producao": graficos,
            "duracao_etapas": duracao_etapas,
            "sla_setores": sla_setores,
            "filiais": filiais_para_usuario(request.user, Filial.objects.filter(is_active=True)).order_by("nome"),
            "status_opcoes": StatusProducaoComposicao.choices,
        },
    )


@login_required
@role_required(*ESTOQUE)
def composicao_producoes_relatorio_csv(request):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="relatorio_producoes_composicao.csv"'
    response.write("\ufeff")
    writer = csv.writer(response, delimiter=";")
    writer.writerow(
        [
            "Data",
            "Empresa",
            "Filial",
            "Produto final",
            "Código produto final",
            "Qtd produzida",
            "Custo total",
            "Status",
            "Responsavel",
            "Motivo",
            "Componentes consumidos",
        ]
    )
    for producao in _producoes_composicao_filtradas(request):
        componentes = " | ".join(
            f"{item.produto_componente.nome}: {item.quantidade_consumida}"
            for item in producao.itens.all()
        )
        writer.writerow(
            [
                producao.criado_em.strftime("%d/%m/%Y %H:%M"),
                producao.empresa.nome_fantasia or producao.empresa.razao_social,
                producao.filial.nome,
                producao.produto_final.nome,
                producao.produto_final.codigo_barras,
                producao.quantidade_final,
                producao.custo_total,
                producao.get_status_display(),
                producao.usuario.username,
                producao.motivo,
                componentes,
            ]
        )
    writer.writerow([])
    writer.writerow(["Resumo de duracao por etapa das ordens"])
    writer.writerow(["Etapa", "Apontamentos", "Tempo total", "Media", "Maior tempo", "Ordem critica"])
    for etapa in _resumo_duracao_etapas_ordens(_ordens_producao_composicao_relatorio(request)):
        ordem_critica = ""
        if etapa["ordem_maior"]:
            ordem_critica = f"Ordem #{etapa['ordem_maior'].id} - {etapa['ordem_maior'].produto_final.nome}"
        writer.writerow(
            [
                etapa["etapa"],
                etapa["apontamentos"],
                etapa["total_label"],
                etapa["media_label"],
                etapa["maior_label"],
                ordem_critica,
            ]
        )
    writer.writerow([])
    writer.writerow(["Resumo de SLA por setor"])
    writer.writerow(["Setor", "Meta", "Ordens", "Dentro da meta", "Fora da meta", "Aderencia", "Media", "Maior tempo", "Status", "Ordem critica"])
    for item in _resumo_sla_setores_ordens(_ordens_producao_composicao_relatorio(request)):
        ordem_critica = ""
        if item["ordem_critica"]:
            ordem_critica = f"Ordem #{item['ordem_critica'].id} - {item['ordem_critica'].produto_final.nome}"
        writer.writerow(
            [
                item["setor"],
                item["meta_label"],
                item["ordens"],
                item["dentro"],
                item["fora"],
                f"{item['aderencia']}%",
                item["media_label"],
                item["maior_label"],
                item["status"],
                ordem_critica,
            ]
        )
    return response


class OrdemProducaoComposicaoListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    required_roles = ESTOQUE
    model = OrdemProducaoComposicao
    template_name = "estoque/ordem_producao_composicao_list.html"
    context_object_name = "ordens"
    paginate_by = 50

    def get_queryset(self):
        return _ordens_producao_composicao_filtradas(self.request)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        _marcar_ultimo_apontamento(context["ordens"])
        base = self.get_queryset()
        hoje = timezone.localdate()
        planejadas = base.filter(status=StatusOrdemProducaoComposicao.PLANEJADA)
        context["total_planejadas"] = base.filter(status=StatusOrdemProducaoComposicao.PLANEJADA).count()
        context["total_produzidas"] = base.filter(status=StatusOrdemProducaoComposicao.PRODUZIDA).count()
        context["total_canceladas"] = base.filter(status=StatusOrdemProducaoComposicao.CANCELADA).count()
        context["total_quantidade_planejada"] = base.aggregate(total=Sum("quantidade_planejada"))["total"] or 0
        context["fila_producao"] = {
            "atrasadas": planejadas.filter(data_programada__lt=hoje).count(),
            "hoje": planejadas.filter(data_programada=hoje).count(),
            "proximas": planejadas.filter(data_programada__gt=hoje).count(),
            "urgentes": planejadas.filter(prioridade="URGENTE").count(),
            "data_hoje": hoje,
            "data_ontem": hoje - timedelta(days=1),
            "data_amanha": hoje + timedelta(days=1),
        }
        context["fila_por_setor"] = (
            planejadas.exclude(setor_responsavel="")
            .values("setor_responsavel")
            .annotate(total=Count("id"), quantidade=Sum("quantidade_planejada"))
            .order_by("-total", "setor_responsavel")[:6]
        )
        context["status_opcoes"] = StatusOrdemProducaoComposicao.choices
        context["prioridade_opcoes"] = OrdemProducaoComposicao._meta.get_field("prioridade").choices
        context["etapa_opcoes"] = OrdemProducaoComposicao._meta.get_field("etapa_operacional").choices
        context["responsaveis_opcoes"] = usuarios_para_usuario(
            self.request.user, get_user_model().objects.filter(is_active=True)
        ).order_by("username")
        return context


class ConfiguracaoSLASetorProducaoListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    required_roles = ESTOQUE
    model = ConfiguracaoSLASetorProducao
    template_name = "estoque/sla_setor_producao_list.html"
    context_object_name = "configuracoes"
    paginate_by = 50

    def get_queryset(self):
        termo = (self.request.GET.get("q") or "").strip()
        queryset = configuracoes_sla_para_usuario(
            self.request.user,
            ConfiguracaoSLASetorProducao.objects.select_related("empresa", "filial"),
        )
        if termo:
            queryset = queryset.filter(
                Q(setor__icontains=termo)
                | Q(empresa__nome_fantasia__icontains=termo)
                | Q(empresa__razao_social__icontains=termo)
                | Q(filial__nome__icontains=termo)
            )
        return queryset.order_by("empresa__nome_fantasia", "filial__nome", "setor")


class ConfiguracaoSLASetorProducaoCreateView(LoginRequiredMixin, RoleRequiredMixin, CreateView):
    required_roles = ESTOQUE
    model = ConfiguracaoSLASetorProducao
    form_class = ConfiguracaoSLASetorProducaoForm
    template_name = "estoque/sla_setor_producao_form.html"
    success_url = reverse_lazy("estoque:slas_setor_producao")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs


class ConfiguracaoSLASetorProducaoUpdateView(LoginRequiredMixin, RoleRequiredMixin, UpdateView):
    required_roles = ESTOQUE
    model = ConfiguracaoSLASetorProducao
    form_class = ConfiguracaoSLASetorProducaoForm
    template_name = "estoque/sla_setor_producao_form.html"
    success_url = reverse_lazy("estoque:slas_setor_producao")

    def get_queryset(self):
        return configuracoes_sla_para_usuario(self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs


@login_required
@role_required(*ESTOQUE)
def alertas_sla_producao(request):
    filtro = request.GET.get("status") or "abertos"
    alertas = alertas_sla_para_usuario(
        request.user,
        AlertaSLAOrdemProducao.objects.select_related(
            "ordem",
            "ordem__produto_final",
            "ordem__filial",
            "usuario",
        ),
    ).filter(usuario=request.user)
    if filtro == "visualizados":
        alertas = alertas.filter(visualizado_em__isnull=False)
    elif filtro != "todos":
        filtro = "abertos"
        alertas = alertas.filter(visualizado_em__isnull=True)
    resumo_base = alertas_sla_para_usuario(request.user).filter(usuario=request.user)
    resumo = {
        "abertos": resumo_base.filter(visualizado_em__isnull=True).count(),
        "visualizados": resumo_base.filter(visualizado_em__isnull=False).count(),
        "total": resumo_base.count(),
    }
    return render(
        request,
        "estoque/alertas_sla_producao.html",
        {
            "alertas": Paginator(alertas.order_by("-criado_em"), 50).get_page(request.GET.get("page")),
            "filtro": filtro,
            "resumo": resumo,
        },
    )


@login_required
@role_required(*ESTOQUE)
@require_POST
def alerta_sla_producao_visualizar(request, pk):
    alerta = get_object_or_404(alertas_sla_para_usuario(request.user), pk=pk, usuario=request.user)
    if alerta.visualizado_em is None:
        alerta.visualizado_em = timezone.now()
        alerta.save(update_fields=["visualizado_em"])
        LogAuditoria.objects.create(
            usuario=request.user,
            modulo="estoque",
            acao="VISUALIZAR_ALERTA_SLA_ORDEM_PRODUCAO",
            descricao=f"Alerta de SLA da ordem #{alerta.ordem_id} marcado como visualizado.",
            objeto_tipo="AlertaSLAOrdemProducao",
            objeto_id=str(alerta.id),
            ip=request.META.get("REMOTE_ADDR"),
        )
        messages.success(request, "Alerta marcado como visualizado.")
    return redirect("estoque:alertas_sla_producao")


def _ordens_producao_composicao_filtradas(request):
    queryset = ordens_producao_para_usuario(
        request.user,
        OrdemProducaoComposicao.objects.select_related(
            "composicao",
            "filial",
            "produto_final",
            "usuario",
            "responsavel_operacional",
            "producao_gerada",
        ).prefetch_related("historico_etapas"),
    )
    termo = (request.GET.get("q") or "").strip()
    status = request.GET.get("status")
    prioridade = request.GET.get("prioridade")
    etapa = request.GET.get("etapa")
    setor = (request.GET.get("setor") or "").strip()
    responsavel = request.GET.get("responsavel")
    data_inicio = request.GET.get("inicio")
    data_fim = request.GET.get("fim")
    if termo:
        queryset = queryset.filter(
            Q(produto_final__nome__icontains=termo)
            | Q(produto_final__codigo_barras__icontains=termo)
            | Q(motivo__icontains=termo)
            | Q(setor_responsavel__icontains=termo)
            | Q(responsavel_operacional__username__icontains=termo)
            | Q(responsavel_operacional__first_name__icontains=termo)
            | Q(responsavel_operacional__last_name__icontains=termo)
        )
    if status:
        queryset = queryset.filter(status=status)
    if prioridade:
        queryset = queryset.filter(prioridade=prioridade)
    if etapa:
        queryset = queryset.filter(etapa_operacional=etapa)
    if setor:
        queryset = queryset.filter(setor_responsavel__icontains=setor)
    if responsavel:
        queryset = queryset.filter(responsavel_operacional_id=responsavel)
    if data_inicio:
        queryset = queryset.filter(data_programada__gte=data_inicio)
    if data_fim:
        queryset = queryset.filter(data_programada__lte=data_fim)
    return queryset.annotate(
        prioridade_ordem=Case(
            When(prioridade="URGENTE", then=Value(0)),
            When(prioridade="ALTA", then=Value(1)),
            When(prioridade="NORMAL", then=Value(2)),
            default=Value(3),
            output_field=IntegerField(),
        )
    ).order_by("data_programada", "prioridade_ordem", "produto_final__nome")


def _marcar_ultimo_apontamento(ordens):
    agora = timezone.localtime()
    metas = _metas_sla_setor_producao(ordens)
    for ordem in ordens:
        historicos = list(ordem.historico_etapas.all())
        ordem.ultimo_apontamento_etapa = historicos[0] if historicos else None
        inicio_etapa = ordem.ultimo_apontamento_etapa.criado_em if ordem.ultimo_apontamento_etapa else ordem.criado_em
        duracao = agora - timezone.localtime(inicio_etapa)
        minutos = max(int(duracao.total_seconds() // 60), 0)
        ordem.tempo_etapa_minutos = minutos
        ordem.tempo_etapa_atual = _formatar_duracao_minutos(minutos)
        setor = ordem.setor_responsavel or "Sem setor"
        ordem.sla_meta_minutos = _meta_sla_para_ordem(ordem, setor, metas)
        ordem.sla_meta_label = _formatar_duracao_minutos(ordem.sla_meta_minutos)
        ordem.sla_estourado = minutos > ordem.sla_meta_minutos
        ordem.sla_atraso_minutos = max(minutos - ordem.sla_meta_minutos, 0)
        ordem.sla_atraso_label = _formatar_duracao_minutos(ordem.sla_atraso_minutos)
    return ordens


def _registrar_alertas_sla_producao(ordens):
    ordens_estouradas = [ordem for ordem in ordens if getattr(ordem, "sla_estourado", False)]
    if not ordens_estouradas:
        return []
    filiais = {ordem.filial_id for ordem in ordens_estouradas if ordem.filial_id}
    perfis_supervisao = PerfilUsuario.objects.select_related("usuario").filter(
        is_active=True,
        filial_id__in=filiais,
        tipo__in=[TipoPerfil.ADMINISTRADOR, TipoPerfil.GERENTE],
    )
    usuarios_supervisao_por_filial = {}
    for perfil in perfis_supervisao:
        usuarios_supervisao_por_filial.setdefault(perfil.filial_id, []).append(perfil.usuario)
    alertas_criados = []
    for ordem in ordens_estouradas:
        mensagem = (
            f"Ordem #{ordem.id} fora do SLA em {ordem.setor_responsavel or 'Sem setor'} "
            f"ha {ordem.sla_atraso_label}."
        )
        destinatarios = []
        if ordem.responsavel_operacional_id:
            destinatarios.append((ordem.responsavel_operacional, "RESPONSAVEL"))
        for usuario in usuarios_supervisao_por_filial.get(ordem.filial_id, []):
            destinatarios.append((usuario, "SUPERVISAO"))
        vistos = set()
        for usuario, papel in destinatarios:
            chave = (usuario.id, papel)
            if chave in vistos:
                continue
            vistos.add(chave)
            alerta, criado = AlertaSLAOrdemProducao.objects.get_or_create(
                ordem=ordem,
                usuario=usuario,
                papel=papel,
                defaults={"mensagem": mensagem},
            )
            if criado:
                alertas_criados.append(alerta)
                LogAuditoria.objects.create(
                    usuario=usuario,
                    acao="ALERTA_SLA_ORDEM_PRODUCAO",
                    descricao=mensagem,
                    objeto_tipo="OrdemProducaoComposicao",
                    objeto_id=str(ordem.id),
                )
    return alertas_criados


@login_required
@role_required(*ESTOQUE)
def ordens_producao_composicao_csv(request):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="ordens_producao_composicao.csv"'
    response.write("\ufeff")
    writer = csv.writer(response, delimiter=";")
    writer.writerow(
        [
            "ID",
            "Data programada",
            "Empresa",
            "Filial",
            "Produto final",
            "Código produto final",
            "Quantidade planejada",
            "Prioridade",
            "Setor",
            "Etapa",
            "Responsavel operacional",
            "Status",
            "Criado por",
            "Motivo",
            "Produção gerada",
            "Criada em",
            "Concluida em",
            "Tempo na etapa",
            "Meta SLA",
            "Status SLA",
            "Atraso SLA",
        ]
    )
    ordens = list(_ordens_producao_composicao_filtradas(request))
    _marcar_ultimo_apontamento(ordens)
    for ordem in ordens:
        writer.writerow(
            [
                ordem.id,
                ordem.data_programada.strftime("%d/%m/%Y"),
                ordem.empresa.nome_fantasia or ordem.empresa.razao_social,
                ordem.filial.nome,
                ordem.produto_final.nome,
                ordem.produto_final.codigo_barras,
                ordem.quantidade_planejada,
                ordem.get_prioridade_display(),
                ordem.setor_responsavel,
                ordem.get_etapa_operacional_display(),
                ordem.responsavel_operacional.username if ordem.responsavel_operacional else "",
                ordem.get_status_display(),
                ordem.usuario.username,
                ordem.motivo,
                ordem.producao_gerada_id or "",
                ordem.criado_em.strftime("%d/%m/%Y %H:%M"),
                ordem.concluido_em.strftime("%d/%m/%Y %H:%M") if ordem.concluido_em else "",
                ordem.tempo_etapa_atual,
                ordem.sla_meta_label,
                "Fora do SLA" if ordem.sla_estourado else "Dentro do SLA",
                ordem.sla_atraso_label if ordem.sla_estourado else "",
            ]
        )
    return response


@login_required
@role_required(*ESTOQUE)
def ordens_producao_composicao_fila(request):
    hoje = timezone.localdate()
    modo = request.GET.get("modo") or "dia"
    setor = (request.GET.get("setor") or "").strip()
    etapa = request.GET.get("etapa")
    responsavel = request.GET.get("responsavel")
    sla = request.GET.get("sla")
    queryset = ordens_producao_para_usuario(
        request.user,
        OrdemProducaoComposicao.objects.select_related(
            "filial",
            "produto_final",
            "usuario",
            "responsavel_operacional",
        ).prefetch_related("historico_etapas").filter(status=StatusOrdemProducaoComposicao.PLANEJADA),
    )
    if modo == "dia":
        queryset = queryset.filter(data_programada__lte=hoje)
    if setor:
        queryset = queryset.filter(setor_responsavel__icontains=setor)
    if etapa:
        queryset = queryset.filter(etapa_operacional=etapa)
    if responsavel:
        queryset = queryset.filter(responsavel_operacional_id=responsavel)
    ordens = list(
        queryset.annotate(
            prioridade_ordem=Case(
                When(prioridade="URGENTE", then=Value(0)),
                When(prioridade="ALTA", then=Value(1)),
                When(prioridade="NORMAL", then=Value(2)),
                default=Value(3),
                output_field=IntegerField(),
            )
        ).order_by("setor_responsavel", "data_programada", "prioridade_ordem", "produto_final__nome")
    )
    _marcar_ultimo_apontamento(ordens)
    if sla == "fora":
        ordens = [ordem for ordem in ordens if ordem.sla_estourado]
    alertas_sla_criados = _registrar_alertas_sla_producao(ordens)
    alertas_sla_recentes = AlertaSLAOrdemProducao.objects.select_related(
        "ordem",
        "ordem__produto_final",
        "usuario",
    ).filter(ordem__in=ordens).order_by("-criado_em")[:12]
    grupos = OrderedDict()
    responsaveis_resumo = OrderedDict()
    for ordem in ordens:
        nome_setor = ordem.setor_responsavel or "Sem setor"
        if nome_setor not in grupos:
            grupos[nome_setor] = {
                "setor": nome_setor,
                "ordens": [],
                "total": 0,
                "quantidade": Decimal("0.000"),
                "atrasadas": 0,
                "urgentes": 0,
                "sla_estouradas": 0,
                "maior_tempo_minutos": 0,
                "maior_tempo_label": "0 min",
                "ordem_gargalo": None,
                "etapas": OrderedDict(),
            }
        grupo = grupos[nome_setor]
        grupo["ordens"].append(ordem)
        grupo["total"] += 1
        grupo["quantidade"] += ordem.quantidade_planejada
        if ordem.data_programada < hoje:
            grupo["atrasadas"] += 1
        if ordem.prioridade == "URGENTE":
            grupo["urgentes"] += 1
        if ordem.sla_estourado:
            grupo["sla_estouradas"] += 1
        if ordem.tempo_etapa_minutos >= grupo["maior_tempo_minutos"]:
            grupo["maior_tempo_minutos"] = ordem.tempo_etapa_minutos
            grupo["maior_tempo_label"] = ordem.tempo_etapa_atual
            grupo["ordem_gargalo"] = ordem
        etapa_label = ordem.get_etapa_operacional_display()
        grupo["etapas"][etapa_label] = grupo["etapas"].get(etapa_label, 0) + 1

        responsavel_id = ordem.responsavel_operacional_id or 0
        responsavel_nome = ordem.responsavel_operacional.username if ordem.responsavel_operacional else "Sem responsavel"
        if responsavel_id not in responsaveis_resumo:
            responsaveis_resumo[responsavel_id] = {
                "usuario_id": ordem.responsavel_operacional_id,
                "nome": responsavel_nome,
                "total": 0,
                "quantidade": Decimal("0.000"),
                "atrasadas": 0,
                "urgentes": 0,
                "sla_estouradas": 0,
                "setores": OrderedDict(),
                "maior_tempo_minutos": 0,
                "maior_tempo_label": "0 min",
                "ordem_gargalo": None,
            }
        resumo = responsaveis_resumo[responsavel_id]
        resumo["total"] += 1
        resumo["quantidade"] += ordem.quantidade_planejada
        resumo["setores"][nome_setor] = True
        if ordem.data_programada < hoje:
            resumo["atrasadas"] += 1
        if ordem.prioridade == "URGENTE":
            resumo["urgentes"] += 1
        if ordem.sla_estourado:
            resumo["sla_estouradas"] += 1
        if ordem.tempo_etapa_minutos >= resumo["maior_tempo_minutos"]:
            resumo["maior_tempo_minutos"] = ordem.tempo_etapa_minutos
            resumo["maior_tempo_label"] = ordem.tempo_etapa_atual
            resumo["ordem_gargalo"] = ordem
    ordem_gargalo = max(ordens, key=lambda ordem: ordem.tempo_etapa_minutos, default=None)
    totais = {
        "ordens": len(ordens),
        "setores": len(grupos),
        "atrasadas": sum(1 for ordem in ordens if ordem.data_programada < hoje),
        "urgentes": sum(1 for ordem in ordens if ordem.prioridade == "URGENTE"),
        "sla_estouradas": sum(1 for ordem in ordens if ordem.sla_estourado),
        "quantidade": sum((ordem.quantidade_planejada for ordem in ordens), Decimal("0.000")),
        "maior_tempo_label": ordem_gargalo.tempo_etapa_atual if ordem_gargalo else "0 min",
        "gargalo_setor": (ordem_gargalo.setor_responsavel or "Sem setor") if ordem_gargalo else "-",
        "gargalo_ordem": ordem_gargalo,
    }
    return render(
        request,
        "estoque/ordem_producao_composicao_fila.html",
        {
            "grupos": grupos.values(),
            "responsaveis_resumo": sorted(
                responsaveis_resumo.values(),
                key=lambda item: (-item["maior_tempo_minutos"], -item["total"], item["nome"]),
            ),
            "alertas_sla_criados": alertas_sla_criados,
            "alertas_sla_recentes": alertas_sla_recentes,
            "totais": totais,
            "hoje": hoje,
            "modo": modo,
            "setor": setor,
            "etapa": etapa,
            "responsavel": responsavel,
            "sla": sla,
            "etapa_opcoes": OrdemProducaoComposicao._meta.get_field("etapa_operacional").choices,
            "responsaveis_opcoes": usuarios_para_usuario(
                request.user, get_user_model().objects.filter(is_active=True)
            ).order_by("username"),
        },
    )


@login_required
@role_required(*ESTOQUE)
def ordem_producao_composicao_imprimir(request, pk):
    ordem = get_object_or_404(
        ordens_producao_para_usuario(
            request.user,
            OrdemProducaoComposicao.objects.select_related(
                "composicao",
                "empresa",
                "filial",
                "produto_final",
                "usuario",
                "responsavel_operacional",
                "producao_gerada",
            ).prefetch_related("composicao__itens", "composicao__itens__produto_componente"),
        ),
        pk=pk,
    )
    fator = ordem.quantidade_planejada / ordem.composicao.quantidade_final
    componentes = [
        {
            "produto": item.produto_componente,
            "quantidade_receita": item.quantidade,
            "quantidade_prevista": item.quantidade * fator,
        }
        for item in ordem.composicao.itens.all()
    ]
    return render(
        request,
        "estoque/ordem_producao_composicao_impressao.html",
        {
            "ordem": ordem,
            "componentes": componentes,
        },
    )


@login_required
@role_required(*ESTOQUE)
def ordem_producao_composicao_etapa(request, pk):
    ordem = get_object_or_404(ordens_producao_para_usuario(request.user), pk=pk)
    if request.method != "POST":
        return redirect("estoque:ordens_producao_composicao")
    etapa = request.POST.get("etapa_operacional")
    etapas_validas = {valor for valor, _ in OrdemProducaoComposicao._meta.get_field("etapa_operacional").choices}
    if ordem.status != StatusOrdemProducaoComposicao.PLANEJADA:
        messages.error(request, "A etapa só pode ser alterada em ordens planejadas.")
    elif etapa not in etapas_validas:
        messages.error(request, "Etapa operacional inválida.")
    else:
        if ordem.etapa_operacional == etapa:
            messages.info(request, "A ordem já está nesta etapa.")
            return redirect("estoque:ordens_producao_composicao")
        etapa_anterior_codigo = ordem.etapa_operacional
        etapa_anterior = ordem.get_etapa_operacional_display()
        ordem.etapa_operacional = etapa
        ordem.save(update_fields=["etapa_operacional", "atualizado_em"])
        HistoricoEtapaOrdemProducaoComposicao.objects.create(
            ordem=ordem,
            etapa_anterior=etapa_anterior_codigo,
            etapa_nova=etapa,
            usuario=request.user,
            observacao=request.POST.get("observacao", "").strip(),
        )
        LogAuditoria.objects.create(
            usuario=request.user,
            modulo="estoque",
            acao="ORDEM_PRODUCAO_COMPOSICAO_ETAPA",
            descricao=f"Ordem de produção {ordem.id} alterada de {etapa_anterior} para {ordem.get_etapa_operacional_display()}.",
            objeto_tipo="OrdemProducaoComposicao",
            objeto_id=str(ordem.id),
            ip=request.META.get("REMOTE_ADDR"),
        )
        messages.success(request, "Etapa da ordem atualizada.")
    return redirect("estoque:ordens_producao_composicao")


@login_required
@role_required(*ESTOQUE)
def ordem_producao_composicao_nova(request):
    initial = {}
    composicao_id = request.GET.get("composicao")
    quantidade = request.GET.get("quantidade")
    if composicao_id:
        initial["composicao"] = composicao_id
        composicao = composicoes_para_usuario(
            request.user, ComposicaoProduto.objects.select_related("filial")
        ).filter(pk=composicao_id).first()
        if composicao and composicao.filial_id:
            initial["filial"] = composicao.filial_id
    if quantidade:
        initial["quantidade_planejada"] = quantidade
    form = OrdemProducaoComposicaoForm(request.POST or None, initial=initial, user=request.user)
    if request.method == "POST" and form.is_valid():
        ordem = form.save(commit=False)
        ordem.empresa = ordem.filial.empresa
        ordem.produto_final = ordem.composicao.produto_final
        ordem.usuario = request.user
        ordem.full_clean()
        ordem.save()
        LogAuditoria.objects.create(
            usuario=request.user,
            modulo="estoque",
            acao="ORDEM_PRODUCAO_COMPOSICAO_CRIADA",
            descricao=f"Ordem de produção {ordem.id} criada para {ordem.quantidade_planejada} de {ordem.produto_final}.",
            objeto_tipo="OrdemProducaoComposicao",
            objeto_id=str(ordem.id),
            ip=request.META.get("REMOTE_ADDR"),
        )
        messages.success(request, "Ordem de produção criada com sucesso.")
        return redirect("estoque:ordens_producao_composicao")
    return render(request, "estoque/ordem_producao_composicao_form.html", {"form": form})


@login_required
@role_required(*ESTOQUE)
def ordem_producao_composicao_confirmar(request, pk):
    ordem = get_object_or_404(ordens_producao_para_usuario(request.user), pk=pk)
    if request.method != "POST":
        return redirect("estoque:ordens_producao_composicao")
    try:
        supervisor = supervisor_from_request(request, acao=AcaoPinSupervisor.ESTOQUE_AJUSTE)
        confirmar_ordem_producao_composicao(
            ordem=ordem,
            usuario=request.user,
            codigo_lote=request.POST.get("codigo_lote", "").strip(),
            fabricacao=request.POST.get("fabricacao") or None,
            validade=request.POST.get("validade") or None,
            supervisor=supervisor,
            ip=request.META.get("REMOTE_ADDR"),
        )
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(request, "Ordem produzida e estoque atualizado.")
    return redirect("estoque:ordens_producao_composicao")


@login_required
@role_required(*ESTOQUE)
def ordem_producao_composicao_cancelar(request, pk):
    ordem = get_object_or_404(ordens_producao_para_usuario(request.user), pk=pk)
    if request.method != "POST":
        return redirect("estoque:ordens_producao_composicao")
    try:
        supervisor = supervisor_from_request(request, acao=AcaoPinSupervisor.ESTOQUE_CANCELAR)
        cancelar_ordem_producao_composicao(
            ordem=ordem,
            usuario=request.user,
            motivo=request.POST.get("motivo", "").strip(),
            supervisor=supervisor,
            ip=request.META.get("REMOTE_ADDR"),
        )
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(request, "Ordem de produção cancelada.")
    return redirect("estoque:ordens_producao_composicao")


def _salvar_composicao_com_itens(request, composicao=None):
    form = ComposicaoProdutoForm(request.POST or None, instance=composicao, user=request.user)
    formset = ItemComposicaoProdutoFormSet(request.POST or None, instance=composicao, prefix="componentes")
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        composicao = form.save()
        formset.instance = composicao
        formset.save()
        messages.success(request, "Composição salva com sucesso.")
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
    objeto = get_object_or_404(composicoes_para_usuario(request.user), pk=pk)
    composicao, form, formset = _salvar_composicao_com_itens(request, objeto)
    if composicao:
        return redirect("estoque:composicao_detalhe", pk=composicao.pk)
    return render(request, "estoque/composicao_form.html", {"form": form, "formset": formset, "object": objeto})


@login_required
@role_required(*ESTOQUE)
def composicao_detalhe(request, pk):
    composicao = get_object_or_404(
        composicoes_para_usuario(
            request.user,
            ComposicaoProduto.objects.select_related("empresa", "filial", "produto_final").prefetch_related(
                "itens__produto_componente",
                "producoes__filial",
                "producoes__usuario",
            ),
        ),
        pk=pk,
    )
    resumo_visual = _resumo_visual_composicao(composicao)
    inicial_producao = {}
    quantidade_planejada = (request.GET.get("quantidade") or "").strip()
    if quantidade_planejada:
        try:
            quantidade_planejada_decimal = Decimal(quantidade_planejada.replace(",", "."))
        except (InvalidOperation, ValueError):
            quantidade_planejada_decimal = None
        if quantidade_planejada_decimal and quantidade_planejada_decimal > 0:
            quantidade_preenchida = min(quantidade_planejada_decimal, resumo_visual["capacidade_maxima"])
            inicial_producao["quantidade_final"] = quantidade_preenchida
            if resumo_visual["producao_sugerida"] and quantidade_preenchida == resumo_visual["producao_sugerida"]:
                inicial_producao["motivo"] = "Reposição até estoque mínimo"
            else:
                inicial_producao["motivo"] = "Produção pela capacidade disponível"
    producao_form = ProducaoComposicaoForm(initial=inicial_producao, composicao=composicao, user=request.user)
    producoes = composicao.producoes.select_related("filial", "usuario").order_by("-criado_em")[:20]
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
    composicao = get_object_or_404(composicoes_para_usuario(request.user), pk=pk)
    if request.method != "POST":
        return redirect("estoque:composicao_detalhe", pk=composicao.pk)
    form = ProducaoComposicaoForm(request.POST, composicao=composicao, user=request.user)
    if form.is_valid():
        try:
            supervisor = supervisor_from_request(request, acao=AcaoPinSupervisor.ESTOQUE_AJUSTE)
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
        messages.error(request, "Confira os dados da produção.")
    return redirect("estoque:composicao_detalhe", pk=composicao.pk)


@login_required
@role_required(*ESTOQUE)
def composicao_cancelar_producao(request, pk):
    producao = get_object_or_404(
        producoes_composicao_para_usuario(
            request.user, ProducaoComposicaoProduto.objects.select_related("composicao")
        ),
        pk=pk,
    )
    if request.method != "POST":
        return redirect("estoque:composicao_detalhe", pk=producao.composicao_id)
    try:
        supervisor = supervisor_from_request(request, acao=AcaoPinSupervisor.ESTOQUE_CANCELAR)
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
        messages.success(request, "Produção cancelada e estoque revertido.")
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
            "Código origem",
            "Qtd origem",
            "Produto destino",
            "Código destino",
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
    queryset = itens_desmembramento_para_usuario(
        request.user,
        ItemDesmembramentoProduto.objects.select_related(
            "desmembramento",
            "desmembramento__filial",
            "desmembramento__empresa",
            "desmembramento__produto_origem",
            "desmembramento__usuario",
            "produto_destino",
        ),
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
        "itens": Paginator(itens, 50).get_page(request.GET.get("page")),
        "total_quantidade": totais["quantidade_gerada"] or 0,
        "total_custo": totais["custo_total"] or 0,
        "total_operacoes": totais["operacoes"] or 0,
        "total_alertas": total_alertas,
        "graficos_rendimento": graficos,
        "filiais": filiais_para_usuario(request.user, Filial.objects.filter(is_active=True)).order_by("nome"),
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
        base_qs.filter(
            Q(codigo_barras__iexact=termo)
            | Q(codigo_interno__iexact=termo)
            | Q(codigos_adicionais__codigo__iexact=termo)
        ).distinct().select_related(
            "categoria", "marca"
        )[:10]
    )
    parciais = list(
        base_qs.filter(
            Q(codigo_barras__icontains=termo)
            | Q(codigo_interno__icontains=termo)
            | Q(codigos_adicionais__codigo__icontains=termo)
            | Q(nome__icontains=termo)
        )
        .exclude(pk__in=[produto.pk for produto in exatos])
        .distinct()
        .select_related("categoria", "marca")
        .order_by("nome")[:20]
    )
    return JsonResponse({"results": [_produto_busca_payload(produto) for produto in exatos + parciais]})


@login_required
@role_required(*ESTOQUE)
@require_GET
def receita_desmembramento_json(request, pk):
    receita = get_object_or_404(
        receitas_desmembramento_para_usuario(
            request.user,
            ReceitaDesmembramento.objects.select_related("empresa", "filial", "produto_origem", "produto_destino"),
        ),
        pk=pk,
        is_active=True,
    )
    return JsonResponse({"status": "ok", "receita": _receita_payload(receita)})


def _destino_formset_initial(user, receita_id=None):
    if not receita_id:
        return [{"tipo_saida_destino": "VENDAVEL"}]
    try:
        receita = receitas_desmembramento_para_usuario(user).get(pk=receita_id, is_active=True)
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
        form = DesmembramentoProdutoForm(request.POST, user=request.user)
        destino_formset = DesmembramentoDestinoFormSet(request.POST, prefix="destinos")
        if form.is_valid() and destino_formset.is_valid():
            dados = form.cleaned_data.copy()
            dados.pop("receita", None)
            try:
                destinos = _destinos_from_formset(destino_formset, dados["produto_origem"])
                if request.POST.get("acao") == "simular":
                    previa = simular_desmembramento_multidestino(destinos=destinos, **dados)
                else:
                    supervisor = supervisor_from_request(request, acao=AcaoPinSupervisor.ESTOQUE_AJUSTE)
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
        form = DesmembramentoProdutoForm(initial={"receita": receita_id}, user=request.user)
        destino_formset = DesmembramentoDestinoFormSet(initial=_destino_formset_initial(request.user, receita_id), prefix="destinos")
    return render(
        request,
        "estoque/desmembramento_form.html",
        {"form": form, "destino_formset": destino_formset, "previa": previa},
    )


@login_required
@role_required(*ESTOQUE)
def desmembramento_detalhe(request, pk):
    desmembramento = get_object_or_404(
        desmembramentos_para_usuario(
            request.user,
            DesmembramentoProduto.objects.select_related("filial", "empresa", "produto_origem", "usuario").prefetch_related(
                "itens__produto_destino"
            ),
        ),
        pk=pk,
    )
    return render(request, "estoque/desmembramento_detalhe.html", {"desmembramento": desmembramento})


@login_required
@role_required(*ESTOQUE)
def desmembramento_cancelar(request, pk):
    desmembramento = get_object_or_404(desmembramentos_para_usuario(request.user), pk=pk)
    if request.method != "POST":
        return redirect("estoque:desmembramento_detalhe", pk=desmembramento.pk)
    try:
        supervisor = supervisor_from_request(request, acao=AcaoPinSupervisor.ESTOQUE_CANCELAR)
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
