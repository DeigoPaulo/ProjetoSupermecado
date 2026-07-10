import csv
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.generic import DetailView, ListView
from django.views.generic.base import TemplateResponseMixin
from django.views.generic.edit import ModelFormMixin, ProcessFormView

from apps.accounts.permissions import COMPRAS, RoleRequiredMixin, role_required, supervisor_from_request
from apps.estoque.models import Estoque, MovimentacaoEstoque
from apps.financeiro.models import ContaFinanceira, StatusContaFinanceira

from .forms import EntradaCompraForm, ItemEntradaCompraFormSet
from .models import EntradaCompra, StatusEntradaCompra
from .services import cancelar_entrada_compra, finalizar_entrada_compra


FINANCEIRO_CHOICES = [
    ("ABERTA", "Conta aberta"),
    ("PAGA", "Conta paga"),
    ("CANCELADA", "Conta cancelada"),
    ("VENCIDA", "Conta vencida"),
    ("SEM_CONTA", "Sem conta financeira"),
]


def entradas_filtradas(params):
    queryset = EntradaCompra.objects.select_related("fornecedor", "filial", "usuario").prefetch_related("contas_financeiras").order_by("-data_recebimento")
    termo = (params.get("q") or "").strip()
    if termo:
        queryset = queryset.filter(Q(numero_documento__icontains=termo) | Q(fornecedor__razao_social__icontains=termo) | Q(fornecedor__nome_fantasia__icontains=termo))
    status = (params.get("status") or "").strip()
    if status:
        queryset = queryset.filter(status=status)
    financeiro = (params.get("financeiro") or "").strip()
    if financeiro == "SEM_CONTA":
        queryset = queryset.filter(contas_financeiras__isnull=True)
    elif financeiro == "VENCIDA":
        queryset = queryset.filter(contas_financeiras__status=StatusContaFinanceira.ABERTA, contas_financeiras__vencimento__lt=timezone.localdate())
    elif financeiro in dict(FINANCEIRO_CHOICES):
        queryset = queryset.filter(contas_financeiras__status=financeiro)
    return queryset.distinct()


class EntradaCompraListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    required_roles = COMPRAS
    model = EntradaCompra
    template_name = "compras/entrada_list.html"
    context_object_name = "entradas"
    paginate_by = 25
    financeiro_choices = FINANCEIRO_CHOICES

    def _url_financeiro(self, financeiro):
        params = self.request.GET.copy()
        params["financeiro"] = financeiro
        return f"?{params.urlencode()}"

    def get_queryset(self):
        return entradas_filtradas(self.request.GET)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        base_queryset = EntradaCompra.objects.all()
        por_status = {
            item["status"]: item
            for item in base_queryset.values("status").annotate(quantidade=Count("id"), total=Sum("total_produtos"))
        }
        context["resumo_compras"] = {
            "total": sum(item["quantidade"] for item in por_status.values()),
            "rascunhos": por_status.get(StatusEntradaCompra.RASCUNHO, {}).get("quantidade", 0),
            "finalizadas": por_status.get(StatusEntradaCompra.FINALIZADA, {}).get("quantidade", 0),
            "total_finalizado": por_status.get(StatusEntradaCompra.FINALIZADA, {}).get("total") or 0,
        }
        hoje = timezone.localdate()
        contas_compra = ContaFinanceira.objects.filter(entrada_compra__isnull=False)
        contas_abertas = contas_compra.filter(status=StatusContaFinanceira.ABERTA)
        context["resumo_financeiro_compras"] = {
            "abertas": contas_abertas.count(),
            "total_aberto": contas_abertas.aggregate(total=Sum("valor"))["total"] or 0,
            "url_abertas": self._url_financeiro("ABERTA"),
            "vencidas": contas_abertas.filter(vencimento__lt=hoje).count(),
            "total_vencido": contas_abertas.filter(vencimento__lt=hoje).aggregate(total=Sum("valor"))["total"] or 0,
            "url_vencidas": self._url_financeiro("VENCIDA"),
            "pagas": contas_compra.filter(status=StatusContaFinanceira.PAGA).count(),
            "total_pago": contas_compra.filter(status=StatusContaFinanceira.PAGA).aggregate(total=Sum("valor_pago"))["total"] or 0,
            "url_pagas": self._url_financeiro("PAGA"),
        }
        context["status_choices"] = StatusEntradaCompra.choices
        context["financeiro_choices"] = self.financeiro_choices
        context["filtros_ativos"] = any((self.request.GET.get("q"), self.request.GET.get("status"), self.request.GET.get("financeiro")))
        status_labels = dict(StatusEntradaCompra.choices)
        financeiro_labels = dict(self.financeiro_choices)
        filtros_aplicados = []
        if self.request.GET.get("q"):
            filtros_aplicados.append(("Busca", self.request.GET.get("q")))
        if self.request.GET.get("status"):
            filtros_aplicados.append(("Status", status_labels.get(self.request.GET.get("status"), self.request.GET.get("status"))))
        if self.request.GET.get("financeiro"):
            filtros_aplicados.append(("Financeiro", financeiro_labels.get(self.request.GET.get("financeiro"), self.request.GET.get("financeiro"))))
        context["filtros_aplicados"] = filtros_aplicados
        return context


