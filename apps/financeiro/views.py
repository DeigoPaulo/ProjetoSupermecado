import csv
from collections import OrderedDict
from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.http import url_has_allowed_host_and_scheme

from apps.accounts.permissions import RELATORIOS, SISTEMA, role_required
from apps.empresas.models import Filial
from apps.vendas.models import PagamentoVenda, StatusVenda

from .forms import BaixaContaForm, CategoriaFinanceiraForm, ContaFinanceiraForm, ContaMovimentoFinanceiroForm, TransferenciaFinanceiraForm
from .models import CategoriaFinanceira, ConciliacaoLancamentoFinanceiro, ContaFinanceira, ContaMovimentoFinanceiro, LancamentoFinanceiro, StatusContaFinanceira, TipoContaFinanceira, TipoLancamentoFinanceiro, TransferenciaFinanceira
from .services import baixar_conta, cancelar_conta, conciliar_lancamento, estornar_lancamento, realizar_transferencia


def _periodo_from_request(request):
    hoje = timezone.localdate()
    data_inicio = parse_date(request.GET.get("data_inicio") or "") or hoje.replace(day=1)
    data_fim = parse_date(request.GET.get("data_fim") or "") or hoje
    return data_inicio, data_fim


def _next_seguro(request, default="financeiro:contas"):
    destino = request.POST.get("next") or request.GET.get("next") or ""
    if destino and url_has_allowed_host_and_scheme(destino, allowed_hosts={request.get_host()}):
        return destino
    return default


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




def _valor_monetario_json(valor):
    return f"{valor.quantize(Decimal('0.01')):.2f}"

def _conciliacao_bancaria_json(resumo):
    por_conta = []
    for linha in resumo["por_conta"]:
        por_conta.append({
            **linha,
            "valor_total": _valor_monetario_json(linha["valor_total"]),
            "valor_conciliado": _valor_monetario_json(linha["valor_conciliado"]),
        })
    return {
        **resumo,
        "percentual": _valor_monetario_json(resumo["percentual"]),
        "valor_total": _valor_monetario_json(resumo["valor_total"]),
        "valor_conciliado": _valor_monetario_json(resumo["valor_conciliado"]),
        "valor_pendente": _valor_monetario_json(resumo["valor_pendente"]),
        "por_conta": por_conta,
    }
