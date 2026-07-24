import csv
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Sum
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date

from apps.accounts.permissions import CADASTROS, COMPRAS, ESTOQUE, PDV, RELATORIOS, has_role, role_required
from apps.compras.models import EntradaCompra, StatusEntradaCompra
from apps.estoque.models import Estoque, MovimentacaoEstoque, PerdaEstoque, TipoMovimentacaoEstoque
from apps.pdv.models import Caixa, Sangria, StatusCaixa, Suprimento
from apps.produtos.models import Produto
from apps.vendas.models import DevolucaoVenda, ItemDevolucaoVenda, ItemVenda, PagamentoVenda, StatusVenda, Venda


@login_required
def dashboard(request):
    if not has_role(request.user, RELATORIOS):
        if has_role(request.user, PDV):
            return redirect("pdv:pdv")
        if has_role(request.user, ESTOQUE):
            return redirect("estoque:lista")
        if has_role(request.user, COMPRAS):
            return redirect("compras:lista")
        if has_role(request.user, CADASTROS):
            return redirect("produtos:lista")
        return redirect("login")

    vendas_finalizadas = Venda.objects.filter(status=StatusVenda.FINALIZADA)
    devolucoes_total = DevolucaoVenda.objects.all()
    devolucoes_hoje = DevolucaoVenda.objects.filter(data__date=timezone.localdate())
    faturamento_bruto = vendas_finalizadas.aggregate(total=Sum("total_liquido"))["total"] or 0
    valor_devolucoes_total = devolucoes_total.aggregate(total=Sum("valor_total"))["total"] or 0
    valor_devolucoes_hoje = devolucoes_hoje.aggregate(total=Sum("valor_total"))["total"] or 0
    produtos_por_categoria = list(
        Produto.objects.values("categoria__nome").annotate(total=Count("id")).order_by("-total")[:6]
    )
    pagamentos_por_forma = list(
        PagamentoVenda.objects.filter(venda__status=StatusVenda.FINALIZADA)
        .values("forma_pagamento__nome")
        .annotate(total=Sum("valor"))
        .order_by("-total")[:6]
    )
    caixas_por_status = list(Caixa.objects.values("status").annotate(total=Count("id")).order_by("status"))
    status_caixa_labels = dict(StatusCaixa.choices)
    dashboard_charts = {
        "pagamentos": {
            "labels": [item["forma_pagamento__nome"] or "Sem forma" for item in pagamentos_por_forma],
            "values": [float(item["total"] or 0) for item in pagamentos_por_forma],
        },
        "categorias": {
            "labels": [item["categoria__nome"] or "Sem categoria" for item in produtos_por_categoria],
            "values": [item["total"] for item in produtos_por_categoria],
        },
        "caixas": {
            "labels": [status_caixa_labels.get(item["status"], item["status"]) for item in caixas_por_status],
            "values": [item["total"] for item in caixas_por_status],
        },
    }
    context = {
        "total_produtos": Produto.all_objects.count(),
        "produtos_ativos": Produto.objects.count(),
        "estoque_baixo": Estoque.objects.filter(quantidade_atual__lte=F("produto__estoque_minimo")).count(),
        "caixas_abertos": Caixa.objects.filter(status=StatusCaixa.ABERTO).count(),
        "total_vendas": vendas_finalizadas.count(),
        "faturamento": faturamento_bruto,
        "faturamento_liquido": faturamento_bruto - valor_devolucoes_total,
        "total_devolucoes_hoje": devolucoes_hoje.count(),
        "valor_devolucoes_hoje": valor_devolucoes_hoje,
        "ultimos_caixas": Caixa.objects.select_related("filial", "usuario_abertura").order_by("-data_abertura")[:5],
        "produtos_por_categoria": produtos_por_categoria,
        "dashboard_charts": dashboard_charts,
    }
    return render(request, "relatorios/dashboard.html", context)


def _periodo_from_request(request):
    hoje = timezone.localdate()
    data_inicio = parse_date(request.GET.get("data_inicio") or "") or hoje.replace(day=1)
    data_fim = parse_date(request.GET.get("data_fim") or "") or hoje
    return data_inicio, data_fim


def _dias_periodo(data_inicio, data_fim):
    return max((data_fim - data_inicio).days + 1, 1)


def _vendas_periodo(data_inicio, data_fim):
    return Venda.objects.filter(
        status=StatusVenda.FINALIZADA,
        data__date__gte=data_inicio,
        data__date__lte=data_fim,
    ).select_related("filial", "caixa", "cliente", "usuario")


def _csv_safe(value):
    if value is None:
        return ""
    text = str(value)
    if text.startswith(("=", "+", "-", "@")):
        return f"'{text}"
    return text


def _csv_money(value):
    return f"{Decimal(value or 0):.2f}".replace(".", ",")


def _caixas_periodo(data_inicio, data_fim):
    return Caixa.objects.filter(
        data_abertura__date__gte=data_inicio,
        data_abertura__date__lte=data_fim,
    ).select_related("filial", "usuario_abertura", "usuario_fechamento", "usuario_conferencia")


def _caixas_filtrados(request):
    data_inicio, data_fim = _periodo_from_request(request)
    operador_id = (request.GET.get("operador") or "").strip()
    caixas_qs = _caixas_periodo(data_inicio, data_fim)
    if operador_id.isdigit():
        caixas_qs = caixas_qs.filter(usuario_abertura_id=int(operador_id))
    return data_inicio, data_fim, operador_id, caixas_qs