@login_required
@role_required(*COMPRAS)
def entradas_csv(request):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="compras_operacionais.csv"'
    response.write("\ufeff")
    writer = csv.writer(response, delimiter=";")
    writer.writerow([
        "ID",
        "Recebimento",
        "Fornecedor",
        "Filial",
        "Documento",
        "Total",
        "Status entrada",
        "Status financeiro",
        "Vencimento financeiro",
        "Data pagamento",
        "Valor financeiro",
        "Valor pago",
    ])
    for entrada in entradas_filtradas(request.GET):
        contas = list(entrada.contas_financeiras.all())
        status_financeiro = ", ".join(conta.get_status_display() for conta in contas) or "Sem conta"
        vencimentos = ", ".join(conta.vencimento.strftime("%d/%m/%Y") for conta in contas if conta.vencimento)
        pagamentos = ", ".join(conta.data_pagamento.strftime("%d/%m/%Y") for conta in contas if conta.data_pagamento)
        valor_financeiro = sum((conta.valor for conta in contas), 0)
        valor_pago = sum((conta.valor_pago or 0 for conta in contas), 0)
        writer.writerow([
            entrada.id,
            timezone.localtime(entrada.data_recebimento).strftime("%d/%m/%Y %H:%M"),
            entrada.fornecedor,
            entrada.filial,
            entrada.numero_documento,
            str(entrada.total_produtos).replace(".", ","),
            entrada.get_status_display(),
            status_financeiro,
            vencimentos,
            pagamentos,
            str(valor_financeiro).replace(".", ","),
            str(valor_pago).replace(".", ","),
        ])
    return response


@login_required
@role_required(*COMPRAS)
def entradas_imprimir(request):
    entradas = list(entradas_filtradas(request.GET))
    total_entradas = len(entradas)
    total_compras = sum((entrada.total_produtos for entrada in entradas), 0)
    total_financeiro = sum((conta.valor for entrada in entradas for conta in entrada.contas_financeiras.all()), 0)
    total_pago = sum((conta.valor_pago or 0 for entrada in entradas for conta in entrada.contas_financeiras.all()), 0)
    return render(request, "compras/entrada_imprimir.html", {
        "entradas": entradas,
        "total_entradas": total_entradas,
        "total_compras": total_compras,
        "total_financeiro": total_financeiro,
        "total_pago": total_pago,
        "gerado_em": timezone.localtime(),
        "filtros": {
            "q": request.GET.get("q", ""),
            "status": request.GET.get("status", ""),
            "financeiro": request.GET.get("financeiro", ""),
        },
    })


@login_required
@role_required(*COMPRAS)
def entrada_imprimir(request, pk):
    entrada = get_object_or_404(
        EntradaCompra.objects.select_related("fornecedor", "filial", "usuario").prefetch_related(
            "itens__produto",
            "contas_financeiras__lancamentos__conta",
            "contas_financeiras__lancamentos__usuario",
        ),
        pk=pk,
    )
    movimentacoes = MovimentacaoEstoque.objects.select_related("produto", "usuario").filter(
        filial=entrada.filial,
        referencia__in=[f"entrada_compra:{entrada.id}", f"entrada_compra_cancelamento:{entrada.id}"],
    ).order_by("data", "id")
    return render(request, "compras/entrada_detalhe_imprimir.html", {
        "entrada": entrada,
        "movimentacoes_estoque": movimentacoes,
        "gerado_em": timezone.localtime(),
    })