def _resultado_financeiro_periodo(data_inicio, data_fim):
    lancamentos = (
        LancamentoFinanceiro.objects.select_related("conta", "conta__filial", "conta_financeira", "conta_financeira__categoria")
        .filter(data__gte=data_inicio, data__lte=data_fim)
        .exclude(origem="TRANSFERENCIA")
    )
    receitas = lancamentos.filter(tipo=TipoLancamentoFinanceiro.ENTRADA).aggregate(total=Sum("valor"))["total"] or Decimal("0.00")
    despesas = lancamentos.filter(tipo=TipoLancamentoFinanceiro.SAIDA).aggregate(total=Sum("valor"))["total"] or Decimal("0.00")
    por_origem = []
    origens = lancamentos.values("origem", "tipo").annotate(total=Sum("valor")).order_by("origem", "tipo")
    acumulado_origem = OrderedDict()
    for item in origens:
        linha = acumulado_origem.setdefault(item["origem"], {"origem": item["origem"], "receitas": Decimal("0.00"), "despesas": Decimal("0.00")})
        if item["tipo"] == TipoLancamentoFinanceiro.ENTRADA:
            linha["receitas"] += item["total"]
        else:
            linha["despesas"] += item["total"]
    for linha in acumulado_origem.values():
        linha["resultado"] = linha["receitas"] - linha["despesas"]
        por_origem.append(linha)

    por_conta = []
    contas = lancamentos.values("conta__nome", "conta__filial__nome", "tipo").annotate(total=Sum("valor")).order_by("conta__filial__nome", "conta__nome")
    acumulado_conta = OrderedDict()
    for item in contas:
        chave = (item["conta__filial__nome"], item["conta__nome"])
        linha = acumulado_conta.setdefault(
            chave,
            {"filial": item["conta__filial__nome"], "conta": item["conta__nome"], "receitas": Decimal("0.00"), "despesas": Decimal("0.00")},
        )
        if item["tipo"] == TipoLancamentoFinanceiro.ENTRADA:
            linha["receitas"] += item["total"]
        else:
            linha["despesas"] += item["total"]
    for linha in acumulado_conta.values():
        linha["resultado"] = linha["receitas"] - linha["despesas"]
        por_conta.append(linha)

    por_categoria = []
    acumulado_categoria = OrderedDict()
    for lancamento in lancamentos:
        categoria = lancamento.conta_financeira.categoria if lancamento.conta_financeira_id else None
        nome_categoria = categoria.nome if categoria else "Sem categoria"
        chave = (nome_categoria, categoria.tipo if categoria else "")
        linha = acumulado_categoria.setdefault(
            chave,
            {"categoria": nome_categoria, "tipo": categoria.get_tipo_display() if categoria else "-", "receitas": Decimal("0.00"), "despesas": Decimal("0.00")},
        )
        if lancamento.tipo == TipoLancamentoFinanceiro.ENTRADA:
            linha["receitas"] += lancamento.valor
        else:
            linha["despesas"] += lancamento.valor
    for linha in acumulado_categoria.values():
        linha["resultado"] = linha["receitas"] - linha["despesas"]
        por_categoria.append(linha)

    saldos_contas = []
    for conta in ContaMovimentoFinanceiro.objects.select_related("filial", "filial__empresa").filter(ativa=True):
        entradas_periodo = lancamentos.filter(conta=conta, tipo=TipoLancamentoFinanceiro.ENTRADA).aggregate(total=Sum("valor"))["total"] or Decimal("0.00")
        saidas_periodo = lancamentos.filter(conta=conta, tipo=TipoLancamentoFinanceiro.SAIDA).aggregate(total=Sum("valor"))["total"] or Decimal("0.00")
        saldos_contas.append(
            {
                "filial": conta.filial.nome,
                "conta": conta.nome,
                "tipo": conta.get_tipo_display(),
                "saldo_inicial": conta.saldo_inicial,
                "entradas_periodo": entradas_periodo,
                "saidas_periodo": saidas_periodo,
                "saldo_atual": conta.saldo_atual,
            }
        )

    conciliacao_bancaria = _resumo_conciliacao_periodo(data_inicio, data_fim)
    return {
        "receitas": receitas,
        "despesas": despesas,
        "resultado": receitas - despesas,
        "por_origem": por_origem,
        "por_conta": por_conta,
        "por_categoria": por_categoria,
        "saldos_contas": saldos_contas,
        "balancete_contas": _balancete_contas_periodo(data_inicio, data_fim),
        "dre_gerencial": _dre_gerencial(receitas, despesas, por_categoria),
        "conciliacao_bancaria": conciliacao_bancaria,
        "pacote_contabil": _pacote_contabil_gerencial(data_inicio, data_fim, receitas, despesas, conciliacao_bancaria),
    }


def _dre_gerencial(receitas, despesas, por_categoria):
    resultado = receitas - despesas
    margem = Decimal("0.00")
    if receitas:
        margem = (resultado / receitas * Decimal("100.00")).quantize(Decimal("0.01"))
    linhas = [
        {
            "grupo": "Receita operacional",
            "valor": receitas,
            "natureza": "entrada",
            "observacao": "Entradas realizadas no livro financeiro, sem transferencias internas.",
        },
        {
            "grupo": "Despesas operacionais",
            "valor": despesas,
            "natureza": "saida",
            "observacao": "Saidas realizadas no livro financeiro, sem transferencias internas.",
        },
        {
            "grupo": "Resultado operacional",
            "valor": resultado,
            "natureza": "resultado",
            "observacao": "Receitas menos despesas no periodo filtrado.",
        },
    ]
    return {
        "linhas": linhas,
        "categorias": sorted(por_categoria, key=lambda item: (item["tipo"], item["categoria"])),
        "margem_percentual": margem,
    }


