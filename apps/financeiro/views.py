import csv
import hashlib
import json
from collections import OrderedDict
from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Count, Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.http import url_has_allowed_host_and_scheme

from apps.accounts.models import PerfilUsuario, TipoPerfil
from apps.accounts.permissions import RELATORIOS, SISTEMA, has_role, role_required
from apps.auditoria.models import LogAuditoria
from apps.empresas.models import Empresa, Filial
from apps.fiscal.models import DocumentoFiscal, StatusDocumentoFiscal
from apps.vendas.models import PagamentoVenda, StatusVenda

from .forms import BaixaContaForm, CategoriaFinanceiraForm, ContaFinanceiraForm, ContaMovimentoFinanceiroForm, TransferenciaFinanceiraForm
from .adapters import carregar_adaptador_contabil, diagnosticar_adaptador_contabil, normalizar_retorno_exportacao
from .models import CategoriaFinanceira, ConciliacaoLancamentoFinanceiro, ContaFinanceira, ContaMovimentoFinanceiro, ExportacaoContabil, LancamentoFinanceiro, StatusContaFinanceira, StatusExportacaoContabil, TipoContaFinanceira, TipoLancamentoFinanceiro, TransferenciaFinanceira
from .services import baixar_conta, cancelar_conta, conciliar_lancamento, estornar_lancamento, realizar_transferencia


def _periodo_from_request(request):
    hoje = timezone.localdate()
    data_inicio = parse_date(request.GET.get("data_inicio") or "") or hoje.replace(day=1)
    data_fim = parse_date(request.GET.get("data_fim") or "") or hoje
    return data_inicio, data_fim


def _escopo_filiais_financeiro(request):
    filiais = Filial.objects.select_related("empresa").order_by("empresa__nome_fantasia", "nome")
    permite_consolidado = request.user.is_superuser
    empresa_id = None
    if not request.user.is_superuser:
        perfil = PerfilUsuario.objects.select_related("filial", "filial__empresa").filter(
            usuario=request.user, is_active=True, filial__isnull=False,
        ).first()
        if not perfil:
            raise PermissionDenied("Usuario sem filial financeira vinculada.")
        if perfil.tipo == TipoPerfil.ADMINISTRADOR:
            filiais = filiais.filter(empresa_id=perfil.filial.empresa_id)
            permite_consolidado = True
            empresa_id = perfil.filial.empresa_id
        else:
            filiais = filiais.filter(pk=perfil.filial_id)

    filial_parametro = (request.GET.get("filial") or "").strip()
    if filial_parametro:
        if not filial_parametro.isdigit() or not filiais.filter(pk=filial_parametro).exists():
            raise PermissionDenied("Filial fora do escopo permitido para este usuario.")
        filial_id = int(filial_parametro)
    elif permite_consolidado:
        filial_id = None
    else:
        filial_id = filiais.values_list("id", flat=True).first()
    return filiais, filial_id, permite_consolidado, empresa_id

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
    filiais, filial_id, permite_consolidado, empresa_id = _escopo_filiais_financeiro(request)
    contas_qs = ContaFinanceira.objects.select_related(
        "categoria", "filial", "fornecedor", "cliente"
    ).filter(vencimento__gte=data_inicio, vencimento__lte=data_fim)
    if filial_id:
        contas_qs = contas_qs.filter(filial_id=filial_id)
    elif empresa_id:
        contas_qs = contas_qs.filter(filial__empresa_id=empresa_id)
    if tipo:
        contas_qs = contas_qs.filter(tipo=tipo)
    if status:
        contas_qs = contas_qs.filter(status=status)
    if q:
        contas_qs = contas_qs.filter(descricao__icontains=q)
    return contas_qs, {
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "tipo": tipo,
        "status": status,
        "q": q,
        "filial_id": str(filial_id or ""),
        "filiais_opcoes": filiais,
        "permite_consolidado": permite_consolidado,
    }

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


def _fluxo_caixa_periodo(data_inicio, data_fim, filial_id=None, empresa_id=None):
    contas_qs = ContaFinanceira.objects.filter(vencimento__gte=data_inicio, vencimento__lte=data_fim)
    if filial_id:
        contas_qs = contas_qs.filter(filial_id=filial_id)
    elif empresa_id:
        contas_qs = contas_qs.filter(filial__empresa_id=empresa_id)
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