def _operadores_caixa():
    User = get_user_model()
    return User.objects.filter(caixas_abertos__isnull=False).distinct().order_by("username")


def _resumo_caixas_por_operador(caixas_qs):
    vendas_por_operador = {
        item["caixa__usuario_abertura_id"]: item
        for item in Venda.objects.filter(caixa__in=caixas_qs, status=StatusVenda.FINALIZADA)
        .values("caixa__usuario_abertura_id")
        .annotate(vendas=Count("id"), total_vendas=Sum("total_liquido"))
    }
    sangrias_por_operador = {
        item["caixa__usuario_abertura_id"]: item["total"] or Decimal("0.00")
        for item in Sangria.objects.filter(caixa__in=caixas_qs)
        .values("caixa__usuario_abertura_id")
        .annotate(total=Sum("valor"))
    }
    suprimentos_por_operador = {
        item["caixa__usuario_abertura_id"]: item["total"] or Decimal("0.00")
        for item in Suprimento.objects.filter(caixa__in=caixas_qs)
        .values("caixa__usuario_abertura_id")
        .annotate(total=Sum("valor"))
    }
    resumo = []
    for item in caixas_qs.values("usuario_abertura_id", "usuario_abertura__username").annotate(
        caixas=Count("id"),
        valor_inicial=Sum("valor_inicial"),
        valor_declarado=Sum("valor_final"),
        valor_conferido=Sum("valor_conferido"),
    ).order_by("usuario_abertura__username"):
        vendas = vendas_por_operador.get(item["usuario_abertura_id"], {})
        sangrias = sangrias_por_operador.get(item["usuario_abertura_id"], Decimal("0.00"))
        suprimentos = suprimentos_por_operador.get(item["usuario_abertura_id"], Decimal("0.00"))
        resumo.append({
            "operador_id": item["usuario_abertura_id"],
            "operador": item["usuario_abertura__username"] or "Sem operador",
            "caixas": item["caixas"],
            "valor_inicial": item["valor_inicial"] or 0,
            "valor_declarado": item["valor_declarado"] or 0,
            "valor_conferido": item["valor_conferido"] or 0,
            "diferenca": (item["valor_conferido"] or 0) - (item["valor_declarado"] or 0),
            "vendas": vendas.get("vendas") or 0,
            "total_vendas": vendas.get("total_vendas") or 0,
            "sangrias": sangrias,
            "suprimentos": suprimentos,
            "saldo_operacional": (vendas.get("total_vendas") or Decimal("0.00")) + suprimentos - sangrias,
        })
    return resumo


def _preparar_caixas_conferencia(caixas_qs):
    caixas = list(caixas_qs)
    total_diferenca = Decimal("0.00")
    for caixa in caixas:
        if caixa.valor_final is not None and caixa.valor_conferido is not None:
            caixa.diferenca_conferencia = caixa.valor_conferido - caixa.valor_final
            total_diferenca += caixa.diferenca_conferencia
        else:
            caixa.diferenca_conferencia = None
    return caixas, total_diferenca


def _compras_periodo(data_inicio, data_fim):
    return EntradaCompra.objects.filter(
        status=StatusEntradaCompra.FINALIZADA,
        data_recebimento__date__gte=data_inicio,
        data_recebimento__date__lte=data_fim,
    ).select_related("fornecedor", "filial", "usuario")


def _perdas_periodo(data_inicio, data_fim):
    return PerdaEstoque.objects.filter(
        data__date__gte=data_inicio,
        data__date__lte=data_fim,
    ).select_related("produto", "produto__categoria", "filial", "usuario")


def _devolucoes_periodo(data_inicio, data_fim):
    return DevolucaoVenda.objects.filter(
        data__date__gte=data_inicio,
        data__date__lte=data_fim,
    ).select_related("venda", "venda__filial", "venda__cliente", "usuario").prefetch_related("itens__produto")


def _estoques_baixos():
    return Estoque.objects.select_related("produto", "filial", "produto__categoria").filter(
        quantidade_atual__lte=F("produto__estoque_minimo"), produto__is_active=True,
    ).order_by("produto__nome", "filial__nome")


def _movimentacoes_periodo(data_inicio, data_fim, tipo=""):
    movimentacoes = MovimentacaoEstoque.objects.filter(
        data__date__gte=data_inicio, data__date__lte=data_fim,
    ).select_related("produto", "filial", "usuario").order_by("-data")
    return movimentacoes.filter(tipo=tipo) if tipo else movimentacoes


@login_required
@role_required(*RELATORIOS)
def vendas(request):
    data_inicio, data_fim = _periodo_from_request(request)
    vendas_qs = _vendas_periodo(data_inicio, data_fim)

    itens_qs = ItemVenda.objects.filter(venda__in=vendas_qs).select_related("produto")
    devolucoes_qs = DevolucaoVenda.objects.filter(
        venda__in=vendas_qs,
        data__date__gte=data_inicio,
        data__date__lte=data_fim,
    )
    lucro_expr = ExpressionWrapper(
        F("total") - (F("custo_unitario_no_momento") * F("quantidade")),
        output_field=DecimalField(max_digits=12, decimal_places=2),
    )
    faturamento_bruto = vendas_qs.aggregate(total=Sum("total_liquido"))["total"] or 0
    valor_devolucoes = devolucoes_qs.aggregate(total=Sum("valor_total"))["total"] or 0

    context = {
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "vendas": vendas_qs[:100],
        "total_vendas": vendas_qs.count(),
        "faturamento": faturamento_bruto,
        "valor_devolucoes": valor_devolucoes,
        "faturamento_liquido": faturamento_bruto - valor_devolucoes,
        "descontos": vendas_qs.aggregate(total=Sum("desconto"))["total"] or 0,
        "lucro_estimado": itens_qs.aggregate(total=Sum(lucro_expr))["total"] or 0,
        "produtos_mais_vendidos": itens_qs.values("produto__nome").annotate(
            quantidade=Sum("quantidade"),
            total=Sum("total"),
        ).order_by("-quantidade")[:10],
    }
    return render(request, "relatorios/vendas.html", context)