def _balancete_contas_periodo(data_inicio, data_fim):
    linhas = []
    contas = ContaMovimentoFinanceiro.objects.select_related("filial", "filial__empresa").filter(ativa=True)
    for conta in contas:
        anteriores = conta.lancamentos.filter(data__lt=data_inicio).values("tipo").annotate(total=Sum("valor"))
        anteriores_por_tipo = {item["tipo"]: item["total"] for item in anteriores}
        saldo_anterior = (
            conta.saldo_inicial
            + anteriores_por_tipo.get(TipoLancamentoFinanceiro.ENTRADA, Decimal("0.00"))
            - anteriores_por_tipo.get(TipoLancamentoFinanceiro.SAIDA, Decimal("0.00"))
        )
        periodo = conta.lancamentos.filter(data__gte=data_inicio, data__lte=data_fim).values("tipo").annotate(total=Sum("valor"))
        periodo_por_tipo = {item["tipo"]: item["total"] for item in periodo}
        entradas = periodo_por_tipo.get(TipoLancamentoFinanceiro.ENTRADA, Decimal("0.00"))
        saidas = periodo_por_tipo.get(TipoLancamentoFinanceiro.SAIDA, Decimal("0.00"))
        linhas.append(
            {
                "filial": conta.filial.nome,
                "conta": conta.nome,
                "tipo": conta.get_tipo_display(),
                "saldo_anterior": saldo_anterior,
                "entradas": entradas,
                "saidas": saidas,
                "saldo_final": saldo_anterior + entradas - saidas,
            }
        )
    return linhas



def _resumo_conciliacao_periodo(data_inicio, data_fim):
    lancamentos = LancamentoFinanceiro.objects.filter(data__range=(data_inicio, data_fim))
    total_lancamentos = lancamentos.count()
    total_valor = lancamentos.aggregate(total=Sum("valor"))["total"] or Decimal("0.00")
    conciliados_qs = lancamentos.filter(conciliacao_bancaria__isnull=False)
    conciliados = conciliados_qs.count()
    valor_conciliado = conciliados_qs.aggregate(total=Sum("valor"))["total"] or Decimal("0.00")
    percentual = Decimal("0.00")
    if total_lancamentos:
        percentual = (Decimal(conciliados) / Decimal(total_lancamentos) * Decimal("100.00")).quantize(Decimal("0.01"))
    por_conta = []
    for conta in ContaMovimentoFinanceiro.objects.select_related("filial").filter(lancamentos__data__range=(data_inicio, data_fim)).distinct():
        movimentos = lancamentos.filter(conta=conta)
        movimentos_conciliados = movimentos.filter(conciliacao_bancaria__isnull=False)
        conta_total = movimentos.count()
        conta_conciliados = movimentos_conciliados.count()
        por_conta.append({
            "filial": conta.filial.nome,
            "conta": conta.nome,
            "total": conta_total,
            "conciliados": conta_conciliados,
            "pendentes": conta_total - conta_conciliados,
            "valor_total": movimentos.aggregate(total=Sum("valor"))["total"] or Decimal("0.00"),
            "valor_conciliado": movimentos_conciliados.aggregate(total=Sum("valor"))["total"] or Decimal("0.00"),
        })
    return {
        "total_lancamentos": total_lancamentos,
        "conciliados": conciliados,
        "pendentes": total_lancamentos - conciliados,
        "percentual": percentual,
        "valor_total": total_valor,
        "valor_conciliado": valor_conciliado,
        "valor_pendente": total_valor - valor_conciliado,
        "por_conta": por_conta,
    }


