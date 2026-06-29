from django.contrib.auth.decorators import login_required
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Sum
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_date

from apps.compras.models import EntradaCompra, StatusEntradaCompra
from apps.estoque.models import Estoque, MovimentacaoEstoque, PerdaEstoque, TipoMovimentacaoEstoque
from apps.pdv.models import Caixa, StatusCaixa
from apps.produtos.models import Produto
from apps.vendas.models import ItemVenda, StatusVenda, Venda


@login_required
def dashboard(request):
    vendas_finalizadas = Venda.objects.filter(status=StatusVenda.FINALIZADA)
    context = {
        "total_produtos": Produto.all_objects.count(),
        "produtos_ativos": Produto.objects.count(),
        "estoque_baixo": Estoque.objects.filter(quantidade_atual__lte=F("produto__estoque_minimo")).count(),
        "caixas_abertos": Caixa.objects.filter(status=StatusCaixa.ABERTO).count(),
        "total_vendas": vendas_finalizadas.count(),
        "faturamento": vendas_finalizadas.aggregate(total=Sum("total_liquido"))["total"] or 0,
        "ultimos_caixas": Caixa.objects.select_related("filial", "usuario_abertura").order_by("-data_abertura")[:5],
        "produtos_por_categoria": Produto.objects.values("categoria__nome").annotate(total=Count("id")).order_by("-total")[:6],
    }
    return render(request, "relatorios/dashboard.html", context)


def _periodo_from_request(request):
    hoje = timezone.localdate()
    data_inicio = parse_date(request.GET.get("data_inicio") or "") or hoje.replace(day=1)
    data_fim = parse_date(request.GET.get("data_fim") or "") or hoje
    return data_inicio, data_fim


@login_required
def vendas(request):
    data_inicio, data_fim = _periodo_from_request(request)
    vendas_qs = Venda.objects.filter(
        status=StatusVenda.FINALIZADA,
        data__date__gte=data_inicio,
        data__date__lte=data_fim,
    ).select_related("filial", "caixa", "cliente", "usuario")

    itens_qs = ItemVenda.objects.filter(venda__in=vendas_qs).select_related("produto")
    lucro_expr = ExpressionWrapper(
        F("total") - (F("custo_unitario_no_momento") * F("quantidade")),
        output_field=DecimalField(max_digits=12, decimal_places=2),
    )

    context = {
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "vendas": vendas_qs[:100],
        "total_vendas": vendas_qs.count(),
        "faturamento": vendas_qs.aggregate(total=Sum("total_liquido"))["total"] or 0,
        "descontos": vendas_qs.aggregate(total=Sum("desconto"))["total"] or 0,
        "lucro_estimado": itens_qs.aggregate(total=Sum(lucro_expr))["total"] or 0,
        "produtos_mais_vendidos": itens_qs.values("produto__nome").annotate(
            quantidade=Sum("quantidade"),
            total=Sum("total"),
        ).order_by("-quantidade")[:10],
    }
    return render(request, "relatorios/vendas.html", context)


@login_required
def estoque_baixo(request):
    estoques = Estoque.objects.select_related("produto", "filial", "produto__categoria").filter(
        quantidade_atual__lte=F("produto__estoque_minimo"),
        produto__is_active=True,
    ).order_by("produto__nome", "filial__nome")
    return render(request, "relatorios/estoque_baixo.html", {"estoques": estoques})


@login_required
def movimentacoes_estoque(request):
    data_inicio, data_fim = _periodo_from_request(request)
    tipo = request.GET.get("tipo") or ""
    movimentacoes = MovimentacaoEstoque.objects.filter(
        data__date__gte=data_inicio,
        data__date__lte=data_fim,
    ).select_related("produto", "filial", "usuario").order_by("-data")
    if tipo:
        movimentacoes = movimentacoes.filter(tipo=tipo)

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
def perdas(request):
    data_inicio, data_fim = _periodo_from_request(request)
    perdas_qs = PerdaEstoque.objects.filter(
        data__date__gte=data_inicio,
        data__date__lte=data_fim,
    ).select_related("produto", "produto__categoria", "filial", "usuario")

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
def compras(request):
    data_inicio, data_fim = _periodo_from_request(request)
    entradas = EntradaCompra.objects.filter(
        status=StatusEntradaCompra.FINALIZADA,
        data_recebimento__date__gte=data_inicio,
        data_recebimento__date__lte=data_fim,
    ).select_related("fornecedor", "filial", "usuario")

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
def caixas(request):
    data_inicio, data_fim = _periodo_from_request(request)
    caixas_qs = Caixa.objects.filter(
        data_abertura__date__gte=data_inicio,
        data_abertura__date__lte=data_fim,
    ).select_related("filial", "usuario_abertura", "usuario_fechamento")

    context = {
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "caixas": caixas_qs[:100],
        "caixas_abertos": caixas_qs.filter(status=StatusCaixa.ABERTO).count(),
        "caixas_fechados": caixas_qs.filter(status=StatusCaixa.FECHADO).count(),
        "valor_inicial_total": caixas_qs.aggregate(total=Sum("valor_inicial"))["total"] or 0,
        "valor_final_total": caixas_qs.aggregate(total=Sum("valor_final"))["total"] or 0,
    }
    return render(request, "relatorios/caixas.html", context)