@login_required
@role_required(*RELATORIOS)
def vendas_csv(request):
    data_inicio, data_fim = _periodo_from_request(request)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="vendas_{data_inicio}_{data_fim}.csv"'
    response.write("\ufeff")
    writer = csv.writer(response, delimiter=";")
    writer.writerow(["Venda", "Data", "Filial", "Cliente", "Operador", "Subtotal", "Desconto", "Total"])
    for venda in _vendas_periodo(data_inicio, data_fim).iterator():
        writer.writerow([
            venda.id,
            timezone.localtime(venda.data).strftime("%d/%m/%Y %H:%M"),
            _csv_safe(venda.filial),
            _csv_safe(venda.cliente) if venda.cliente else "Cliente avulso",
            _csv_safe(venda.usuario),
            str(venda.subtotal).replace(".", ","),
            str(venda.desconto).replace(".", ","),
            str(venda.total_liquido).replace(".", ","),
        ])
    return response


@login_required
@role_required(*RELATORIOS)
def vendas_imprimir(request):
    data_inicio, data_fim = _periodo_from_request(request)
    vendas_qs = _vendas_periodo(data_inicio, data_fim)
    context = {
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "vendas": vendas_qs,
        "total_vendas": vendas_qs.count(),
        "faturamento": vendas_qs.aggregate(total=Sum("total_liquido"))["total"] or 0,
        "descontos": vendas_qs.aggregate(total=Sum("desconto"))["total"] or 0,
        "gerado_em": timezone.localtime(),
    }
    return render(request, "relatorios/vendas_imprimir.html", context)


@login_required
@role_required(*RELATORIOS)
def curva_abc(request):
    data_inicio, data_fim = _periodo_from_request(request)
    linhas, total_liquido = _calcular_curva_abc(data_inicio, data_fim)
    context = {
        "data_inicio": data_inicio, "data_fim": data_fim, "linhas": linhas[:200],
        "total_liquido": total_liquido, "total_produtos": len(linhas),
        "classe_a": sum(1 for item in linhas if item["classe"] == "A"),
        "classe_b": sum(1 for item in linhas if item["classe"] == "B"),
        "classe_c": sum(1 for item in linhas if item["classe"] == "C"),
    }
    return render(request, "relatorios/curva_abc.html", context)


def _calcular_curva_abc(data_inicio, data_fim):
    vendas_qs = Venda.objects.filter(
        status=StatusVenda.FINALIZADA,
        data__date__gte=data_inicio,
        data__date__lte=data_fim,
    )
    vendidos = list(
        ItemVenda.objects.filter(venda__in=vendas_qs)
        .values("produto_id", "produto__nome", "produto__codigo_barras")
        .annotate(quantidade=Sum("quantidade"), total=Sum("total"))
        .order_by("-total")
    )
    devolvidos = {
        item["produto_id"]: item
        for item in ItemDevolucaoVenda.objects.filter(
            devolucao__venda__in=vendas_qs,
            devolucao__data__date__gte=data_inicio,
            devolucao__data__date__lte=data_fim,
        )
        .values("produto_id")
        .annotate(quantidade=Sum("quantidade"), total=Sum("valor_total"))
    }

    linhas = []
    total_liquido = Decimal("0.00")
    for item in vendidos:
        devolucao = devolvidos.get(item["produto_id"], {})
        quantidade_liquida = (item["quantidade"] or Decimal("0.000")) - (devolucao.get("quantidade") or Decimal("0.000"))
        valor_liquido = (item["total"] or Decimal("0.00")) - (devolucao.get("total") or Decimal("0.00"))
        if valor_liquido <= 0:
            continue
        total_liquido += valor_liquido
        linhas.append(
            {
                "produto_id": item["produto_id"],
                "produto": item["produto__nome"],
                "codigo": item["produto__codigo_barras"],
                "quantidade": quantidade_liquida,
                "valor": valor_liquido,
                "devolvido": devolucao.get("total") or Decimal("0.00"),
            }
        )

    acumulado = Decimal("0.00")
    for linha in sorted(linhas, key=lambda item: item["valor"], reverse=True):
        participacao = (linha["valor"] / total_liquido * Decimal("100")) if total_liquido else Decimal("0.00")
        acumulado += participacao
        linha["participacao"] = participacao
        linha["acumulado"] = acumulado
        if acumulado <= Decimal("80.00"):
            linha["classe"] = "A"
        elif acumulado <= Decimal("95.00"):
            linha["classe"] = "B"
        else:
            linha["classe"] = "C"

    linhas = sorted(linhas, key=lambda item: item["valor"], reverse=True)
    return linhas, total_liquido