def _pacote_contabil_gerencial(data_inicio, data_fim, receitas, despesas, conciliacao_bancaria):
    lancamentos_periodo = LancamentoFinanceiro.objects.filter(data__gte=data_inicio, data__lte=data_fim)
    transferencias = lancamentos_periodo.filter(origem="TRANSFERENCIA")
    estornos = lancamentos_periodo.filter(estorno_de__isnull=False)
    total_entradas_livro = lancamentos_periodo.filter(tipo=TipoLancamentoFinanceiro.ENTRADA).aggregate(total=Sum("valor"))["total"] or Decimal("0.00")
    total_saidas_livro = lancamentos_periodo.filter(tipo=TipoLancamentoFinanceiro.SAIDA).aggregate(total=Sum("valor"))["total"] or Decimal("0.00")
    transferencias_entradas = transferencias.filter(tipo=TipoLancamentoFinanceiro.ENTRADA).aggregate(total=Sum("valor"))["total"] or Decimal("0.00")
    transferencias_saidas = transferencias.filter(tipo=TipoLancamentoFinanceiro.SAIDA).aggregate(total=Sum("valor"))["total"] or Decimal("0.00")
    estornos_valor = estornos.aggregate(total=Sum("valor"))["total"] or Decimal("0.00")
    linhas = [
        {
            "item": "Receitas operacionais",
            "valor": receitas,
            "observacao": "Entradas sem transferências internas, usadas na DRE gerencial.",
        },
        {
            "item": "Despesas operacionais",
            "valor": despesas,
            "observacao": "Saídas sem transferências internas, usadas na DRE gerencial.",
        },
        {
            "item": "Resultado operacional",
            "valor": receitas - despesas,
            "observacao": "Diferença entre receitas e despesas do período filtrado.",
        },
        {
            "item": "Movimentação total do livro",
            "valor": total_entradas_livro - total_saidas_livro,
            "observacao": "Inclui transferências e serve para conferência do saldo das contas de movimento.",
        },
    ]
    alertas = [
        "Pacote gerencial para conferência interna e envio preliminar ao contador; não substitui SPED, ECD, ECF ou obrigações oficiais.",
        "Conferir documentos fiscais, centro de custo, plano de contas e conciliação bancária antes do fechamento contábil oficial.",
    ]
    return {
        "linhas": linhas,
        "total_lancamentos": lancamentos_periodo.count(),
        "transferencias": transferencias.count(),
        "transferencias_entradas": transferencias_entradas,
        "transferencias_saidas": transferencias_saidas,
        "estornos": estornos.count(),
        "estornos_valor": estornos_valor,
        "conciliacao_bancaria": conciliacao_bancaria,
        "alertas": alertas,
    }


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
@role_required(*RELATORIOS)
def resultado_financeiro(request):
    data_inicio, data_fim = _periodo_from_request(request)
    resultado = _resultado_financeiro_periodo(data_inicio, data_fim)
    return render(request, "financeiro/resultado.html", {
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        **resultado,
    })