class EntradaCompraDetailView(LoginRequiredMixin, RoleRequiredMixin, DetailView):
    required_roles = COMPRAS
    model = EntradaCompra
    template_name = "compras/entrada_detalhe.html"
    context_object_name = "entrada"

    def get_queryset(self):
        return EntradaCompra.objects.select_related("fornecedor", "filial", "usuario").prefetch_related(
            "itens__produto",
            "contas_financeiras__lancamentos__conta",
            "contas_financeiras__lancamentos__usuario",
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        entrada = self.object
        retorno_lista = self.request.GET.get("next") or reverse("compras:lista")
        if not url_has_allowed_host_and_scheme(retorno_lista, allowed_hosts={self.request.get_host()}):
            retorno_lista = reverse("compras:lista")
        context["retorno_lista_url"] = retorno_lista
        bloqueios_cancelamento = []
        if entrada.status == StatusEntradaCompra.FINALIZADA:
            if entrada.contas_financeiras.filter(status=StatusContaFinanceira.PAGA).exists():
                bloqueios_cancelamento.append("A conta financeira vinculada ja foi paga.")
            for item in entrada.itens.all():
                estoque = Estoque.objects.filter(produto=item.produto, filial=entrada.filial).first()
                saldo = estoque.quantidade_disponivel if estoque else 0
                if saldo < item.quantidade:
                    bloqueios_cancelamento.append(
                        f"Saldo insuficiente para reverter {item.produto}: disponivel {saldo}, necessario {item.quantidade}."
                    )
        context["bloqueios_cancelamento"] = bloqueios_cancelamento
        context["pode_cancelar_entrada"] = entrada.status == StatusEntradaCompra.FINALIZADA and not bloqueios_cancelamento
        context["movimentacoes_estoque"] = MovimentacaoEstoque.objects.select_related("produto", "usuario").filter(
            filial=entrada.filial,
            referencia__in=[f"entrada_compra:{entrada.id}", f"entrada_compra_cancelamento:{entrada.id}"],
        ).order_by("data", "id")
        return context


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

    def get_retorno_lista_url(self):
        retorno = self.request.POST.get("next") or self.request.GET.get("next") or ""
        if retorno and url_has_allowed_host_and_scheme(retorno, allowed_hosts={self.request.get_host()}):
            return retorno
        return ""

    def get_success_url(self):
        url = reverse("compras:detalhe", args=[self.object.pk])
        retorno = self.get_retorno_lista_url()
        if retorno:
            url = f"{url}?{urlencode({'next': retorno})}"
        return url

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.method == "POST":
            context["formset"] = ItemEntradaCompraFormSet(self.request.POST, instance=self.object)
        else:
            context["formset"] = ItemEntradaCompraFormSet(instance=self.object)
        context["retorno_lista_url"] = self.get_retorno_lista_url()
        return context

    def form_valid(self, form):
        context = self.get_context_data(form=form)
        formset = context["formset"]
        if not formset.is_valid():
            return self.form_invalid(form)
        finalizar_agora = self.request.POST.get("acao") == "finalizar"

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

        if finalizar_agora:
            try:
                supervisor = supervisor_from_request(self.request)
                finalizar_entrada_compra(self.object, supervisor=supervisor, ip=self.request.META.get("REMOTE_ADDR"))
            except ValidationError as exc:
                messages.error(self.request, "Entrada salva como rascunho. " + " ".join(exc.messages))
                return redirect(self.get_success_url())
            messages.success(self.request, "Entrada finalizada e estoque atualizado.")
            return redirect(self.get_success_url())

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


@login_required
@role_required(*COMPRAS)
def cancelar_entrada(request, pk):
    entrada = get_object_or_404(EntradaCompra.objects.prefetch_related("itens__produto", "contas_financeiras"), pk=pk)
    if request.method != "POST":
        return redirect("compras:detalhe", pk=entrada.pk)

    try:
        supervisor = supervisor_from_request(request)
        cancelar_entrada_compra(
            entrada,
            usuario=request.user,
            motivo=request.POST.get("motivo", ""),
            supervisor=supervisor,
            ip=request.META.get("REMOTE_ADDR"),
        )
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(request, "Entrada cancelada, estoque revertido e financeiro ajustado.")

    return redirect("compras:detalhe", pk=entrada.pk)

# Create your views here.