def _conciliacao_periodo(data_inicio, data_fim, filial_id=None, empresa_id=None):
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
    if filial_id:
        pagamentos_pdv = pagamentos_pdv.filter(venda__filial_id=filial_id)
    elif empresa_id:
        pagamentos_pdv = pagamentos_pdv.filter(venda__filial__empresa_id=empresa_id)
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
    if filial_id:
        contas_baixadas = contas_baixadas.filter(filial_id=filial_id)
    elif empresa_id:
        contas_baixadas = contas_baixadas.filter(filial__empresa_id=empresa_id)
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
def _resultado_financeiro_periodo(data_inicio, data_fim, filial_id=None, empresa_id=None):
    lancamentos = (
        LancamentoFinanceiro.objects.select_related("conta", "conta__filial", "conta_financeira", "conta_financeira__categoria")
        .filter(data__gte=data_inicio, data__lte=data_fim)
        .exclude(origem="TRANSFERENCIA")
    )
    if filial_id:
        lancamentos = lancamentos.filter(conta__filial_id=filial_id)
    elif empresa_id:
        lancamentos = lancamentos.filter(conta__filial__empresa_id=empresa_id)
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
    contas_movimento = ContaMovimentoFinanceiro.objects.select_related("filial", "filial__empresa").filter(ativa=True)
    if filial_id:
        contas_movimento = contas_movimento.filter(filial_id=filial_id)
    elif empresa_id:
        contas_movimento = contas_movimento.filter(filial__empresa_id=empresa_id)
    for conta in contas_movimento:
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

    conciliacao_bancaria = _resumo_conciliacao_periodo(data_inicio, data_fim, filial_id, empresa_id)
    integracao_fiscal = _resumo_integracao_fiscal(data_inicio, data_fim, filial_id, empresa_id)
    return {
        "receitas": receitas,
        "despesas": despesas,
        "resultado": receitas - despesas,
        "por_origem": por_origem,
        "por_conta": por_conta,
        "por_categoria": por_categoria,
        "saldos_contas": saldos_contas,
        "balancete_contas": _balancete_contas_periodo(data_inicio, data_fim, filial_id, empresa_id),
        "dre_gerencial": _dre_gerencial(receitas, despesas, por_categoria),
        "conciliacao_bancaria": conciliacao_bancaria,
        "integracao_fiscal": integracao_fiscal,
        "pacote_contabil": _pacote_contabil_gerencial(data_inicio, data_fim, receitas, despesas, conciliacao_bancaria, filial_id, empresa_id),
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


def _balancete_contas_periodo(data_inicio, data_fim, filial_id=None, empresa_id=None):
    linhas = []
    contas = ContaMovimentoFinanceiro.objects.select_related("filial", "filial__empresa").filter(ativa=True)
    if filial_id:
        contas = contas.filter(filial_id=filial_id)
    elif empresa_id:
        contas = contas.filter(filial__empresa_id=empresa_id)
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



def _resumo_conciliacao_periodo(data_inicio, data_fim, filial_id=None, empresa_id=None):
    lancamentos = LancamentoFinanceiro.objects.filter(data__range=(data_inicio, data_fim))
    if filial_id:
        lancamentos = lancamentos.filter(conta__filial_id=filial_id)
    elif empresa_id:
        lancamentos = lancamentos.filter(conta__filial__empresa_id=empresa_id)
    total_lancamentos = lancamentos.count()
    total_valor = lancamentos.aggregate(total=Sum("valor"))["total"] or Decimal("0.00")
    conciliados_qs = lancamentos.filter(conciliacao_bancaria__isnull=False)
    conciliados = conciliados_qs.count()
    valor_conciliado = conciliados_qs.aggregate(total=Sum("valor"))["total"] or Decimal("0.00")
    percentual = Decimal("0.00")
    if total_lancamentos:
        percentual = (Decimal(conciliados) / Decimal(total_lancamentos) * Decimal("100.00")).quantize(Decimal("0.01"))
    por_conta = []
    contas_conciliacao = ContaMovimentoFinanceiro.objects.select_related("filial").filter(
        lancamentos__data__range=(data_inicio, data_fim)
    ).distinct()
    if filial_id:
        contas_conciliacao = contas_conciliacao.filter(filial_id=filial_id)
    elif empresa_id:
        contas_conciliacao = contas_conciliacao.filter(filial__empresa_id=empresa_id)
    for conta in contas_conciliacao:
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


def _resumo_integracao_fiscal(data_inicio, data_fim, filial_id=None, empresa_id=None):
    documentos = (
        DocumentoFiscal.objects.select_related("filial", "venda", "pedido_online")
        .filter(criado_em__date__range=(data_inicio, data_fim))
        .exclude(status=StatusDocumentoFiscal.CANCELADO)
    )
    if filial_id:
        documentos = documentos.filter(filial_id=filial_id)
    elif empresa_id:
        documentos = documentos.filter(filial__empresa_id=empresa_id)
    documentos_venda = documentos.filter(venda__isnull=False)
    vendas_documentadas = {
        item["venda_id"]: item
        for item in documentos_venda.values("venda_id", "filial__nome")
        .annotate(valor_fiscal=Sum("valor_total"), documentos=Count("id"))
    }
    entradas_qs = LancamentoFinanceiro.objects.filter(
        data__range=(data_inicio, data_fim), tipo=TipoLancamentoFinanceiro.ENTRADA,
        pagamento_venda__venda_id__isnull=False,
    )
    if filial_id:
        entradas_qs = entradas_qs.filter(conta__filial_id=filial_id)
    elif empresa_id:
        entradas_qs = entradas_qs.filter(conta__filial__empresa_id=empresa_id)
    entradas_venda = {
        item["pagamento_venda__venda_id"]: item
        for item in entradas_qs.values(
            "pagamento_venda__venda_id", "pagamento_venda__venda__filial__nome"
        ).annotate(valor_financeiro=Sum("valor"))
    }
    divergencias = []
    conciliadas = 0
    for venda_id, fiscal in vendas_documentadas.items():
        valor_fiscal = fiscal["valor_fiscal"] or Decimal("0.00")
        entrada = entradas_venda.get(venda_id)
        valor_financeiro = entrada["valor_financeiro"] if entrada else Decimal("0.00")
        diferenca = valor_financeiro - valor_fiscal
        if abs(diferenca) <= Decimal("0.01"):
            conciliadas += 1
            continue
        divergencias.append({
            "venda_id": venda_id, "filial": fiscal["filial__nome"],
            "valor_fiscal": valor_fiscal, "valor_financeiro": valor_financeiro,
            "diferenca": diferenca,
            "situacao": "Sem lancamento financeiro" if not valor_financeiro else "Valores divergentes",
        })
    vendas_sem_documento = sorted(set(entradas_venda) - set(vendas_documentadas))
    for venda_id in vendas_sem_documento:
        entrada = entradas_venda[venda_id]
        divergencias.append({
            "venda_id": venda_id,
            "filial": entrada["pagamento_venda__venda__filial__nome"],
            "valor_fiscal": Decimal("0.00"),
            "valor_financeiro": entrada["valor_financeiro"],
            "diferenca": entrada["valor_financeiro"],
            "situacao": "Sem documento fiscal",
        })
    status = {
        item["status"]: {"quantidade": item["quantidade"], "valor": item["valor"] or Decimal("0.00")}
        for item in documentos.values("status").annotate(quantidade=Count("id"), valor=Sum("valor_total"))
    }
    return {
        "contrato": "financial_fiscal_reconciliation_v1",
        "documentos": documentos.count(), "documentos_venda": documentos_venda.count(),
        "documentos_pedido_online": documentos.filter(pedido_online__isnull=False).count(),
        "valor_fiscal": documentos.aggregate(total=Sum("valor_total"))["total"] or Decimal("0.00"),
        "vendas_com_lancamento": len(entradas_venda), "vendas_conciliadas": conciliadas,
        "vendas_sem_documento": len(vendas_sem_documento),
        "vendas_sem_documento_ids": vendas_sem_documento[:100],
        "divergencias": divergencias[:100], "total_divergencias": len(divergencias), "status": status,
    }


def _integracao_fiscal_json(resumo):
    return {
        **resumo,
        "valor_fiscal": _valor_monetario_json(resumo["valor_fiscal"]),
        "status": {
            chave: {"quantidade": valor["quantidade"], "valor": _valor_monetario_json(valor["valor"])}
            for chave, valor in resumo["status"].items()
        },
        "divergencias": [
            {**linha, "valor_fiscal": _valor_monetario_json(linha["valor_fiscal"]),
             "valor_financeiro": _valor_monetario_json(linha["valor_financeiro"]),
             "diferenca": _valor_monetario_json(linha["diferenca"])}
            for linha in resumo["divergencias"]
        ],
    }

def _pacote_contabil_gerencial(data_inicio, data_fim, receitas, despesas, conciliacao_bancaria, filial_id=None, empresa_id=None):
    lancamentos_periodo = LancamentoFinanceiro.objects.filter(data__gte=data_inicio, data__lte=data_fim)
    if filial_id:
        lancamentos_periodo = lancamentos_periodo.filter(conta__filial_id=filial_id)
    elif empresa_id:
        lancamentos_periodo = lancamentos_periodo.filter(conta__filial__empresa_id=empresa_id)
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
    pagina = Paginator(contas_qs, 50).get_page(request.GET.get("page"))
    context = {
        **filtros,
        **_resumo_contas(contas_qs),
        "tipos": TipoContaFinanceira.choices,
        "status_choices": StatusContaFinanceira.choices,
        "contas": pagina,
        "page_obj": pagina,
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
    filiais, filial_id, permite_consolidado, empresa_id = _escopo_filiais_financeiro(request)
    linhas = _fluxo_caixa_periodo(data_inicio, data_fim, filial_id, empresa_id)
    context = {
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "filiais_opcoes": filiais,
        "filial_id": str(filial_id or ""),
        "permite_consolidado": permite_consolidado,
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
    _, filial_id, _, empresa_id = _escopo_filiais_financeiro(request)
    linhas = _fluxo_caixa_periodo(data_inicio, data_fim, filial_id, empresa_id)
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
    filiais, filial_id, permite_consolidado, empresa_id = _escopo_filiais_financeiro(request)
    linhas = _conciliacao_periodo(data_inicio, data_fim, filial_id, empresa_id)
    context = {
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "filiais_opcoes": filiais,
        "filial_id": str(filial_id or ""),
        "permite_consolidado": permite_consolidado,
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
    _, filial_id, _, empresa_id = _escopo_filiais_financeiro(request)
    linhas = _conciliacao_periodo(data_inicio, data_fim, filial_id, empresa_id)
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
    filiais, filial_id, permite_consolidado, empresa_id = _escopo_filiais_financeiro(request)
    resultado = _resultado_financeiro_periodo(data_inicio, data_fim, filial_id, empresa_id)
    exportacoes = ExportacaoContabil.objects.select_related("empresa", "filial", "usuario")
    if filial_id:
        exportacoes = exportacoes.filter(filial_id=filial_id)
    elif empresa_id:
        exportacoes = exportacoes.filter(empresa_id=empresa_id)
    elif not request.user.is_superuser:
        exportacoes = exportacoes.none()
    return render(request, "financeiro/resultado.html", {
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "filiais": filiais,
        "filial_id": filial_id,
        "permite_consolidado": permite_consolidado,
        "adaptador_contabil": diagnosticar_adaptador_contabil(),
        "pode_enviar_contabil": has_role(request.user, SISTEMA),
        "exportacoes_contabeis": exportacoes[:10],
        **resultado,
    })

@login_required
@role_required(*RELATORIOS)
def resultado_financeiro_csv(request):
    data_inicio, data_fim = _periodo_from_request(request)
    filiais, filial_id, permite_consolidado, empresa_id = _escopo_filiais_financeiro(request)
    resultado = _resultado_financeiro_periodo(data_inicio, data_fim, filial_id, empresa_id)
    filial = filiais.filter(pk=filial_id).first() if filial_id else None
    def valor_csv(valor):
        return f"{valor:.2f}".replace(".", ",")

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="resultado_financeiro_{data_inicio}_{data_fim}.csv"'
    response.write("\ufeff")
    writer = csv.writer(response, delimiter=";")
    writer.writerow(["Filial", filial.nome if filial else "Todas as filiais permitidas"])
    writer.writerow([])
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
    fiscal = resultado["integracao_fiscal"]
    writer.writerow([])
    writer.writerow(["Conferencia fiscal x financeiro"])
    writer.writerow(["Contrato", fiscal["contrato"]])
    writer.writerow(["Documentos fiscais", fiscal["documentos"], valor_csv(fiscal["valor_fiscal"])])
    writer.writerow(["Vendas conciliadas", fiscal["vendas_conciliadas"]])
    writer.writerow(["Vendas sem documento fiscal", fiscal["vendas_sem_documento"]])
    writer.writerow(["Divergencias fiscais", fiscal["total_divergencias"]])
    writer.writerow(["Venda", "Filial", "Valor fiscal", "Valor financeiro", "Diferenca", "Situacao"])
    for linha in fiscal["divergencias"]:
        writer.writerow([linha["venda_id"], linha["filial"], valor_csv(linha["valor_fiscal"]), valor_csv(linha["valor_financeiro"]), valor_csv(linha["diferenca"]), linha["situacao"]])
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


def _payload_pacote_contabil(data_inicio, data_fim, filiais, filial_id, empresa_id, resultado):
    filial = filiais.filter(pk=filial_id).first() if filial_id else None
    empresa = filial.empresa if filial else Empresa.objects.filter(pk=empresa_id).first()
    pacote = resultado["pacote_contabil"]
    return {
        "contrato": "financial_accounting_package_v1",
        "periodo": {"inicio": data_inicio.isoformat(), "fim": data_fim.isoformat()},
        "empresa": {"id": empresa.pk, "razao_social": empresa.razao_social, "cnpj": empresa.cnpj} if empresa else None,
        "filial": {"id": filial.pk, "nome": filial.nome, "cnpj": filial.cnpj} if filial else None,
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
        "integracao_fiscal": _integracao_fiscal_json(resultado["integracao_fiscal"]),
        "pacote_contabil": pacote,
        "alertas": pacote["alertas"],
        "observacao": "Pacote gerencial de conferencia interna; nao substitui SPED, ECD, ECF ou obrigacoes oficiais.",
    }


@login_required
@role_required(*RELATORIOS)
def resultado_pacote_contabil_json(request):
    data_inicio, data_fim = _periodo_from_request(request)
    filiais, filial_id, _, empresa_id = _escopo_filiais_financeiro(request)
    resultado = _resultado_financeiro_periodo(data_inicio, data_fim, filial_id, empresa_id)
    return JsonResponse(_payload_pacote_contabil(data_inicio, data_fim, filiais, filial_id, empresa_id, resultado))


@login_required
@role_required(*RELATORIOS)
def diagnostico_contabil_json(request):
    diagnostico = diagnosticar_adaptador_contabil()
    diagnostico["envio_permitido"] = has_role(request.user, SISTEMA)
    return JsonResponse(diagnostico)


@login_required
@role_required(*SISTEMA)
def enviar_pacote_contabil(request):
    if request.method != "POST":
        raise PermissionDenied("O envio contábil exige confirmação administrativa.")
    data_inicio, data_fim = _periodo_from_request(request)
    filiais, filial_id, _, empresa_id = _escopo_filiais_financeiro(request)
    filial = filiais.filter(pk=filial_id).select_related("empresa").first() if filial_id else None
    empresa = filial.empresa if filial else Empresa.objects.filter(pk=empresa_id).first()
    destino = f"/financeiro/resultado/?data_inicio={data_inicio}&data_fim={data_fim}" + (f"&filial={filial_id}" if filial_id else "")
    if not empresa:
        messages.error(request, "Selecione uma filial antes de enviar; não é permitido misturar empresas no mesmo pacote contábil.")
        return redirect(destino)

    resultado = _resultado_financeiro_periodo(data_inicio, data_fim, filial_id, empresa.pk)
    payload = _payload_pacote_contabil(data_inicio, data_fim, filiais, filial_id, empresa.pk, resultado)
    payload_bytes = json.dumps(payload, cls=DjangoJSONEncoder, sort_keys=True, ensure_ascii=False).encode("utf-8")
    payload_sha256 = hashlib.sha256(payload_bytes).hexdigest()
    chave = hashlib.sha256(
        f"{empresa.pk}:{filial_id or 'consolidado'}:{data_inicio}:{data_fim}:{payload_sha256}".encode("utf-8")
    ).hexdigest()
    diagnostico = diagnosticar_adaptador_contabil()
    if not diagnostico["carregavel"]:
        messages.error(request, diagnostico["erro"] or "Configure e homologue um adaptador contábil antes do envio.")
        return redirect(destino)

    exportacao, criada = ExportacaoContabil.objects.get_or_create(
        chave_idempotencia=chave,
        defaults={
            "empresa": empresa,
            "filial": filial,
            "data_inicio": data_inicio,
            "data_fim": data_fim,
            "payload_sha256": payload_sha256,
            "provedor": diagnostico["provedor"],
            "usuario": request.user,
        },
    )
    if not criada and exportacao.status == StatusExportacaoContabil.ENVIADO:
        messages.info(request, f"Este fechamento já foi enviado. Protocolo: {exportacao.protocolo}.")
        return redirect(destino)

    try:
        retorno = carregar_adaptador_contabil().exportar(payload=payload, chave_idempotencia=chave)
        normalizado = normalizar_retorno_exportacao(retorno)
        exportacao.status = normalizado.status
        exportacao.protocolo = normalizado.protocolo
        exportacao.mensagem = normalizado.mensagem
    except Exception as exc:
        exportacao.status = StatusExportacaoContabil.ERRO
        exportacao.mensagem = str(exc)[:2000]
    exportacao.usuario = request.user
    exportacao.save(update_fields=["status", "protocolo", "mensagem", "usuario", "atualizado_em"])
    LogAuditoria.objects.create(
        usuario=request.user,
        modulo="financeiro",
        acao="EXPORTACAO_CONTABIL",
        descricao=f"Exportação contábil #{exportacao.pk}: {exportacao.status}. Período {data_inicio} a {data_fim}.",
        objeto_tipo="ExportacaoContabil",
        objeto_id=str(exportacao.pk),
        ip=request.META.get("REMOTE_ADDR"),
    )
    if exportacao.status == StatusExportacaoContabil.ENVIADO:
        messages.success(request, f"Pacote contábil enviado. Protocolo: {exportacao.protocolo}.")
    elif exportacao.status == StatusExportacaoContabil.PENDENTE:
        messages.warning(request, "O provedor recebeu o pacote e deixou o processamento pendente.")
    else:
        messages.error(request, exportacao.mensagem or "O provedor não aceitou o pacote contábil.")
    return redirect(destino)

def _lancamentos_filtrados(request):
    data_inicio, data_fim = _periodo_from_request(request)
    conta_id = request.GET.get("conta", "").strip()
    tipo = request.GET.get("tipo", "").strip()
    filiais, filial_id, permite_consolidado, empresa_id = _escopo_filiais_financeiro(request)
    lancamentos = LancamentoFinanceiro.objects.select_related(
        "conta", "conta__filial", "conta_financeira", "usuario", "estorno_de",
        "pagamento_venda", "sangria", "suprimento",
    ).filter(data__gte=data_inicio, data__lte=data_fim)
    if filial_id:
        lancamentos = lancamentos.filter(conta__filial_id=filial_id)
    elif empresa_id:
        lancamentos = lancamentos.filter(conta__filial__empresa_id=empresa_id)
    if conta_id.isdigit():
        lancamentos = lancamentos.filter(conta_id=conta_id)
    if tipo:
        lancamentos = lancamentos.filter(tipo=tipo)
    return lancamentos, {
        "data_inicio": data_inicio, "data_fim": data_fim, "conta_id": conta_id,
        "filial_id": str(filial_id or ""), "tipo": tipo,
    }, filiais, permite_consolidado


def _lancamentos_conciliacao_filtrados(request):
    data_inicio, data_fim = _periodo_from_request(request)
    filiais, filial_id, permite_consolidado, empresa_id = _escopo_filiais_financeiro(request)
    filtros = {
        "data_inicio": data_inicio, "data_fim": data_fim, "filial_id": str(filial_id or ""),
        "conta": request.GET.get("conta", "").strip(),
        "status": request.GET.get("status", "").strip(), "q": request.GET.get("q", "").strip(),
    }
    lancamentos = LancamentoFinanceiro.objects.select_related(
        "conta", "conta__filial", "conta__filial__empresa", "usuario",
        "conciliacao_bancaria", "conciliacao_bancaria__usuario",
    ).filter(data__range=(data_inicio, data_fim))
    if filial_id:
        lancamentos = lancamentos.filter(conta__filial_id=filial_id)
    elif empresa_id:
        lancamentos = lancamentos.filter(conta__filial__empresa_id=empresa_id)
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
    return lancamentos, filtros, filiais, permite_consolidado

@login_required
@role_required(*RELATORIOS)
def conciliacao_bancaria(request):
    lancamentos, filtros, filiais, permite_consolidado = _lancamentos_conciliacao_filtrados(request)
    total = lancamentos.count()
    conciliados = lancamentos.filter(conciliacao_bancaria__isnull=False).count()
    pagina = Paginator(lancamentos, 50).get_page(request.GET.get("page"))
    query = request.GET.copy()
    query.pop("page", None)
    return render(request, "financeiro/conciliacao_bancaria.html", {
        **filtros,
        "pagina": pagina,
        "query_sem_pagina": query.urlencode(),
        "filiais_opcoes": filiais,
        "permite_consolidado": permite_consolidado,
        "contas_opcoes": ContaMovimentoFinanceiro.objects.filter(ativa=True, filial__in=filiais).select_related("filial"),
        "total": total,
        "conciliados": conciliados,
        "pendentes": total - conciliados,
    })


@login_required
@role_required(*SISTEMA)
def conciliar_lancamento_view(request, pk):
    filiais, _, _, _ = _escopo_filiais_financeiro(request)
    lancamento = get_object_or_404(LancamentoFinanceiro.objects.filter(conta__filial__in=filiais), pk=pk)
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
    lancamentos, filtros, filiais, permite_consolidado = _lancamentos_conciliacao_filtrados(request)
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
    lancamentos, filtros, filiais, permite_consolidado = _lancamentos_filtrados(request)
    total_entradas = lancamentos.filter(tipo=TipoLancamentoFinanceiro.ENTRADA).aggregate(total=Sum("valor"))["total"] or 0
    total_saidas = lancamentos.filter(tipo=TipoLancamentoFinanceiro.SAIDA).aggregate(total=Sum("valor"))["total"] or 0
    pagina = Paginator(lancamentos, 50).get_page(request.GET.get("page"))
    return render(request, "financeiro/livro.html", {
        **filtros,
        "lancamentos": pagina,
        "page_obj": pagina,
        "contas_opcoes": ContaMovimentoFinanceiro.objects.filter(ativa=True, filial__in=filiais).select_related("filial"),
        "filiais_opcoes": filiais.filter(is_active=True),
        "permite_consolidado": permite_consolidado,
        "tipos_lancamento": TipoLancamentoFinanceiro.choices,
        "total_entradas": total_entradas,
        "total_saidas": total_saidas,
        "saldo_periodo": total_entradas - total_saidas,
    })


@login_required
@role_required(*RELATORIOS)
def livro_financeiro_csv(request):
    lancamentos, filtros, filiais, permite_consolidado = _lancamentos_filtrados(request)
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
        form = ContaFinanceiraForm(request.POST, instance=conta, user=request.user)
        if form.is_valid():
            nova_conta = form.save(commit=False)
            if not nova_conta.pk:
                nova_conta.usuario = request.user
            nova_conta.save()
            messages.success(request, "Conta financeira salva.")
            return redirect("financeiro:contas")
    else:
        form = ContaFinanceiraForm(instance=conta, user=request.user)
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