@login_required
@role_required(*RELATORIOS)
def resultado_financeiro_csv(request):
    data_inicio, data_fim = _periodo_from_request(request)
    resultado = _resultado_financeiro_periodo(data_inicio, data_fim)
    def valor_csv(valor):
        return f"{valor:.2f}".replace(".", ",")

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="resultado_financeiro_{data_inicio}_{data_fim}.csv"'
    response.write("\ufeff")
    writer = csv.writer(response, delimiter=";")
    writer.writerow(["Resumo", "Receitas", "Despesas", "Resultado"])
    writer.writerow([
        "Periodo",
        f"{resultado['receitas']:.2f}".replace(".", ","),
        f"{resultado['despesas']:.2f}".replace(".", ","),
        f"{resultado['resultado']:.2f}".replace(".", ","),
    ])
    writer.writerow([])
    writer.writerow(["DRE gerencial"])
    writer.writerow(["Grupo", "Valor", "Observacao"])
    for linha in resultado["dre_gerencial"]["linhas"]:
        writer.writerow([linha["grupo"], valor_csv(linha["valor"]), linha["observacao"]])
    writer.writerow(["Margem operacional", f"{resultado['dre_gerencial']['margem_percentual']:.2f}".replace(".", ",") + "%", "Resultado dividido pela receita operacional."])
    writer.writerow([])
    writer.writerow(["Origem", "Receitas", "Despesas", "Resultado"])
    for linha in resultado["por_origem"]:
        writer.writerow([linha["origem"], str(linha["receitas"]).replace(".", ","), str(linha["despesas"]).replace(".", ","), str(linha["resultado"]).replace(".", ",")])
    writer.writerow([])
    writer.writerow(["Categoria", "Tipo", "Receitas", "Despesas", "Resultado"])
    for linha in resultado["por_categoria"]:
        writer.writerow([
            linha["categoria"],
            linha["tipo"],
            str(linha["receitas"]).replace(".", ","),
            str(linha["despesas"]).replace(".", ","),
            str(linha["resultado"]).replace(".", ","),
        ])
    writer.writerow([])
    writer.writerow(["Filial", "Conta", "Receitas", "Despesas", "Resultado"])
    for linha in resultado["por_conta"]:
        writer.writerow([linha["filial"], linha["conta"], str(linha["receitas"]).replace(".", ","), str(linha["despesas"]).replace(".", ","), str(linha["resultado"]).replace(".", ",")])
    writer.writerow([])
    writer.writerow(["Filial", "Conta movimento", "Tipo", "Saldo inicial", "Entradas periodo", "Saidas periodo", "Saldo atual"])
    for linha in resultado["saldos_contas"]:
        writer.writerow([
            linha["filial"],
            linha["conta"],
            linha["tipo"],
            valor_csv(linha["saldo_inicial"]),
            valor_csv(linha["entradas_periodo"]),
            valor_csv(linha["saidas_periodo"]),
            valor_csv(linha["saldo_atual"]),
        ])
    writer.writerow([])
    writer.writerow(["Pacote contabil gerencial"])
    writer.writerow(["Item", "Valor", "Observacao"])
    for linha in resultado["pacote_contabil"]["linhas"]:
        writer.writerow([linha["item"], valor_csv(linha["valor"]), linha["observacao"]])
    writer.writerow(["Total de lancamentos", resultado["pacote_contabil"]["total_lancamentos"], "Registros do livro financeiro no periodo."])
    writer.writerow(["Transferencias internas", resultado["pacote_contabil"]["transferencias"], f"Entradas {valor_csv(resultado['pacote_contabil']['transferencias_entradas'])} / Saidas {valor_csv(resultado['pacote_contabil']['transferencias_saidas'])}"])
    writer.writerow(["Estornos", resultado["pacote_contabil"]["estornos"], f"Valor {valor_csv(resultado['pacote_contabil']['estornos_valor'])}"])
    conciliacao = resultado["conciliacao_bancaria"]
    writer.writerow(["Conciliação bancária", f"{conciliacao['percentual']:.2f}".replace(".", ",") + "%", f"{conciliacao['conciliados']} conciliados / {conciliacao['pendentes']} pendentes"])
    writer.writerow(["Valor conciliado", valor_csv(conciliacao["valor_conciliado"]), f"Pendente {valor_csv(conciliacao['valor_pendente'])}"])
    for alerta in resultado["pacote_contabil"]["alertas"]:
        writer.writerow(["Alerta", "", alerta])
    writer.writerow([])
    writer.writerow(["Balancete gerencial por conta"])
    writer.writerow(["Filial", "Conta movimento", "Tipo", "Saldo anterior", "Entradas", "Saidas", "Saldo final"])
    for linha in resultado["balancete_contas"]:
        writer.writerow([
            linha["filial"],
            linha["conta"],
            linha["tipo"],
            valor_csv(linha["saldo_anterior"]),
            valor_csv(linha["entradas"]),
            valor_csv(linha["saidas"]),
            valor_csv(linha["saldo_final"]),
        ])
    return response


