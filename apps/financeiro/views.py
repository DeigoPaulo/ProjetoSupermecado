import csv
from collections import OrderedDict
from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date

from apps.accounts.permissions import RELATORIOS, SISTEMA, role_required
from apps.vendas.models import PagamentoVenda, StatusVenda

from .forms import BaixaContaForm, CategoriaFinanceiraForm, ContaFinanceiraForm
from .models import CategoriaFinanceira, ContaFinanceira, StatusContaFinanceira, TipoContaFinanceira
from .services import baixar_conta, cancelar_conta


def _periodo_from_request(request):
    hoje = timezone.localdate()
    data_inicio = parse_date(request.GET.get("data_inicio") or "") or hoje.replace(day=1)
    data_fim = parse_date(request.GET.get("data_fim") or "") or hoje
    return data_inicio, data_fim


def _contas_filtradas(request):
    data_inicio, data_fim = _periodo_from_request(request)
    tipo = request.GET.get("tipo", "")
    status = request.GET.get("status", "")
    q = request.GET.get("q", "").strip()
    contas_qs = ContaFinanceira.objects.select_related("categoria", "filial", "fornecedor", "cliente").filter(
        vencimento__gte=data_inicio,
        vencimento__lte=data_fim,
    )
    if tipo:
        contas_qs = contas_qs.filter(tipo=tipo)
    if status:
        contas_qs = contas_qs.filter(status=status)
    if q:
        contas_qs = contas_qs.filter(descricao__icontains=q)
    return contas_qs, {"data_inicio": data_inicio, "data_fim": data_fim, "tipo": tipo, "status": status, "q": q}


def _resumo_contas(contas_qs):
    resumo_abertas = contas_qs.filter(status=StatusContaFinanceira.ABERTA)
    total_pagar = resumo_abertas.filter(tipo=TipoContaFinanceira.PAGAR).aggregate(total=Sum("valor"))["total"] or 0
    total_receber = resumo_abertas.filter(tipo=TipoContaFinanceira.RECEBER).aggregate(total=Sum("valor"))["total"] or 0
    total_pago = contas_qs.filter(status=StatusContaFinanceira.PAGA).aggregate(total=Sum("valor_pago"))["total"] or 0
    vencidas = sum(1 for conta in resumo_abertas if conta.esta_vencida)
    return {
        "total_pagar": total_pagar,
        "total_receber": total_receber,
        "saldo_previsto": total_receber - total_pagar,
        "total_pago": total_pago,
        "vencidas": vencidas,
        "total_contas": contas_qs.count(),
    }


def _parceiro(conta):
    return conta.fornecedor or conta.cliente or ""


def _fluxo_caixa_periodo(data_inicio, data_fim):
    contas_qs = ContaFinanceira.objects.filter(vencimento__gte=data_inicio, vencimento__lte=data_fim)
    fluxo = OrderedDict()
    dia = data_inicio
    while dia <= data_fim:
        fluxo[dia] = {
            "data": dia,
            "previsto_receber": Decimal("0.00"),
            "previsto_pagar": Decimal("0.00"),
            "realizado_receber": Decimal("0.00"),
            "realizado_pagar": Decimal("0.00"),
            "saldo_previsto": Decimal("0.00"),
            "saldo_realizado": Decimal("0.00"),
        }
        dia = dia + timedelta(days=1)

    for conta in contas_qs:
        linha = fluxo.get(conta.vencimento)
        if not linha:
            continue
        if conta.tipo == TipoContaFinanceira.RECEBER:
            linha["previsto_receber"] += conta.valor
            if conta.status == StatusContaFinanceira.PAGA:
                linha["realizado_receber"] += conta.valor_pago or Decimal("0.00")
        else:
            linha["previsto_pagar"] += conta.valor
            if conta.status == StatusContaFinanceira.PAGA:
                linha["realizado_pagar"] += conta.valor_pago or Decimal("0.00")

    for linha in fluxo.values():
        linha["saldo_previsto"] = linha["previsto_receber"] - linha["previsto_pagar"]
        linha["saldo_realizado"] = linha["realizado_receber"] - linha["realizado_pagar"]

    return list(fluxo.values())