@login_required
@role_required(*RELATORIOS)
def curva_abc_csv(request):
    data_inicio, data_fim = _periodo_from_request(request)
    linhas, _ = _calcular_curva_abc(data_inicio, data_fim)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="curva_abc_{data_inicio}_{data_fim}.csv"'
    response.write("\ufeff")
    writer = csv.writer(response, delimiter=";")
    writer.writerow(["Classe", "Produto", "Codigo", "Quantidade liquida", "Devolucoes", "Valor liquido", "Participacao %", "Acumulado %"])
    for item in linhas:
        writer.writerow([item["classe"], _csv_safe(item["produto"]), _csv_safe(item["codigo"]),
                         str(item["quantidade"]).replace(".", ","), str(item["devolvido"]).replace(".", ","),
                         str(item["valor"]).replace(".", ","), f'{item["participacao"]:.2f}'.replace(".", ","),
                         f'{item["acumulado"]:.2f}'.replace(".", ",")])
    return response


@login_required
@role_required(*RELATORIOS)
def curva_abc_imprimir(request):
    data_inicio, data_fim = _periodo_from_request(request)
    dados, total_liquido = _calcular_curva_abc(data_inicio, data_fim)
    linhas = [[item["classe"], item["produto"], item["codigo"], f'{item["quantidade"]:.3f}',
               f'R$ {item["devolvido"]:.2f}', f'R$ {item["valor"]:.2f}',
               f'{item["participacao"]:.2f}%', f'{item["acumulado"]:.2f}%'] for item in dados]
    return render(request, "relatorios/exportacao_imprimir.html", {
        "titulo": "Curva ABC", "subtitulo": "Classificacao de produtos por faturamento liquido",
        "data_inicio": data_inicio, "data_fim": data_fim, "gerado_em": timezone.localtime(),
        "cabecalhos": ["Classe", "Produto", "Codigo", "Qtd liquida", "Devolucoes", "Valor liquido", "%", "% acum."],
        "linhas": linhas, "resumos": [("Produtos", len(dados)), ("Faturamento liquido", f"R$ {total_liquido:.2f}")],
    })


@login_required
@role_required(*RELATORIOS)
def estoque_baixo(request):
    return render(request, "relatorios/estoque_baixo.html", {"estoques": _estoques_baixos()})


@login_required
@role_required(*RELATORIOS)
def estoque_baixo_csv(request):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="estoque_baixo_{timezone.localdate()}.csv"'
    response.write("\ufeff")
    writer = csv.writer(response, delimiter=";")
    writer.writerow(["Produto", "Categoria", "Filial", "Atual", "Reservado", "Disponivel", "Minimo", "Deficit"])
    for estoque in _estoques_baixos().iterator():
        deficit = max(estoque.produto.estoque_minimo - estoque.quantidade_disponivel, Decimal("0.000"))
        writer.writerow([
            _csv_safe(estoque.produto), _csv_safe(estoque.produto.categoria), _csv_safe(estoque.filial),
            str(estoque.quantidade_atual).replace(".", ","), str(estoque.quantidade_reservada).replace(".", ","),
            str(estoque.quantidade_disponivel).replace(".", ","), str(estoque.produto.estoque_minimo).replace(".", ","),
            str(deficit).replace(".", ","),
        ])
    return response


@login_required
@role_required(*RELATORIOS)
def estoque_baixo_imprimir(request):
    linhas = []
    for estoque in _estoques_baixos():
        deficit = max(estoque.produto.estoque_minimo - estoque.quantidade_disponivel, Decimal("0.000"))
        linhas.append([estoque.produto, estoque.produto.categoria, estoque.filial, estoque.quantidade_atual,
                       estoque.quantidade_reservada, estoque.quantidade_disponivel, estoque.produto.estoque_minimo, deficit])
    hoje = timezone.localdate()
    return render(request, "relatorios/exportacao_imprimir.html", {
        "titulo": "Relatorio de estoque baixo", "subtitulo": "Produtos que exigem atencao para reposicao",
        "data_inicio": hoje, "data_fim": hoje, "gerado_em": timezone.localtime(),
        "cabecalhos": ["Produto", "Categoria", "Filial", "Atual", "Reservado", "Disponivel", "Minimo", "Deficit"],
        "linhas": linhas, "resumos": [("Produtos/filiais", len(linhas))],
    })


@login_required
@role_required(*RELATORIOS)
def sugestao_reposicao(request):
    data_inicio, data_fim = _periodo_from_request(request)
    try:
        dias_cobertura = int(request.GET.get("dias_cobertura") or 7)
    except ValueError:
        dias_cobertura = 7
    dias_cobertura = min(max(dias_cobertura, 1), 90)
    linhas = _calcular_reposicao(data_inicio, data_fim, dias_cobertura)
    context = {
        "data_inicio": data_inicio, "data_fim": data_fim, "dias_cobertura": dias_cobertura,
        "linhas": linhas[:200], "total_produtos": len(linhas),
        "quantidade_sugerida": sum((item["sugestao"] for item in linhas), Decimal("0.000")),
    }
    return render(request, "relatorios/sugestao_reposicao.html", context)