@login_required
@role_required(*RELATORIOS)
def resultado_pacote_contabil_json(request):
    data_inicio, data_fim = _periodo_from_request(request)
    resultado = _resultado_financeiro_periodo(data_inicio, data_fim)
    pacote = resultado["pacote_contabil"]
    payload = {
        "contrato": "financial_accounting_package_v1",
        "periodo": {"inicio": data_inicio.isoformat(), "fim": data_fim.isoformat()},
        "resumo": {
            "receitas": _valor_monetario_json(resultado["receitas"]),
            "despesas": _valor_monetario_json(resultado["despesas"]),
            "resultado": _valor_monetario_json(resultado["resultado"]),
            "margem_operacional_percentual": _valor_monetario_json(resultado["dre_gerencial"]["margem_percentual"]),
            "total_lancamentos": pacote["total_lancamentos"],
            "transferencias_internas": pacote["transferencias"],
            "estornos": pacote["estornos"],
        },
        "dre_gerencial": resultado["dre_gerencial"],
        "balancete_contas": resultado["balancete_contas"],
        "conciliacao_bancaria": _conciliacao_bancaria_json(resultado["conciliacao_bancaria"]),
        "pacote_contabil": pacote,
        "alertas": pacote["alertas"],
        "observacao": "Pacote gerencial de conferencia interna; nao substitui SPED, ECD, ECF ou obrigacoes oficiais.",
    }
    return JsonResponse(payload)



def _lancamentos_filtrados(request):
    data_inicio, data_fim = _periodo_from_request(request)
    conta_id = request.GET.get("conta", "").strip()
    tipo = request.GET.get("tipo", "").strip()
    filial_id = request.GET.get("filial", "").strip()
    lancamentos = LancamentoFinanceiro.objects.select_related("conta", "conta__filial", "conta_financeira", "usuario", "estorno_de", "pagamento_venda", "sangria", "suprimento").filter(
        data__gte=data_inicio,
        data__lte=data_fim,
    )
    if conta_id.isdigit():
        lancamentos = lancamentos.filter(conta_id=conta_id)
    if filial_id.isdigit():
        lancamentos = lancamentos.filter(conta__filial_id=filial_id)
    if tipo:
        lancamentos = lancamentos.filter(tipo=tipo)
    return lancamentos, {
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "conta_id": conta_id,
        "filial_id": filial_id,
        "tipo": tipo,
    }



def _lancamentos_conciliacao_filtrados(request):
    data_inicio, data_fim = _periodo_from_request(request)
    filtros = {
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "conta": request.GET.get("conta", "").strip(),
        "status": request.GET.get("status", "").strip(),
        "q": request.GET.get("q", "").strip(),
    }
    lancamentos = LancamentoFinanceiro.objects.select_related(
        "conta", "conta__filial", "conta__filial__empresa", "usuario", "conciliacao_bancaria", "conciliacao_bancaria__usuario"
    ).filter(data__range=(data_inicio, data_fim))
    if filtros["conta"].isdigit():
        lancamentos = lancamentos.filter(conta_id=filtros["conta"])
    if filtros["status"] == "conciliado":
        lancamentos = lancamentos.filter(conciliacao_bancaria__isnull=False)
    elif filtros["status"] == "pendente":
        lancamentos = lancamentos.filter(conciliacao_bancaria__isnull=True)
    if filtros["q"]:
        lancamentos = lancamentos.filter(
            Q(descricao__icontains=filtros["q"])
            | Q(origem__icontains=filtros["q"])
            | Q(conciliacao_bancaria__referencia_externa__icontains=filtros["q"])
        )
    return lancamentos, filtros


@login_required
@role_required(*RELATORIOS)
def conciliacao_bancaria(request):
    lancamentos, filtros = _lancamentos_conciliacao_filtrados(request)
    total = lancamentos.count()
    conciliados = lancamentos.filter(conciliacao_bancaria__isnull=False).count()
    pagina = Paginator(lancamentos, 50).get_page(request.GET.get("page"))
    query = request.GET.copy()
    query.pop("page", None)
    return render(request, "financeiro/conciliacao_bancaria.html", {
        **filtros,
        "pagina": pagina,
        "query_sem_pagina": query.urlencode(),
        "contas_opcoes": ContaMovimentoFinanceiro.objects.filter(ativa=True).select_related("filial"),
        "total": total,
        "conciliados": conciliados,
        "pendentes": total - conciliados,
    })