def _conciliacao_periodo(data_inicio, data_fim):
    formas_prazo = {"CREDIARIO", "FIADO", "PRAZO"}
    linhas = OrderedDict()
    dia = data_inicio
    while dia <= data_fim:
        linhas[dia] = {
            "data": dia,
            "entradas_pdv": Decimal("0.00"),
            "recebimentos_financeiros": Decimal("0.00"),
            "saidas_financeiras": Decimal("0.00"),
            "saldo_operacional": Decimal("0.00"),
        }
        dia = dia + timedelta(days=1)

    pagamentos_pdv = PagamentoVenda.objects.select_related("venda", "forma_pagamento").filter(
        venda__status=StatusVenda.FINALIZADA,
        data__date__gte=data_inicio,
        data__date__lte=data_fim,
    )
    for pagamento in pagamentos_pdv:
        if pagamento.forma_pagamento.tipo in formas_prazo:
            continue
        data = timezone.localtime(pagamento.data).date()
        if data in linhas:
            linhas[data]["entradas_pdv"] += pagamento.valor

    contas_baixadas = ContaFinanceira.objects.filter(
        status=StatusContaFinanceira.PAGA,
        data_pagamento__gte=data_inicio,
        data_pagamento__lte=data_fim,
    )
    for conta in contas_baixadas:
        if conta.data_pagamento not in linhas:
            continue
        valor = conta.valor_pago or Decimal("0.00")
        if conta.tipo == TipoContaFinanceira.RECEBER:
            linhas[conta.data_pagamento]["recebimentos_financeiros"] += valor
        else:
            linhas[conta.data_pagamento]["saidas_financeiras"] += valor

    for linha in linhas.values():
        linha["saldo_operacional"] = linha["entradas_pdv"] + linha["recebimentos_financeiros"] - linha["saidas_financeiras"]

    return list(linhas.values())


@login_required
@role_required(*RELATORIOS)
def contas(request):
    contas_qs, filtros = _contas_filtradas(request)
    context = {
        **filtros,
        **_resumo_contas(contas_qs),
        "tipos": TipoContaFinanceira.choices,
        "status_choices": StatusContaFinanceira.choices,
        "contas": contas_qs[:200],
    }
    return render(request, "financeiro/contas.html", context)


@login_required
@role_required(*RELATORIOS)
def contas_csv(request):
    contas_qs, filtros = _contas_filtradas(request)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="financeiro_{filtros["data_inicio"]}_{filtros["data_fim"]}.csv"'
    response.write("\ufeff")
    writer = csv.writer(response, delimiter=";")
    writer.writerow(["Vencimento", "Tipo", "Descricao", "Categoria", "Filial", "Parceiro", "Status", "Valor", "Data pagamento", "Valor pago", "Forma"])
    for conta in contas_qs.iterator():
        writer.writerow([
            conta.vencimento.strftime("%d/%m/%Y"),
            conta.get_tipo_display(),
            conta.descricao,
            conta.categoria or "",
            conta.filial,
            _parceiro(conta),
            conta.get_status_display(),
            str(conta.valor).replace(".", ","),
            conta.data_pagamento.strftime("%d/%m/%Y") if conta.data_pagamento else "",
            str(conta.valor_pago).replace(".", ",") if conta.valor_pago is not None else "",
            conta.forma_pagamento,
        ])
    return response


@login_required
@role_required(*RELATORIOS)
def contas_imprimir(request):
    contas_qs, filtros = _contas_filtradas(request)
    resumo = _resumo_contas(contas_qs)
    return render(request, "financeiro/contas_imprimir.html", {
        **filtros,
        **resumo,
        "contas": contas_qs,
        "gerado_em": timezone.localtime(),
    })


@login_required
@role_required(*RELATORIOS)
def fluxo_caixa(request):
    data_inicio, data_fim = _periodo_from_request(request)
    linhas = _fluxo_caixa_periodo(data_inicio, data_fim)
    context = {
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "linhas": linhas,
        "total_previsto_receber": sum((linha["previsto_receber"] for linha in linhas), Decimal("0.00")),
        "total_previsto_pagar": sum((linha["previsto_pagar"] for linha in linhas), Decimal("0.00")),
        "total_realizado_receber": sum((linha["realizado_receber"] for linha in linhas), Decimal("0.00")),
        "total_realizado_pagar": sum((linha["realizado_pagar"] for linha in linhas), Decimal("0.00")),
    }
    context["saldo_previsto"] = context["total_previsto_receber"] - context["total_previsto_pagar"]
    context["saldo_realizado"] = context["total_realizado_receber"] - context["total_realizado_pagar"]
    return render(request, "financeiro/fluxo_caixa.html", context)


@login_required
@role_required(*RELATORIOS)
def fluxo_caixa_csv(request):
    data_inicio, data_fim = _periodo_from_request(request)
    linhas = _fluxo_caixa_periodo(data_inicio, data_fim)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="fluxo_caixa_{data_inicio}_{data_fim}.csv"'
    response.write("\ufeff")
    writer = csv.writer(response, delimiter=";")
    writer.writerow(["Data", "Previsto receber", "Previsto pagar", "Saldo previsto", "Realizado receber", "Realizado pagar", "Saldo realizado"])
    for linha in linhas:
        writer.writerow([
            linha["data"].strftime("%d/%m/%Y"),
            str(linha["previsto_receber"]).replace(".", ","),
            str(linha["previsto_pagar"]).replace(".", ","),
            str(linha["saldo_previsto"]).replace(".", ","),
            str(linha["realizado_receber"]).replace(".", ","),
            str(linha["realizado_pagar"]).replace(".", ","),
            str(linha["saldo_realizado"]).replace(".", ","),
        ])
    return response