def _calcular_reposicao(data_inicio, data_fim, dias_cobertura):
    dias_periodo = Decimal(str(_dias_periodo(data_inicio, data_fim)))
    vendas_qs = Venda.objects.filter(
        status=StatusVenda.FINALIZADA,
        data__date__gte=data_inicio,
        data__date__lte=data_fim,
    )
    vendas_por_produto = {
        item["produto_id"]: item["quantidade"] or Decimal("0.000")
        for item in ItemVenda.objects.filter(venda__in=vendas_qs)
        .values("produto_id")
        .annotate(quantidade=Sum("quantidade"))
    }
    devolucoes_por_produto = {
        item["produto_id"]: item["quantidade"] or Decimal("0.000")
        for item in ItemDevolucaoVenda.objects.filter(
            devolucao__venda__in=vendas_qs,
            devolucao__data__date__gte=data_inicio,
            devolucao__data__date__lte=data_fim,
        )
        .values("produto_id")
        .annotate(quantidade=Sum("quantidade"))
    }

    linhas = []
    estoques = Estoque.objects.select_related("produto", "produto__categoria", "filial").filter(produto__is_active=True)
    for estoque in estoques:
        vendido = vendas_por_produto.get(estoque.produto_id, Decimal("0.000"))
        devolvido = devolucoes_por_produto.get(estoque.produto_id, Decimal("0.000"))
        venda_liquida = max(vendido - devolvido, Decimal("0.000"))
        media_dia = venda_liquida / dias_periodo
        disponivel = estoque.quantidade_disponivel
        necessidade_minimo = max(estoque.produto.estoque_minimo - disponivel, Decimal("0.000"))
        necessidade_cobertura = max((media_dia * Decimal(str(dias_cobertura))) - disponivel, Decimal("0.000"))
        sugestao = max(necessidade_minimo, necessidade_cobertura).quantize(Decimal("0.001"))
        if sugestao <= 0:
            continue
        linhas.append(
            {
                "produto": estoque.produto,
                "filial": estoque.filial,
                "disponivel": disponivel,
                "estoque_minimo": estoque.produto.estoque_minimo,
                "venda_liquida": venda_liquida,
                "media_dia": media_dia,
                "sugestao": sugestao,
            }
        )

    linhas.sort(key=lambda item: (item["sugestao"], item["media_dia"]), reverse=True)
    return linhas


@login_required
@role_required(*RELATORIOS)
def sugestao_reposicao_csv(request):
    data_inicio, data_fim = _periodo_from_request(request)
    try:
        dias_cobertura = int(request.GET.get("dias_cobertura") or 7)
    except ValueError:
        dias_cobertura = 7
    dias_cobertura = min(max(dias_cobertura, 1), 90)
    linhas = _calcular_reposicao(data_inicio, data_fim, dias_cobertura)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="reposicao_{data_inicio}_{data_fim}.csv"'
    response.write("\ufeff")
    writer = csv.writer(response, delimiter=";")
    writer.writerow(["Produto", "Categoria", "Filial", "Disponivel", "Minimo", "Venda no periodo", "Media por dia", "Dias cobertura", "Quantidade sugerida"])
    for item in linhas:
        writer.writerow([_csv_safe(item["produto"].nome), _csv_safe(item["produto"].categoria), _csv_safe(item["filial"]),
                         str(item["disponivel"]).replace(".", ","), str(item["estoque_minimo"]).replace(".", ","),
                         str(item["venda_liquida"]).replace(".", ","), f'{item["media_dia"]:.3f}'.replace(".", ","),
                         dias_cobertura, str(item["sugestao"]).replace(".", ",")])
    return response


@login_required
@role_required(*RELATORIOS)
def sugestao_reposicao_imprimir(request):
    data_inicio, data_fim = _periodo_from_request(request)
    try:
        dias_cobertura = int(request.GET.get("dias_cobertura") or 7)
    except ValueError:
        dias_cobertura = 7
    dias_cobertura = min(max(dias_cobertura, 1), 90)
    dados = _calcular_reposicao(data_inicio, data_fim, dias_cobertura)
    linhas = [[item["produto"].nome, item["produto"].categoria, item["filial"], item["disponivel"],
               item["estoque_minimo"], item["venda_liquida"], f'{item["media_dia"]:.3f}', item["sugestao"]]
              for item in dados]
    quantidade = sum((item["sugestao"] for item in dados), Decimal("0.000"))
    return render(request, "relatorios/exportacao_imprimir.html", {
        "titulo": "Sugestao de reposicao", "subtitulo": f"Necessidade calculada para {dias_cobertura} dias de cobertura",
        "data_inicio": data_inicio, "data_fim": data_fim, "gerado_em": timezone.localtime(),
        "cabecalhos": ["Produto", "Categoria", "Filial", "Disponivel", "Minimo", "Venda periodo", "Media/dia", "Sugerido"],
        "linhas": linhas, "resumos": [("Produtos", len(dados)), ("Quantidade sugerida", quantidade)],
    })


@login_required
@role_required(*RELATORIOS)
def movimentacoes_estoque(request):
    data_inicio, data_fim = _periodo_from_request(request)
    tipo = request.GET.get("tipo") or ""
    movimentacoes = _movimentacoes_periodo(data_inicio, data_fim, tipo)

    context = {
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "tipo": tipo,
        "tipos": TipoMovimentacaoEstoque.choices,
        "movimentacoes": movimentacoes[:200],
        "total_movimentacoes": movimentacoes.count(),
        "quantidade_total": movimentacoes.aggregate(total=Sum("quantidade"))["total"] or 0,
    }
    return render(request, "relatorios/movimentacoes_estoque.html", context)


@login_required
@role_required(*RELATORIOS)
def movimentacoes_estoque_csv(request):
    data_inicio, data_fim = _periodo_from_request(request)
    tipo = request.GET.get("tipo") or ""
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="movimentacoes_estoque_{data_inicio}_{data_fim}.csv"'
    response.write("\ufeff")
    writer = csv.writer(response, delimiter=";")
    writer.writerow(["Data", "Produto", "Filial", "Tipo", "Quantidade", "Custo unitario", "Custo total", "Referencia", "Responsavel", "Motivo"])
    for mov in _movimentacoes_periodo(data_inicio, data_fim, tipo).iterator():
        writer.writerow([
            timezone.localtime(mov.data).strftime("%d/%m/%Y %H:%M"), _csv_safe(mov.produto), _csv_safe(mov.filial),
            mov.get_tipo_display(), str(mov.quantidade).replace(".", ","),
            str(mov.custo_unitario).replace(".", ",") if mov.custo_unitario is not None else "",
            str(mov.custo_total).replace(".", ",") if mov.custo_total is not None else "",
            _csv_safe(mov.referencia), _csv_safe(mov.usuario) if mov.usuario else "", _csv_safe(mov.motivo),
        ])
    return response