@login_required
@role_required(*SISTEMA)
def conciliar_lancamento_view(request, pk):
    lancamento = get_object_or_404(LancamentoFinanceiro, pk=pk)
    if request.method == "POST":
        data_conciliacao = parse_date(request.POST.get("data_conciliacao", "")) or timezone.localdate()
        try:
            conciliar_lancamento(
                lancamento=lancamento,
                data_conciliacao=data_conciliacao,
                referencia_externa=request.POST.get("referencia_externa", ""),
                observacao=request.POST.get("observacao", ""),
                usuario=request.user,
                ip=request.META.get("REMOTE_ADDR"),
            )
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        else:
            messages.success(request, f"Lancamento #{lancamento.pk} conciliado com o extrato.")
    return redirect("financeiro:conciliacao_bancaria")


@login_required
@role_required(*RELATORIOS)
def conciliacao_bancaria_csv(request):
    lancamentos, filtros = _lancamentos_conciliacao_filtrados(request)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="conciliacao_bancaria_{filtros["data_inicio"]}_{filtros["data_fim"]}.csv"'
    response.write("\ufeff")
    writer = csv.writer(response, delimiter=";")
    writer.writerow(["Data", "Conta", "Filial", "Tipo", "Descricao", "Valor", "Status", "Data conciliacao", "Referencia", "Responsavel", "Observacao"])
    for lancamento in lancamentos:
        conciliacao = getattr(lancamento, "conciliacao_bancaria", None)
        writer.writerow([
            lancamento.data.strftime("%d/%m/%Y"), lancamento.conta.nome, lancamento.conta.filial,
            lancamento.get_tipo_display(), lancamento.descricao, str(lancamento.valor).replace(".", ","),
            "Conciliado" if conciliacao else "Pendente",
            conciliacao.data_conciliacao.strftime("%d/%m/%Y") if conciliacao else "",
            conciliacao.referencia_externa if conciliacao else "",
            conciliacao.usuario.get_username() if conciliacao else "",
            conciliacao.observacao if conciliacao else "",
        ])
    return response


@login_required
@role_required(*RELATORIOS)
def contas_movimento(request):
    contas_qs = ContaMovimentoFinanceiro.objects.select_related("filial", "filial__empresa")
    contas_lista = list(contas_qs)
    return render(request, "financeiro/contas_movimento.html", {
        "contas_movimento": contas_lista,
        "total_contas_movimento": len(contas_lista),
        "saldo_total": sum((conta.saldo_atual for conta in contas_lista), Decimal("0.00")),
    })


@login_required
@role_required(*SISTEMA)
def conta_movimento_form(request, pk=None):
    conta = get_object_or_404(ContaMovimentoFinanceiro, pk=pk) if pk else None
    form = ContaMovimentoFinanceiroForm(request.POST or None, instance=conta)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Conta de movimento salva.")
        return redirect("financeiro:contas_movimento")
    return render(request, "financeiro/conta_movimento_form.html", {"form": form, "conta": conta})


@login_required
@role_required(*SISTEMA)
def transferencia_form(request):
    form = TransferenciaFinanceiraForm(request.POST or None, initial={"data": timezone.localdate()})
    if request.method == "POST" and form.is_valid():
        try:
            realizar_transferencia(
                usuario=request.user,
                ip=request.META.get("REMOTE_ADDR"),
                **form.cleaned_data,
            )
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, "Transferencia registrada com os dois lancamentos financeiros.")
            return redirect("financeiro:livro")
    return render(request, "financeiro/transferencia_form.html", {
        "form": form,
        "transferencias_recentes": TransferenciaFinanceira.objects.select_related(
            "conta_origem", "conta_destino", "conta_origem__filial", "conta_destino__filial", "usuario"
        )[:20],
    })