@login_required
@role_required(*RELATORIOS)
def conciliacao(request):
    data_inicio, data_fim = _periodo_from_request(request)
    linhas = _conciliacao_periodo(data_inicio, data_fim)
    context = {
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "linhas": linhas,
        "total_entradas_pdv": sum((linha["entradas_pdv"] for linha in linhas), Decimal("0.00")),
        "total_recebimentos_financeiros": sum((linha["recebimentos_financeiros"] for linha in linhas), Decimal("0.00")),
        "total_saidas_financeiras": sum((linha["saidas_financeiras"] for linha in linhas), Decimal("0.00")),
    }
    context["saldo_operacional"] = context["total_entradas_pdv"] + context["total_recebimentos_financeiros"] - context["total_saidas_financeiras"]
    return render(request, "financeiro/conciliacao.html", context)


@login_required
@role_required(*RELATORIOS)
def conciliacao_csv(request):
    data_inicio, data_fim = _periodo_from_request(request)
    linhas = _conciliacao_periodo(data_inicio, data_fim)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="conciliacao_{data_inicio}_{data_fim}.csv"'
    response.write("\ufeff")
    writer = csv.writer(response, delimiter=";")
    writer.writerow(["Data", "Entradas PDV", "Recebimentos financeiros", "Saidas financeiras", "Saldo operacional"])
    for linha in linhas:
        writer.writerow([
            linha["data"].strftime("%d/%m/%Y"),
            str(linha["entradas_pdv"]).replace(".", ","),
            str(linha["recebimentos_financeiros"]).replace(".", ","),
            str(linha["saidas_financeiras"]).replace(".", ","),
            str(linha["saldo_operacional"]).replace(".", ","),
        ])
    return response


@login_required
@role_required(*SISTEMA)
def conta_form(request, pk=None):
    conta = get_object_or_404(ContaFinanceira, pk=pk) if pk else None
    if request.method == "POST":
        form = ContaFinanceiraForm(request.POST, instance=conta)
        if form.is_valid():
            nova_conta = form.save(commit=False)
            if not nova_conta.pk:
                nova_conta.usuario = request.user
            nova_conta.save()
            messages.success(request, "Conta financeira salva.")
            return redirect("financeiro:contas")
    else:
        form = ContaFinanceiraForm(instance=conta)
    return render(request, "financeiro/conta_form.html", {"form": form, "conta": conta})


@login_required
@role_required(*SISTEMA)
def baixar(request, pk):
    conta = get_object_or_404(ContaFinanceira, pk=pk)
    initial = {"data_pagamento": timezone.localdate(), "valor_pago": conta.valor}
    if request.method == "POST":
        form = BaixaContaForm(request.POST)
        if form.is_valid():
            try:
                baixar_conta(conta=conta, usuario=request.user, ip=request.META.get("REMOTE_ADDR"), **form.cleaned_data)
            except ValidationError as exc:
                messages.error(request, " ".join(exc.messages))
            else:
                messages.success(request, "Conta baixada com sucesso.")
                return redirect("financeiro:contas")
    else:
        form = BaixaContaForm(initial=initial)
    return render(request, "financeiro/baixa_form.html", {"form": form, "conta": conta})


@login_required
@role_required(*SISTEMA)
def cancelar(request, pk):
    conta = get_object_or_404(ContaFinanceira, pk=pk)
    if request.method == "POST":
        try:
            cancelar_conta(conta=conta, usuario=request.user, motivo=request.POST.get("motivo", ""), ip=request.META.get("REMOTE_ADDR"))
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        else:
            messages.success(request, "Conta cancelada.")
    return redirect("financeiro:contas")


@login_required
@role_required(*SISTEMA)
def categorias(request):
    categorias_qs = CategoriaFinanceira.objects.order_by("tipo", "nome")
    return render(request, "financeiro/categorias.html", {"categorias": categorias_qs})


@login_required
@role_required(*SISTEMA)
def categoria_form(request, pk=None):
    categoria = get_object_or_404(CategoriaFinanceira, pk=pk) if pk else None
    if request.method == "POST":
        form = CategoriaFinanceiraForm(request.POST, instance=categoria)
        if form.is_valid():
            form.save()
            messages.success(request, "Categoria financeira salva.")
            return redirect("financeiro:categorias")
    else:
        form = CategoriaFinanceiraForm(instance=categoria)
    return render(request, "financeiro/categoria_form.html", {"form": form, "categoria": categoria})