@login_required
@role_required(*RELATORIOS)
def movimentacoes_estoque_imprimir(request):
    data_inicio, data_fim = _periodo_from_request(request)
    tipo = request.GET.get("tipo") or ""
    movimentacoes = _movimentacoes_periodo(data_inicio, data_fim, tipo)
    linhas = [[timezone.localtime(mov.data).strftime("%d/%m/%Y %H:%M"), mov.produto, mov.filial,
               mov.get_tipo_display(), mov.quantidade, mov.referencia or "-", mov.usuario or "-", mov.motivo or "-"]
              for mov in movimentacoes]
    return render(request, "relatorios/exportacao_imprimir.html", {
        "titulo": "Movimentacoes de estoque", "subtitulo": "Entradas, saidas, vendas, devolucoes, reservas e ajustes",
        "data_inicio": data_inicio, "data_fim": data_fim, "gerado_em": timezone.localtime(),
        "cabecalhos": ["Data", "Produto", "Filial", "Tipo", "Quantidade", "Referencia", "Responsavel", "Motivo"],
        "linhas": linhas, "resumos": [("Movimentacoes", len(linhas))],
    })


@login_required
@role_required(*RELATORIOS)
def perdas(request):
    data_inicio, data_fim = _periodo_from_request(request)
    perdas_qs = _perdas_periodo(data_inicio, data_fim)

    context = {
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "perdas": perdas_qs[:200],
        "total_perdas": perdas_qs.count(),
        "valor_custo_total": perdas_qs.aggregate(total=Sum("valor_custo_estimado"))["total"] or 0,
        "valor_venda_total": perdas_qs.aggregate(total=Sum("valor_venda_estimado"))["total"] or 0,
        "perdas_por_tipo": perdas_qs.values("tipo").annotate(
            quantidade=Count("id"),
            custo=Sum("valor_custo_estimado"),
            venda=Sum("valor_venda_estimado"),
        ).order_by("-custo"),
    }
    return render(request, "relatorios/perdas.html", context)


@login_required
@role_required(*RELATORIOS)
def perdas_csv(request):
    data_inicio, data_fim = _periodo_from_request(request)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="perdas_{data_inicio}_{data_fim}.csv"'
    response.write("\ufeff")
    writer = csv.writer(response, delimiter=";")
    writer.writerow(["Data", "Produto", "Filial", "Tipo", "Motivo", "Quantidade", "Responsavel", "Custo estimado", "Venda estimada"])
    for perda in _perdas_periodo(data_inicio, data_fim).iterator():
        writer.writerow([
            timezone.localtime(perda.data).strftime("%d/%m/%Y %H:%M"), _csv_safe(perda.produto), _csv_safe(perda.filial),
            perda.get_tipo_display(), _csv_safe(perda.motivo), str(perda.quantidade).replace(".", ","),
            _csv_safe(perda.usuario), str(perda.valor_custo_estimado).replace(".", ","),
            str(perda.valor_venda_estimado).replace(".", ","),
        ])
    return response


@login_required
@role_required(*RELATORIOS)
def perdas_imprimir(request):
    data_inicio, data_fim = _periodo_from_request(request)
    perdas_qs = _perdas_periodo(data_inicio, data_fim)
    linhas = [[
        timezone.localtime(perda.data).strftime("%d/%m/%Y %H:%M"), str(perda.produto), str(perda.filial),
        perda.get_tipo_display(), perda.motivo, perda.quantidade, perda.usuario,
        f"R$ {perda.valor_custo_estimado:.2f}", f"R$ {perda.valor_venda_estimado:.2f}",
    ] for perda in perdas_qs]
    return render(request, "relatorios/exportacao_imprimir.html", {
        "titulo": "Relatorio de perdas", "subtitulo": "Perdas registradas no estoque",
        "data_inicio": data_inicio, "data_fim": data_fim, "gerado_em": timezone.localtime(),
        "cabecalhos": ["Data", "Produto", "Filial", "Tipo", "Motivo", "Qtd", "Responsavel", "Custo", "Venda estimada"],
        "linhas": linhas,
        "resumos": [("Registros", perdas_qs.count()), ("Custo perdido", f'R$ {(perdas_qs.aggregate(total=Sum("valor_custo_estimado"))["total"] or 0):.2f}')],
    })


@login_required
@role_required(*RELATORIOS)
def devolucoes(request):
    data_inicio, data_fim = _periodo_from_request(request)
    devolucoes_qs = _devolucoes_periodo(data_inicio, data_fim)
    itens_qs = ItemDevolucaoVenda.objects.filter(devolucao__in=devolucoes_qs).select_related("produto")

    context = {
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "devolucoes": devolucoes_qs[:200],
        "total_devolucoes": devolucoes_qs.count(),
        "valor_total": devolucoes_qs.aggregate(total=Sum("valor_total"))["total"] or 0,
        "quantidade_itens": itens_qs.aggregate(total=Sum("quantidade"))["total"] or 0,
        "produtos_mais_devolvidos": itens_qs.values("produto__nome").annotate(
            quantidade=Sum("quantidade"),
            valor=Sum("valor_total"),
        ).order_by("-quantidade")[:10],
    }
    return render(request, "relatorios/devolucoes.html", context)