@login_required
@role_required(*RELATORIOS)
def livro_financeiro(request):
    lancamentos, filtros = _lancamentos_filtrados(request)
    total_entradas = lancamentos.filter(tipo=TipoLancamentoFinanceiro.ENTRADA).aggregate(total=Sum("valor"))["total"] or 0
    total_saidas = lancamentos.filter(tipo=TipoLancamentoFinanceiro.SAIDA).aggregate(total=Sum("valor"))["total"] or 0
    return render(request, "financeiro/livro.html", {
        **filtros,
        "lancamentos": lancamentos[:300],
        "contas_opcoes": ContaMovimentoFinanceiro.objects.filter(ativa=True).select_related("filial"),
        "filiais_opcoes": Filial.objects.filter(is_active=True).select_related("empresa"),
        "tipos_lancamento": TipoLancamentoFinanceiro.choices,
        "total_entradas": total_entradas,
        "total_saidas": total_saidas,
        "saldo_periodo": total_entradas - total_saidas,
    })


@login_required
@role_required(*RELATORIOS)
def livro_financeiro_csv(request):
    lancamentos, filtros = _lancamentos_filtrados(request)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="livro_financeiro_{filtros["data_inicio"]}_{filtros["data_fim"]}.csv"'
    response.write("\ufeff")
    writer = csv.writer(response, delimiter=";")
    writer.writerow(["Data", "Filial", "Conta", "Tipo", "Origem", "Descricao", "Valor", "Conta financeira", "Transferencia", "Pagamento venda", "Sangria", "Suprimento", "Estorno de", "Usuario", "Criado em"])
    for lancamento in lancamentos:
        writer.writerow([
            lancamento.data.strftime("%d/%m/%Y"),
            lancamento.conta.filial,
            lancamento.conta.nome,
            lancamento.get_tipo_display(),
            lancamento.origem,
            lancamento.descricao,
            str(lancamento.valor).replace(".", ","),
            lancamento.conta_financeira_id or "",
            lancamento.transferencia_id or "",
            lancamento.pagamento_venda_id or "",
            lancamento.sangria_id or "",
            lancamento.suprimento_id or "",
            lancamento.estorno_de_id or "",
            lancamento.usuario.get_username(),
            timezone.localtime(lancamento.criado_em).strftime("%d/%m/%Y %H:%M:%S"),
        ])
    return response


@login_required
@role_required(*SISTEMA)
def estornar_livro(request, pk):
    lancamento = get_object_or_404(LancamentoFinanceiro, pk=pk)
    if request.method == "POST":
        try:
            estornar_lancamento(
                lancamento=lancamento,
                usuario=request.user,
                motivo=request.POST.get("motivo", ""),
                ip=request.META.get("REMOTE_ADDR"),
            )
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        else:
            messages.success(request, "Estorno registrado com lancamento inverso.")
    return redirect("financeiro:livro")


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
    next_url = _next_seguro(request)
    initial = {"data_pagamento": timezone.localdate(), "valor_pago": conta.valor}
    if request.method == "POST":
        form = BaixaContaForm(request.POST, filial=conta.filial)
        if form.is_valid():
            try:
                baixar_conta(conta=conta, usuario=request.user, ip=request.META.get("REMOTE_ADDR"), **form.cleaned_data)
            except ValidationError as exc:
                messages.error(request, " ".join(exc.messages))
            else:
                messages.success(request, "Conta baixada com sucesso.")
                return redirect(next_url)
    else:
        form = BaixaContaForm(initial=initial, filial=conta.filial)
    return render(request, "financeiro/baixa_form.html", {"form": form, "conta": conta, "next_url": next_url})


@login_required
@role_required(*SISTEMA)
def cancelar(request, pk):
    conta = get_object_or_404(ContaFinanceira, pk=pk)
    next_url = _next_seguro(request)
    if request.method == "POST":
        try:
            cancelar_conta(conta=conta, usuario=request.user, motivo=request.POST.get("motivo", ""), ip=request.META.get("REMOTE_ADDR"))
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        else:
            messages.success(request, "Conta cancelada.")
    return redirect(next_url)


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