def _linhas_devolucoes(data_inicio, data_fim):
    for devolucao in _devolucoes_periodo(data_inicio, data_fim):
        cliente = str(devolucao.venda.cliente) if devolucao.venda.cliente else "Cliente avulso"
        for item in devolucao.itens.all():
            yield [
                timezone.localtime(devolucao.data).strftime("%d/%m/%Y %H:%M"), devolucao.id, devolucao.venda_id,
                cliente, str(item.produto), item.quantidade, item.valor_total, devolucao.motivo, str(devolucao.usuario),
            ]


@login_required
@role_required(*RELATORIOS)
def devolucoes_csv(request):
    data_inicio, data_fim = _periodo_from_request(request)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="devolucoes_{data_inicio}_{data_fim}.csv"'
    response.write("\ufeff")
    writer = csv.writer(response, delimiter=";")
    writer.writerow(["Data", "Devolucao", "Venda", "Cliente", "Produto", "Quantidade", "Valor", "Motivo", "Responsavel"])
    for linha in _linhas_devolucoes(data_inicio, data_fim):
        linha[3] = _csv_safe(linha[3])
        linha[4] = _csv_safe(linha[4])
        linha[5] = str(linha[5]).replace(".", ",")
        linha[6] = str(linha[6]).replace(".", ",")
        linha[7] = _csv_safe(linha[7])
        linha[8] = _csv_safe(linha[8])
        writer.writerow(linha)
    return response


@login_required
@role_required(*RELATORIOS)
def devolucoes_imprimir(request):
    data_inicio, data_fim = _periodo_from_request(request)
    devolucoes_qs = _devolucoes_periodo(data_inicio, data_fim)
    linhas = list(_linhas_devolucoes(data_inicio, data_fim))
    for linha in linhas:
        linha[6] = f"R$ {linha[6]:.2f}"
    return render(request, "relatorios/exportacao_imprimir.html", {
        "titulo": "Relatorio de devolucoes", "subtitulo": "Itens devolvidos e impacto nas vendas",
        "data_inicio": data_inicio, "data_fim": data_fim, "gerado_em": timezone.localtime(),
        "cabecalhos": ["Data", "Devolucao", "Venda", "Cliente", "Produto", "Qtd", "Valor", "Motivo", "Responsavel"],
        "linhas": linhas,
        "resumos": [("Devolucoes", devolucoes_qs.count()), ("Valor devolvido", f'R$ {(devolucoes_qs.aggregate(total=Sum("valor_total"))["total"] or 0):.2f}')],
    })


@login_required
@role_required(*RELATORIOS)
def compras(request):
    data_inicio, data_fim = _periodo_from_request(request)
    entradas = _compras_periodo(data_inicio, data_fim)

    context = {
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "entradas": entradas[:100],
        "total_entradas": entradas.count(),
        "total_compras": entradas.aggregate(total=Sum("total_produtos"))["total"] or 0,
        "compras_por_fornecedor": entradas.values("fornecedor__razao_social").annotate(
            total=Sum("total_produtos"),
            quantidade=Count("id"),
        ).order_by("-total")[:10],
    }
    return render(request, "relatorios/compras.html", context)


@login_required
@role_required(*RELATORIOS)
def compras_csv(request):
    data_inicio, data_fim = _periodo_from_request(request)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="compras_{data_inicio}_{data_fim}.csv"'
    response.write("\ufeff")
    writer = csv.writer(response, delimiter=";")
    writer.writerow(["Entrada", "Documento", "Emissao", "Recebimento", "Fornecedor", "Filial", "Responsavel", "Total"])
    for entrada in _compras_periodo(data_inicio, data_fim).iterator():
        writer.writerow([
            entrada.id,
            _csv_safe(entrada.numero_documento),
            entrada.data_emissao.strftime("%d/%m/%Y") if entrada.data_emissao else "",
            timezone.localtime(entrada.data_recebimento).strftime("%d/%m/%Y %H:%M"),
            _csv_safe(entrada.fornecedor),
            _csv_safe(entrada.filial),
            _csv_safe(entrada.usuario),
            str(entrada.total_produtos).replace(".", ","),
        ])
    return response


@login_required
@role_required(*RELATORIOS)
def compras_imprimir(request):
    data_inicio, data_fim = _periodo_from_request(request)
    entradas = _compras_periodo(data_inicio, data_fim)
    context = {
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "entradas": entradas,
        "total_entradas": entradas.count(),
        "total_compras": entradas.aggregate(total=Sum("total_produtos"))["total"] or 0,
        "gerado_em": timezone.localtime(),
    }
    return render(request, "relatorios/compras_imprimir.html", context)


@login_required
@role_required(*RELATORIOS)
def caixas(request):
    data_inicio, data_fim, operador_id, caixas_qs = _caixas_filtrados(request)
    query_params = request.GET.copy()
    query_params["data_inicio"] = data_inicio.isoformat()
    query_params["data_fim"] = data_fim.isoformat()
    caixas_lista, diferenca_total = _preparar_caixas_conferencia(caixas_qs[:100])

    context = {
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "operador_id": operador_id,
        "operadores": _operadores_caixa(),
        "caixas_query": query_params.urlencode(),
        "caixas": caixas_lista,
        "caixas_abertos": caixas_qs.filter(status=StatusCaixa.ABERTO).count(),
        "caixas_fechados": caixas_qs.filter(status=StatusCaixa.FECHADO).count(),
        "caixas_conferidos": caixas_qs.filter(status=StatusCaixa.CONFERIDO).count(),
        "valor_inicial_total": caixas_qs.aggregate(total=Sum("valor_inicial"))["total"] or 0,
        "valor_final_total": caixas_qs.aggregate(total=Sum("valor_final"))["total"] or 0,
        "valor_conferido_total": caixas_qs.aggregate(total=Sum("valor_conferido"))["total"] or 0,
        "total_sangrias": Sangria.objects.filter(caixa__in=caixas_qs).aggregate(total=Sum("valor"))["total"] or 0,
        "total_suprimentos": Suprimento.objects.filter(caixa__in=caixas_qs).aggregate(total=Sum("valor"))["total"] or 0,
        "diferenca_total": diferenca_total,
        "resumo_por_operador": _resumo_caixas_por_operador(caixas_qs),
        "pagamentos_por_forma": PagamentoVenda.objects.filter(
            venda__caixa__in=caixas_qs,
            venda__status=StatusVenda.FINALIZADA,
        ).values("forma_pagamento__nome").annotate(total=Sum("valor")).order_by("forma_pagamento__nome"),
    }
    return render(request, "relatorios/caixas.html", context)


@login_required
@role_required(*RELATORIOS)
def caixas_csv(request):
    data_inicio, data_fim, operador_id, caixas_qs = _caixas_filtrados(request)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="caixas_{data_inicio}_{data_fim}.csv"'
    response.write("\ufeff")
    writer = csv.writer(response, delimiter=";")
    if operador_id:
        operador = _csv_safe(get_user_model().objects.filter(pk=operador_id).values_list("username", flat=True).first() or operador_id)
        writer.writerow(["Filtro operador", operador])
    writer.writerow([
        "Caixa", "Filial", "Operador", "Conferente", "Abertura", "Fechamento",
        "Valor inicial", "Valor declarado", "Valor conferido", "Diferenca", "Status",
    ])
    for caixa in caixas_qs.iterator():
        diferenca = ""
        if caixa.valor_final is not None and caixa.valor_conferido is not None:
            diferenca = str(caixa.valor_conferido - caixa.valor_final).replace(".", ",")
        writer.writerow([
            caixa.id,
            _csv_safe(caixa.filial),
            _csv_safe(caixa.usuario_abertura),
            _csv_safe(caixa.usuario_conferencia) if caixa.usuario_conferencia else "",
            timezone.localtime(caixa.data_abertura).strftime("%d/%m/%Y %H:%M"),
            timezone.localtime(caixa.data_fechamento).strftime("%d/%m/%Y %H:%M") if caixa.data_fechamento else "",
            str(caixa.valor_inicial).replace(".", ","),
            str(caixa.valor_final).replace(".", ",") if caixa.valor_final is not None else "",
            str(caixa.valor_conferido).replace(".", ",") if caixa.valor_conferido is not None else "",
            diferenca,
            caixa.get_status_display(),
        ])
    writer.writerow([])
    writer.writerow(["Resumo por operador"])
    writer.writerow(["Operador", "Caixas", "Vendas", "Total vendas", "Sangrias", "Suprimentos", "Saldo operacional", "Valor inicial", "Declarado", "Conferido", "Diferenca"])
    for item in _resumo_caixas_por_operador(caixas_qs):
        writer.writerow([
            _csv_safe(item["operador"]),
            item["caixas"],
            item["vendas"],
            _csv_money(item["total_vendas"]),
            _csv_money(item["sangrias"]),
            _csv_money(item["suprimentos"]),
            _csv_money(item["saldo_operacional"]),
            _csv_money(item["valor_inicial"]),
            _csv_money(item["valor_declarado"]),
            _csv_money(item["valor_conferido"]),
            _csv_money(item["diferenca"]),
        ])
    return response


@login_required
@role_required(*RELATORIOS)
def caixas_imprimir(request):
    data_inicio, data_fim, operador_id, caixas_qs = _caixas_filtrados(request)
    caixas_lista, diferenca_total = _preparar_caixas_conferencia(caixas_qs)
    context = {
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "operador_id": operador_id,
        "operador_selecionado": get_user_model().objects.filter(pk=operador_id).first() if operador_id.isdigit() else None,
        "caixas": caixas_lista,
        "total_caixas": caixas_qs.count(),
        "valor_inicial_total": caixas_qs.aggregate(total=Sum("valor_inicial"))["total"] or 0,
        "valor_final_total": caixas_qs.aggregate(total=Sum("valor_final"))["total"] or 0,
        "valor_conferido_total": caixas_qs.aggregate(total=Sum("valor_conferido"))["total"] or 0,
        "total_sangrias": Sangria.objects.filter(caixa__in=caixas_qs).aggregate(total=Sum("valor"))["total"] or 0,
        "total_suprimentos": Suprimento.objects.filter(caixa__in=caixas_qs).aggregate(total=Sum("valor"))["total"] or 0,
        "diferenca_total": diferenca_total,
        "resumo_por_operador": _resumo_caixas_por_operador(caixas_qs),
        "pagamentos_por_forma": PagamentoVenda.objects.filter(
            venda__caixa__in=caixas_qs,
            venda__status=StatusVenda.FINALIZADA,
        ).values("forma_pagamento__nome").annotate(total=Sum("valor")).order_by("forma_pagamento__nome"),
        "gerado_em": timezone.localtime(),
    }
    return render(request, "relatorios/caixas_imprimir.html", context)
