import csv
import hashlib
import json
from datetime import date
from io import BytesIO, StringIO
from zipfile import ZIP_DEFLATED, ZipFile
from collections import OrderedDict
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
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
from django.views.decorators.http import require_GET

from apps.accounts.models import PerfilUsuario, TipoPerfil
from apps.accounts.permissions import ADMINISTRACAO, CONTABILIDADE, RELATORIOS, SISTEMA, has_role, role_required
from apps.auditoria.models import LogAuditoria
from apps.empresas.models import Empresa, Filial
from apps.fiscal.models import (
    CartaCorrecaoFiscal,
    DocumentoDFeRecebido,
    DocumentoFiscal,
    EventoDFeRecebido,
    EvidenciaFiscal,
    ManifestacaoDestinatario,
    StatusDocumentoFiscal,
    TipoEvidenciaFiscal,
)
from apps.fiscal.pacote_contabil import analisar_xml_nfe, data_competencia_documento
from apps.estoque.models import Estoque, FechamentoEstoqueContabil
from apps.vendas.models import PagamentoVenda, StatusVenda

from .forms import AlocacaoRecebivelForm, AmostraContabilForm, BaixaContaForm, CategoriaFinanceiraForm, CentroCustoForm, ContratoIntegracaoContabilForm, ContaContabilForm, ContaFinanceiraForm, ContaMovimentoFinanceiroForm, ImportacaoExtratoFinanceiroForm, RegraLiquidacaoEletronicaForm, TransferenciaFinanceiraForm
from .adapters import carregar_adaptador_contabil, diagnosticar_adaptador_contabil, normalizar_retorno_exportacao
from .models import AceiteAmostraContabil, CategoriaFinanceira, CentroCusto, ContaContabil, ConciliacaoLancamentoFinanceiro, ContaFinanceira, ContaMovimentoFinanceiro, ChaveIntegracaoContabil, ContratoIntegracaoContabil, ExportacaoContabil, ImportacaoExtratoFinanceiro, ItemExtratoFinanceiro, LancamentoFinanceiro, RecebivelEletronico, RegraLiquidacaoEletronica, StatusContaFinanceira, StatusContratoIntegracaoContabil, StatusExportacaoContabil, StatusItemExtratoFinanceiro, StatusRecebivelEletronico, TipoContaFinanceira, TipoLancamentoFinanceiro, TransferenciaFinanceira
from .services import baixar_conta, cancelar_conta, conciliar_lancamento, estornar_lancamento, realizar_transferencia
from .services_conciliacao import conciliar_item_extrato, importar_extrato
from .services_recebiveis import candidatos_recebivel_item, conciliar_recebivel_com_item, sincronizar_recebiveis
from .reconciliacao_contabil import gerar_reconciliacao_operacional
from .contrato_contabil import registrar_contrato_contabil, resumo_contrato_contabil
from .amostra_contabil import registrar_aceite_amostra, validar_amostra_contabil


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
            raise PermissionDenied("Usuário sem filial financeira vinculada.")
        if perfil.tipo in {TipoPerfil.ADMINISTRADOR, TipoPerfil.CONTABILIDADE}:
            filiais = filiais.filter(empresa_id=perfil.filial.empresa_id)
            permite_consolidado = True
            empresa_id = perfil.filial.empresa_id
        else:
            filiais = filiais.filter(pk=perfil.filial_id)

    filial_parametro = (request.GET.get("filial") or "").strip()
    if filial_parametro:
        if not filial_parametro.isdigit() or not filiais.filter(pk=filial_parametro).exists():
            raise PermissionDenied("Filial fora do escopo permitido para este usuário.")
        filial_id = int(filial_parametro)
    elif permite_consolidado:
        filial_id = None
    else:
        filial_id = filiais.values_list("id", flat=True).first()
    return filiais, filial_id, permite_consolidado, empresa_id

def _queryset_no_escopo_financeiro(request, queryset, campo_filial="filial"):
    filiais, _filial_id, _permite_consolidado, _empresa_id = _escopo_filiais_financeiro(request)
    return queryset.filter(**{f"{campo_filial}__in": filiais})


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
        "categoria", "centro_custo", "filial", "fornecedor", "cliente"
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
        LancamentoFinanceiro.objects.select_related("conta", "conta__filial", "conta_financeira", "conta_financeira__categoria", "centro_custo", "conta_contabil")
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

    por_centro_custo = []
    acumulado_centro = OrderedDict()
    for lancamento in lancamentos:
        centro = lancamento.centro_custo
        chave = centro.pk if centro else None
        linha = acumulado_centro.setdefault(
            chave,
            {
                "codigo": centro.codigo if centro else "-",
                "centro_custo": centro.nome if centro else "Sem centro de custo",
                "receitas": Decimal("0.00"),
                "despesas": Decimal("0.00"),
            },
        )
        if lancamento.tipo == TipoLancamentoFinanceiro.ENTRADA:
            linha["receitas"] += lancamento.valor
        else:
            linha["despesas"] += lancamento.valor
    for linha in acumulado_centro.values():
        linha["resultado"] = linha["receitas"] - linha["despesas"]
        por_centro_custo.append(linha)

    por_conta_contabil = []
    acumulado_contabil = OrderedDict()
    for lancamento in lancamentos:
        conta_contabil = lancamento.conta_contabil
        chave = conta_contabil.pk if conta_contabil else None
        linha = acumulado_contabil.setdefault(
            chave,
            {
                "codigo": conta_contabil.codigo if conta_contabil else "-",
                "conta_contabil": conta_contabil.nome if conta_contabil else "Sem conta contábil",
                "natureza": conta_contabil.get_natureza_display() if conta_contabil else "-",
                "receitas": Decimal("0.00"),
                "despesas": Decimal("0.00"),
            },
        )
        if lancamento.tipo == TipoLancamentoFinanceiro.ENTRADA:
            linha["receitas"] += lancamento.valor
        else:
            linha["despesas"] += lancamento.valor
    for linha in acumulado_contabil.values():
        linha["resultado"] = linha["receitas"] - linha["despesas"]
        por_conta_contabil.append(linha)

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
        "por_centro_custo": por_centro_custo,
        "por_conta_contabil": por_conta_contabil,
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
            "observacao": "Entradas realizadas no livro financeiro, sem transferências internas.",
        },
        {
            "grupo": "Despesas operacionais",
            "valor": despesas,
            "natureza": "saida",
            "observacao": "Saidas realizadas no livro financeiro, sem transferências internas.",
        },
        {
            "grupo": "Resultado operacional",
            "valor": resultado,
            "natureza": "resultado",
            "observacao": "Receitas menos despesas no período filtrado.",
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
            "situacao": "Sem lançamento financeiro" if not valor_financeiro else "Valores divergentes",
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
    empresa = Empresa.objects.filter(pk=empresa_id).first()
    contrato_contabil = resumo_contrato_contabil(empresa)
    envio_contabil_liberado = bool(
        contrato_contabil.get("validado")
        and contrato_contabil.get("formato_entrega") == "ADAPTADOR_SERVIDOR_V1"
    )
    return render(request, "financeiro/resultado.html", {
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "filiais": filiais,
        "filial_id": filial_id,
        "permite_consolidado": permite_consolidado,
        "adaptador_contabil": diagnosticar_adaptador_contabil(),
        "contrato_integracao_contabil": contrato_contabil,
        "pode_enviar_contabil": has_role(request.user, SISTEMA),
        "envio_contabil_liberado": envio_contabil_liberado,
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
    writer.writerow(["Codigo", "Centro de custo", "Receitas", "Despesas", "Resultado"])
    for linha in resultado["por_centro_custo"]:
        writer.writerow([
            linha["codigo"],
            linha["centro_custo"],
            valor_csv(linha["receitas"]),
            valor_csv(linha["despesas"]),
            valor_csv(linha["resultado"]),
        ])
    writer.writerow([])
    writer.writerow(["Codigo", "Conta contabil", "Natureza", "Receitas", "Despesas", "Resultado"])
    for linha in resultado["por_conta_contabil"]:
        writer.writerow([
            linha["codigo"],
            linha["conta_contabil"],
            linha["natureza"],
            valor_csv(linha["receitas"]),
            valor_csv(linha["despesas"]),
            valor_csv(linha["resultado"]),
        ])
    writer.writerow([])
    writer.writerow(["Filial", "Conta", "Receitas", "Despesas", "Resultado"])
    for linha in resultado["por_conta"]:
        writer.writerow([linha["filial"], linha["conta"], str(linha["receitas"]).replace(".", ","), str(linha["despesas"]).replace(".", ","), str(linha["resultado"]).replace(".", ",")])
    writer.writerow([])
    writer.writerow(["Filial", "Conta movimento", "Tipo", "Saldo inicial", "Entradas período", "Saidas período", "Saldo atual"])
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
    writer.writerow(["Total de lançamentos", resultado["pacote_contabil"]["total_lancamentos"], "Registros do livro financeiro no período."])
    writer.writerow(["Transferências internas", resultado["pacote_contabil"]["transferencias"], f"Entradas {valor_csv(resultado['pacote_contabil']['transferencias_entradas'])} / Saidas {valor_csv(resultado['pacote_contabil']['transferencias_saidas'])}"])
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
        "plano_contas": [
            {
                **linha,
                "receitas": _valor_monetario_json(linha["receitas"]),
                "despesas": _valor_monetario_json(linha["despesas"]),
                "resultado": _valor_monetario_json(linha["resultado"]),
            }
            for linha in resultado["por_conta_contabil"]
        ],
        "centros_custo": [
            {
                **linha,
                "receitas": _valor_monetario_json(linha["receitas"]),
                "despesas": _valor_monetario_json(linha["despesas"]),
                "resultado": _valor_monetario_json(linha["resultado"]),
            }
            for linha in resultado["por_centro_custo"]
        ],
        "balancete_contas": resultado["balancete_contas"],
        "conciliacao_bancaria": _conciliacao_bancaria_json(resultado["conciliacao_bancaria"]),
        "integracao_fiscal": _integracao_fiscal_json(resultado["integracao_fiscal"]),
        "pacote_contabil": pacote,
        "contrato_integracao_contabil": resumo_contrato_contabil(empresa),
        "alertas": pacote["alertas"],
        "observacao": "Pacote gerencial de conferencia interna; não substitui SPED, ECD, ECF ou obrigacoes oficiais.",
    }


def _periodo_competencia(request):
    competencia = (request.GET.get("competencia") or "").strip()
    if not competencia:
        hoje = timezone.localdate()
        competencia = hoje.strftime("%Y-%m")
    try:
        ano, mes = (int(parte) for parte in competencia.split("-", 1))
        data_inicio = date(ano, mes, 1)
    except (TypeError, ValueError):
        raise ValidationError("Competência inválida. Informe no formato AAAA-MM.")
    if mes == 12:
        data_fim = date(ano + 1, 1, 1) - timedelta(days=1)
    else:
        data_fim = date(ano, mes + 1, 1) - timedelta(days=1)
    return competencia, data_inicio, data_fim


def _documentos_fiscais_periodo(filiais, data_inicio, data_fim):
    return DocumentoFiscal.objects.select_related("filial").filter(
        filial__in=filiais,
        criado_em__date__gte=data_inicio,
        criado_em__date__lte=data_fim,
    ).order_by("filial__nome", "tipo_documento", "serie", "numero", "pk")


def _documentos_saida_competencia(filiais, data_inicio, data_fim):
    documentos = DocumentoFiscal.objects.select_related("filial").filter(
        filial__in=filiais
    ).order_by("filial__nome", "tipo_documento", "serie", "numero", "pk")
    selecionados = []
    for documento in documentos.iterator():
        analise = analisar_xml_nfe(documento.xml_conteudo)
        data_emissao, fonte_competencia = data_competencia_documento(documento, analise)
        if data_inicio <= data_emissao <= data_fim:
            selecionados.append((documento, analise, data_emissao, fonte_competencia))
    return selecionados


def _documentos_entrada_competencia(filiais, data_inicio, data_fim, consolidado):
    empresas = Empresa.objects.filter(filiais__in=filiais).distinct()
    documentos = DocumentoDFeRecebido.objects.select_related("filial_destino").filter(empresa__in=empresas)
    if consolidado:
        documentos = documentos.filter(Q(filial_destino__in=filiais) | Q(filial_destino__isnull=True))
    else:
        documentos = documentos.filter(filial_destino__in=filiais)
    candidatos = documentos.filter(
        Q(data_emissao__range=(data_inicio, data_fim))
        | Q(data_emissao__isnull=True, recebido_em__date__range=(data_inicio, data_fim))
    ).order_by("data_emissao", "pk")
    return [
        (
            documento,
            analisar_xml_nfe(documento.xml_conteudo),
            documento.data_emissao or documento.recebido_em.date(),
            "XML_DHEMI" if documento.data_emissao else "RECEBIDO_EM",
        )
        for documento in candidatos
    ]


def _csv_text(cabecalho, linhas):
    buffer = StringIO(newline="")
    escritor = csv.writer(buffer, delimiter=";")
    escritor.writerow(cabecalho)
    escritor.writerows(linhas)
    return buffer.getvalue()


def _csv_excel_bytes(cabecalho, linhas):
    """Gera CSV que o Excel do Windows abre com codificação UTF-8 correta."""
    return _csv_text(cabecalho, linhas).encode("utf-8-sig")


def _pacote_contabil_zip(competencia, data_inicio, data_fim, filiais, filial_id, empresa_id):
    resultado = _resultado_financeiro_periodo(data_inicio, data_fim, filial_id, empresa_id)
    filiais_pacote = filiais.filter(pk=filial_id) if filial_id else filiais
    payload = _payload_pacote_contabil(data_inicio, data_fim, filiais_pacote, filial_id, empresa_id, resultado)
    documentos_saida = _documentos_saida_competencia(filiais_pacote, data_inicio, data_fim)
    documentos_entrada = _documentos_entrada_competencia(
        filiais_pacote, data_inicio, data_fim, consolidado=not bool(filial_id)
    )
    lancamentos = LancamentoFinanceiro.objects.select_related(
        "conta", "conta__filial", "conta_contabil", "centro_custo"
    ).filter(
        conta__filial__in=filiais_pacote,
        data__gte=data_inicio,
        data__lte=data_fim,
    ).order_by("data", "pk")
    empresa = filiais_pacote.first().empresa if filiais_pacote.exists() else None
    estoques = Estoque.objects.select_related("filial", "produto").filter(
        filial__in=filiais_pacote
    ).order_by("filial__nome", "produto__nome", "produto_id")
    fechamentos_inventario = list(
        FechamentoEstoqueContabil.objects.prefetch_related("itens").select_related("filial").filter(
            filial__in=filiais_pacote, data_referencia=data_fim
        ).order_by("filial__nome")
    )
    snapshot_completo = len(fechamentos_inventario) == filiais_pacote.count()
    referencia_inventario = (
        max(fechamento.capturado_em for fechamento in fechamentos_inventario)
        if snapshot_completo and fechamentos_inventario
        else timezone.now()
    )
    qualidade_inventario = (
        "SNAPSHOT_IMUTAVEL_FECHAMENTO"
        if snapshot_completo
        else ("POSICAO_NO_FECHAMENTO" if data_fim == referencia_inventario.date() else "POSICAO_ATUAL_NAO_RETROATIVA")
    )
    arquivos = OrderedDict()

    def adicionar_texto(nome, conteudo):
        arquivos[nome] = conteudo.encode("utf-8") if isinstance(conteudo, str) else conteudo

    adicionar_texto(
        "LEIA-ME.txt",
        "Pacote contábil gerencial do Deigo Varejo.\n"
        "Este material apoia a conferência da contabilidade e não substitui SPED, ECD, ECF ou obrigações oficiais.\n"
        f"Competência: {competencia}. A competência fiscal prioriza dhEmi/dEmi do XML e informa o fallback utilizado.\n"
        "Os dados por item são cópias estruturadas dos XMLs armazenados; divergências devem ser conferidas no XML original.\n"
        "O inventário prioriza snapshot imutável do fechamento; sem cobertura completa, informa explicitamente a qualidade temporal.\n",
    )
    adicionar_texto(
        "financeiro/pacote-gerencial.json",
        json.dumps(payload, cls=DjangoJSONEncoder, ensure_ascii=False, indent=2),
    )
    arquivos["financeiro/lancamentos.csv"] = _csv_excel_bytes(
        ["Data", "Filial", "Tipo", "Origem", "Descrição", "Valor", "Conta contábil", "Centro de custo"],
        [
            [
                lancamento.data.isoformat(),
                lancamento.conta.filial.nome,
                lancamento.get_tipo_display(),
                lancamento.origem,
                lancamento.descricao,
                f"{lancamento.valor:.2f}".replace(".", ","),
                str(lancamento.conta_contabil or ""),
                str(lancamento.centro_custo or ""),
            ]
            for lancamento in lancamentos
        ],
    )

    linhas_inventario = []
    valor_total_inventario = Decimal("0.00")
    if snapshot_completo:
        for fechamento in fechamentos_inventario:
            for item in fechamento.itens.all():
                valor_total_inventario += item.valor_custo
                linhas_inventario.append([
                    fechamento.filial.nome,
                    item.codigo_interno,
                    item.codigo_barras,
                    item.nome_produto,
                    item.ncm,
                    item.cest,
                    item.unidade,
                    f"{item.quantidade_fisica:.3f}".replace(".", ","),
                    f"{item.quantidade_reservada:.3f}".replace(".", ","),
                    f"{item.quantidade_disponivel:.3f}".replace(".", ","),
                    f"{item.custo_medio:.6f}".replace(".", ","),
                    f"{item.valor_custo:.2f}".replace(".", ","),
                    fechamento.capturado_em.isoformat(),
                    fechamento.criterio_custo,
                    qualidade_inventario,
                ])
    else:
        for saldo in estoques:
            valor_custo = saldo.quantidade_atual * saldo.custo_medio
            valor_total_inventario += valor_custo
            linhas_inventario.append([
                saldo.filial.nome,
                saldo.produto.codigo_interno,
                saldo.produto.codigo_barras,
                saldo.produto.nome,
                saldo.produto.ncm,
                saldo.produto.cest,
                saldo.produto.get_unidade_display(),
                f"{saldo.quantidade_atual:.3f}".replace(".", ","),
                f"{saldo.quantidade_reservada:.3f}".replace(".", ","),
                f"{saldo.quantidade_disponivel:.3f}".replace(".", ","),
                f"{saldo.custo_medio:.6f}".replace(".", ","),
                f"{valor_custo:.2f}".replace(".", ","),
                referencia_inventario.isoformat(),
                "CUSTO_MEDIO_PONDERADO_MOVEL",
                qualidade_inventario,
            ])
    arquivos["estoque/inventario-valorizado.csv"] = _csv_excel_bytes(
        [
            "Filial", "Código interno", "Código de barras", "Produto", "NCM", "CEST", "Unidade",
            "Quantidade física", "Quantidade reservada", "Quantidade disponível", "Custo médio unitário",
            "Valor a custo", "Data/hora da posição", "Critério de custo", "Qualidade temporal",
        ],
        linhas_inventario,
    )
    reconciliacao_operacional = gerar_reconciliacao_operacional(
        filiais=filiais_pacote, data_inicio=data_inicio, data_fim=data_fim
    )
    adicionar_texto(
        "reconciliacao/resumo.json",
        json.dumps(reconciliacao_operacional, cls=DjangoJSONEncoder, ensure_ascii=False, indent=2),
    )
    arquivos["reconciliacao/vendas.csv"] = _csv_excel_bytes(
        [
            "Filial", "Venda ID", "Data", "Status", "Total venda", "Pagamentos confirmados",
            "Pagamentos pendentes", "Pagamentos estornados", "Livro financeiro", "Documentos fiscais",
            "Documentos emitidos", "Valor fiscal", "Itens", "Movimentos de estoque", "Devoluções",
            "Situação", "Divergências",
        ],
        [
            [
                linha["filial"], linha["venda_id"], linha["data"].isoformat(), linha["status_venda"],
                f"{linha['total_venda']:.2f}".replace(".", ","),
                f"{linha['pagamentos_confirmados']:.2f}".replace(".", ","),
                f"{linha['pagamentos_pendentes']:.2f}".replace(".", ","),
                f"{linha['pagamentos_estornados']:.2f}".replace(".", ","),
                f"{linha['livro_financeiro']:.2f}".replace(".", ","),
                linha["documentos_fiscais"], linha["documentos_emitidos"],
                f"{linha['valor_fiscal']:.2f}".replace(".", ","),
                linha["itens_venda"], linha["movimentos_estoque"], linha["devolucoes"],
                linha["situacao"], linha["divergencias"],
            ]
            for linha in reconciliacao_operacional["vendas"]
        ],
    )
    arquivos["reconciliacao/entradas.csv"] = _csv_excel_bytes(
        [
            "Filial", "Entrada ID", "Data de emissão", "Data de recebimento", "Status", "Fornecedor",
            "Número documento", "Chave de acesso", "Total itens", "Total produtos", "Total documento",
            "DF-e vinculado", "Contas a pagar", "Valor contas a pagar", "Itens", "Movimentos de estoque",
            "Situação", "Divergências",
        ],
        [
            [
                linha["filial"], linha["entrada_id"],
                linha["data_emissao"].isoformat() if linha["data_emissao"] else "",
                linha["data_recebimento"].isoformat(), linha["status_entrada"], linha["fornecedor"],
                linha["numero_documento"], linha["chave_acesso"],
                f"{linha['total_itens']:.2f}".replace(".", ","),
                f"{linha['total_produtos']:.2f}".replace(".", ","),
                f"{linha['total_documento']:.2f}".replace(".", ",") if linha["total_documento"] is not None else "",
                "Sim" if linha["documento_dfe_vinculado"] else "Não", linha["contas_pagar"],
                f"{linha['valor_contas_pagar']:.2f}".replace(".", ","),
                linha["itens_entrada"], linha["movimentos_estoque"], linha["situacao"], linha["divergencias"],
            ]
            for linha in reconciliacao_operacional["entradas"]
        ],
    )

    arquivos["fiscal/documentos-saida.csv"] = _csv_excel_bytes(
        [
            "Filial", "Tipo", "Série", "Número", "Chave de acesso", "Status", "Valor total",
            "Protocolo", "Data de emissão", "Data de autorização", "Fonte da competência", "Protocolo de cancelamento", "Data de cancelamento", "XML incluído", "Pendência do XML",
        ],
        [
            [
                documento.filial.nome,
                documento.get_tipo_documento_display(),
                documento.serie,
                documento.numero or "",
                documento.chave_acesso or analise["chave_acesso"],
                documento.get_status_display(),
                f"{documento.valor_total:.2f}".replace(".", ","),
                documento.protocolo,
                data_emissao.isoformat(),
                analise["data_autorizacao"].isoformat() if analise["data_autorizacao"] else "",
                fonte_competencia,
                documento.protocolo_cancelamento,
                documento.cancelamento_em.isoformat() if documento.cancelamento_em else "",
                "Sim" if documento.xml_conteudo else "Não",
                analise["erro"],
            ]
            for documento, analise, data_emissao, fonte_competencia in documentos_saida
        ],
    )
    # Nome legado mantido durante a transição do contrato v1 para o v2.
    arquivos["fiscal/documentos.csv"] = arquivos["fiscal/documentos-saida.csv"]
    arquivos["fiscal/documentos-entrada.csv"] = _csv_excel_bytes(
        [
            "Filial destino", "Modelo", "Número", "Chave de acesso", "Emitente CNPJ", "Emitente",
            "Status", "Valor total", "Data de emissão", "Fonte da competência", "XML incluído", "Pendência do XML",
        ],
        [
            [
                str(documento.filial_destino or "Consolidado da empresa"),
                analise["modelo"],
                documento.numero_documento,
                documento.chave_acesso or analise["chave_acesso"],
                documento.emitente_cnpj,
                documento.emitente_nome,
                documento.get_status_display(),
                f"{documento.valor_total:.2f}".replace(".", ","),
                data_emissao.isoformat(),
                fonte_competencia,
                "Sim" if documento.xml_conteudo else "Não",
                analise["erro"],
            ]
            for documento, analise, data_emissao, fonte_competencia in documentos_entrada
        ],
    )

    campos_item = [
        "numero_item", "codigo_produto", "descricao", "ncm", "cest", "cfop", "unidade", "quantidade",
        "valor_unitario", "valor_produto", "valor_desconto", "origem_icms", "cst_icms", "csosn", "cbenef",
        "base_icms", "aliquota_icms", "valor_icms", "reducao_base_icms", "base_icms_st", "aliquota_icms_st",
        "valor_icms_st", "mva_st", "base_fcp", "aliquota_fcp", "valor_fcp", "base_fcp_st", "aliquota_fcp_st",
        "valor_fcp_st", "cst_pis", "base_pis", "aliquota_pis", "valor_pis", "cst_cofins", "base_cofins",
        "aliquota_cofins", "valor_cofins", "cst_ipi", "base_ipi", "aliquota_ipi", "valor_ipi",
    ]
    cabecalho_item = [
        "Origem", "Filial", "Documento ID", "Modelo", "Série", "Número", "Chave de acesso", "Status",
        "Data de emissão", "Fonte da competência",
    ] + campos_item
    linhas_itens = []
    for documento, analise, data_emissao, fonte_competencia in documentos_saida:
        for item in analise["itens"]:
            linhas_itens.append([
                "SAIDA", documento.filial.nome, documento.pk, analise["modelo"] or documento.tipo_documento,
                documento.serie, documento.numero or "", documento.chave_acesso or analise["chave_acesso"],
                documento.get_status_display(), data_emissao.isoformat(), fonte_competencia,
            ] + [item[campo] for campo in campos_item])
    for documento, analise, data_emissao, fonte_competencia in documentos_entrada:
        for item in analise["itens"]:
            linhas_itens.append([
                "ENTRADA", str(documento.filial_destino or "Consolidado da empresa"), documento.pk,
                analise["modelo"], "", documento.numero_documento, documento.chave_acesso or analise["chave_acesso"],
                documento.get_status_display(), data_emissao.isoformat(), fonte_competencia,
            ] + [item[campo] for campo in campos_item])
    arquivos["fiscal/itens-fiscais.csv"] = _csv_excel_bytes(cabecalho_item, linhas_itens)

    ids_saida = [documento.pk for documento, _analise, _data, _fonte in documentos_saida]
    cartas = CartaCorrecaoFiscal.objects.select_related("documento").filter(
        documento_id__in=ids_saida
    ).filter(
        Q(processado_em__date__range=(data_inicio, data_fim))
        | Q(processado_em__isnull=True, criado_em__date__range=(data_inicio, data_fim))
    ).order_by("documento_id", "sequencia")
    evidencias_evento = EvidenciaFiscal.objects.select_related("documento").filter(
        documento_id__in=ids_saida,
        criado_em__date__range=(data_inicio, data_fim),
        tipo__in=[
            TipoEvidenciaFiscal.EVENTO_CANCELAMENTO_ENVIO,
            TipoEvidenciaFiscal.EVENTO_CANCELAMENTO_RETORNO,
            TipoEvidenciaFiscal.EVENTO_CCE_ENVIO,
            TipoEvidenciaFiscal.EVENTO_CCE_RETORNO,
        ],
    ).order_by("documento_id", "sequencia")
    eventos_entrada = EventoDFeRecebido.objects.filter(
        empresa=empresa
    ).filter(
        Q(filial_destino__in=filiais_pacote) | (Q(filial_destino__isnull=True) if not filial_id else Q(pk__isnull=True))
    ).filter(
        Q(data_evento__date__range=(data_inicio, data_fim))
        | Q(data_evento__isnull=True, recebido_em__date__range=(data_inicio, data_fim))
    ).order_by("data_evento", "pk") if empresa else EventoDFeRecebido.objects.none()
    manifestacoes = ManifestacaoDestinatario.objects.select_related("documento").filter(
        empresa=empresa, filial__in=filiais_pacote
    ).filter(
        Q(processado_em__date__range=(data_inicio, data_fim))
        | Q(processado_em__isnull=True, criado_em__date__range=(data_inicio, data_fim))
    ).order_by("documento_id", "criado_em") if empresa else ManifestacaoDestinatario.objects.none()
    linhas_eventos = []
    for carta in cartas:
        linhas_eventos.append([
            "SAIDA", "CC-e", carta.documento.chave_acesso, carta.sequencia, carta.get_status_display(),
            carta.codigo_status, carta.protocolo, (carta.processado_em or carta.criado_em).isoformat(), carta.mensagem,
        ])
        if carta.xml_envio:
            adicionar_texto(f"fiscal/eventos/saida/cce-{carta.pk}-envio.xml", carta.xml_envio)
        if carta.xml_retorno:
            adicionar_texto(f"fiscal/eventos/saida/cce-{carta.pk}-retorno.xml", carta.xml_retorno)
    for evidencia in evidencias_evento:
        linhas_eventos.append([
            "SAIDA", evidencia.get_tipo_display(), evidencia.documento.chave_acesso, evidencia.sequencia, "Evidência",
            "", evidencia.protocolo, evidencia.criado_em.isoformat(), evidencia.referencia,
        ])
        adicionar_texto(f"fiscal/eventos/saida/evidencia-{evidencia.pk}.xml", evidencia.conteudo)
    for manifestacao in manifestacoes:
        linhas_eventos.append([
            "ENTRADA", manifestacao.get_tipo_display(), manifestacao.documento.chave_acesso, 1,
            manifestacao.get_status_display(), manifestacao.codigo_status, manifestacao.protocolo,
            (manifestacao.processado_em or manifestacao.criado_em).isoformat(), manifestacao.mensagem,
        ])
        if manifestacao.xml_envio:
            adicionar_texto(f"fiscal/eventos/entrada/manifestacao-{manifestacao.pk}-envio.xml", manifestacao.xml_envio)
        if manifestacao.xml_retorno:
            adicionar_texto(f"fiscal/eventos/entrada/manifestacao-{manifestacao.pk}-retorno.xml", manifestacao.xml_retorno)
    for evento in eventos_entrada:
        linhas_eventos.append([
            "ENTRADA", evento.tipo_evento or evento.descricao, evento.chave_acesso, evento.sequencia, "Recebido",
            "", "", (evento.data_evento or evento.recebido_em).isoformat(), evento.descricao,
        ])
        adicionar_texto(f"fiscal/eventos/entrada/evento-{evento.pk}.xml", evento.xml_conteudo)
    arquivos["fiscal/eventos.csv"] = _csv_excel_bytes(
        ["Origem", "Tipo", "Chave de acesso", "Sequência", "Status", "Código", "Protocolo", "Data", "Descrição"],
        linhas_eventos,
    )

    for documento, _analise, _data, _fonte in documentos_saida:
        if documento.xml_conteudo:
            nome = f"{documento.tipo_documento}-{documento.serie}-{documento.numero or documento.pk}-{documento.pk}.xml"
            adicionar_texto(f"fiscal/xml/saida/{nome}", documento.xml_conteudo)
            # Caminho legado mantido durante a transição.
            nome_legado = f"{documento.tipo_documento}-{documento.serie}-{documento.numero or documento.pk}.xml"
            adicionar_texto(f"fiscal/xml/{nome_legado}", documento.xml_conteudo)
    for documento, _analise, _data, _fonte in documentos_entrada:
        if documento.xml_conteudo:
            adicionar_texto(f"fiscal/xml/entrada/NFE-{documento.chave_acesso or documento.pk}-{documento.pk}.xml", documento.xml_conteudo)

    integridade = [
        {"caminho": nome, "bytes": len(conteudo), "sha256": hashlib.sha256(conteudo).hexdigest()}
        for nome, conteudo in arquivos.items()
    ]
    manifesto = {
        "contrato": "accounting_monthly_package_v2",
        "compatibilidade": ["accounting_monthly_package_v1"],
        "competencia": competencia,
        "empresa": payload["empresa"],
        "filial": payload["filial"],
        "contrato_integracao_contabil": resumo_contrato_contabil(empresa),
        "criterio_competencia_fiscal": "dhEmi/dEmi do XML; fallback xml_gerado_em e criado_em explicitado nos CSVs",
        "contagens": {
            "documentos_saida": len(documentos_saida),
            "documentos_entrada": len(documentos_entrada),
            "itens_fiscais": len(linhas_itens),
            "eventos": len(linhas_eventos),
            "itens_inventario": len(linhas_inventario),
            "vendas_reconciliadas": reconciliacao_operacional["resumo"]["vendas"],
            "vendas_divergentes": reconciliacao_operacional["resumo"]["vendas_divergentes"],
            "entradas_reconciliadas": reconciliacao_operacional["resumo"]["entradas"],
            "entradas_divergentes": reconciliacao_operacional["resumo"]["entradas_divergentes"],
        },
        "inventario": {
            "criterio_custo": "CUSTO_MEDIO_PONDERADO_MOVEL",
            "referencia": referencia_inventario.isoformat(),
            "qualidade_temporal": qualidade_inventario,
            "valor_total_custo": f"{valor_total_inventario:.2f}",
            "snapshot_completo": snapshot_completo,
            "fechamentos": [fechamento.conteudo_sha256 for fechamento in fechamentos_inventario] if snapshot_completo else [],
            "alerta": "Snapshot imutável do fechamento." if snapshot_completo else "Sem snapshot completo; para competência passada, esta é a posição atual e exige conferência.",
        },
        "arquivos": integridade,
        "observacao": "Arquivo gerencial. Valide regras fiscais e obrigações com o contador responsável.",
    }
    arquivo = BytesIO()
    with ZipFile(arquivo, "w", ZIP_DEFLATED) as zip_file:
        zip_file.writestr(
            "manifesto.json",
            json.dumps(manifesto, cls=DjangoJSONEncoder, ensure_ascii=False, indent=2).encode("utf-8"),
        )
        for nome, conteudo in arquivos.items():
            zip_file.writestr(nome, conteudo)
    xml_saida_total = sum(1 for documento, _analise, _data, _fonte in documentos_saida if documento.xml_conteudo)
    return arquivo.getvalue(), resultado, len(documentos_saida), xml_saida_total
@login_required
@role_required(*RELATORIOS)
def resultado_pacote_contabil_json(request):
    data_inicio, data_fim = _periodo_from_request(request)
    filiais, filial_id, _permite_consolidado, empresa_id = _escopo_filiais_financeiro(request)
    resultado = _resultado_financeiro_periodo(data_inicio, data_fim, filial_id, empresa_id)
    return JsonResponse(_payload_pacote_contabil(data_inicio, data_fim, filiais, filial_id, empresa_id, resultado))


@login_required
@role_required(*CONTABILIDADE)
def portal_contabilidade(request):
    competencia, data_inicio, data_fim = _periodo_competencia(request)
    filiais, filial_id, permite_consolidado, empresa_id = _escopo_filiais_financeiro(request)
    resultado = _resultado_financeiro_periodo(data_inicio, data_fim, filial_id, empresa_id)
    filiais_portal = filiais.filter(pk=filial_id) if filial_id else filiais
    documentos = _documentos_saida_competencia(filiais_portal, data_inicio, data_fim)
    documentos_total = len(documentos)
    xml_total = sum(1 for documento, _analise, _data, _fonte in documentos if documento.xml_conteudo)
    return render(
        request,
        "financeiro/portal_contabilidade.html",
        {
            "competencia": competencia,
            "filiais": filiais,
            "filial_id": filial_id,
            "permite_consolidado": permite_consolidado,
            "resultado": resultado,
            "documentos_total": documentos_total,
            "xml_total": xml_total,
            "pendencias_xml": documentos_total - xml_total,
            "contrato_integracao_contabil": resumo_contrato_contabil(
                Empresa.objects.filter(pk=empresa_id).first()
            ),
            "aceite_amostra_contabil": AceiteAmostraContabil.objects.filter(
                empresa_id=empresa_id, competencia=data_inicio
            ).order_by("-registrado_em").first(),
        },
    )


@login_required
@role_required(*CONTABILIDADE)
def pacote_contabil_mensal_zip(request):
    competencia, data_inicio, data_fim = _periodo_competencia(request)
    filiais, filial_id, _permite_consolidado, empresa_id = _escopo_filiais_financeiro(request)
    arquivo, _resultado, _documentos_total, _xml_total = _pacote_contabil_zip(
        competencia, data_inicio, data_fim, filiais, filial_id, empresa_id
    )
    LogAuditoria.objects.create(
        usuario=request.user,
        modulo="financeiro",
        acao="DOWNLOAD_PACOTE_CONTABIL",
        descricao=f"Pacote mensal {competencia} baixado.",
        objeto_tipo="Empresa",
        objeto_id=str(empresa_id or ""),
        ip=request.META.get("REMOTE_ADDR") or None,
    )
    resposta = HttpResponse(arquivo, content_type="application/zip")
    resposta["Content-Disposition"] = f'attachment; filename="pacote-contabil-{competencia}.zip"'
    return resposta


@login_required
@role_required(*ADMINISTRACAO)
def chaves_integracao_contabil(request):
    filiais, _filial_id, _permite_consolidado, empresa_id = _escopo_filiais_financeiro(request)
    empresas = Empresa.objects.filter(filiais__in=filiais).distinct().order_by("nome_fantasia")
    token_gerado = ""
    contrato_form = ContratoIntegracaoContabilForm(empresas=empresas) if request.user.is_superuser else None
    if request.method == "POST":
        acao = (request.POST.get("acao") or "").strip()
        if acao == "registrar_contrato":
            if not request.user.is_superuser:
                raise PermissionDenied("Somente o Master pode registrar ou validar o contrato contábil.")
            contrato_form = ContratoIntegracaoContabilForm(request.POST, empresas=empresas)
            if contrato_form.is_valid():
                dados = contrato_form.cleaned_data
                contrato = registrar_contrato_contabil(
                    empresa=dados["empresa"], usuario=request.user,
                    software_contabil=dados["software_contabil"],
                    formato_entrega=dados["formato_entrega"],
                    responsavel_efd_icms_ipi=dados["responsavel_efd_icms_ipi"],
                    responsavel_efd_nome=dados["responsavel_efd_nome"],
                    aceite_referencia=dados["aceite_referencia"],
                    observacoes=dados["observacoes"],
                    validar=dados["confirmar_validacao"],
                    ip=request.META.get("REMOTE_ADDR") or None,
                )
                messages.success(
                    request,
                    f"Contrato contábil v{contrato.versao} registrado como {contrato.get_status_display().lower()}.",
                )
                return redirect("financeiro:chaves_integracao_contabil")
        elif acao == "criar":
            empresa = get_object_or_404(empresas, pk=request.POST.get("empresa"))
            nome = (request.POST.get("nome") or "").strip()
            if not nome:
                messages.error(request, "Informe a identificação da chave.")
            elif ChaveIntegracaoContabil.objects.filter(empresa=empresa, nome=nome).exists():
                messages.error(request, "Já existe uma chave com esta identificação para a empresa.")
            else:
                token_gerado = ChaveIntegracaoContabil.gerar_token()
                chave = ChaveIntegracaoContabil(empresa=empresa, nome=nome, criada_por=request.user)
                chave.definir_token(token_gerado)
                chave.save()
                LogAuditoria.objects.create(
                    usuario=request.user,
                    modulo="financeiro",
                    acao="CRIAR_CHAVE_CONTABIL",
                    descricao=f"Chave de integração criada para {empresa.nome_fantasia}.",
                    objeto_tipo="ChaveIntegracaoContabil",
                    objeto_id=str(chave.pk),
                    ip=request.META.get("REMOTE_ADDR") or None,
                )
                messages.success(request, "Chave de integração criada. Copie o token exibido agora.")
        elif acao == "revogar":
            chave = get_object_or_404(ChaveIntegracaoContabil, pk=request.POST.get("chave"), empresa__in=empresas)
            chave.revogar()
            LogAuditoria.objects.create(
                usuario=request.user,
                modulo="financeiro",
                acao="REVOGAR_CHAVE_CONTABIL",
                descricao=f"Chave de integração revogada: {chave.nome}.",
                objeto_tipo="ChaveIntegracaoContabil",
                objeto_id=str(chave.pk),
                ip=request.META.get("REMOTE_ADDR") or None,
            )
            messages.success(request, "Chave de integração revogada.")
            return redirect("financeiro:chaves_integracao_contabil")
    chaves = ChaveIntegracaoContabil.objects.filter(empresa__in=empresas).select_related("empresa")
    contratos = [resumo_contrato_contabil(empresa) | {"empresa": empresa} for empresa in empresas]
    return render(
        request,
        "financeiro/chaves_integracao_contabil.html",
        {
            "empresas": empresas,
            "chaves": chaves,
            "token_gerado": token_gerado,
            "contrato_form": contrato_form,
            "contratos": contratos,
        },
    )


@login_required
def validar_amostra_contabil_view(request):
    if not request.user.is_superuser:
        raise PermissionDenied("Somente o Master pode validar ou aceitar a amostra contábil.")
    empresas = Empresa.objects.filter(filiais__is_active=True).distinct().order_by("nome_fantasia")
    form = AmostraContabilForm(request.POST or None, empresas=empresas)
    relatorio = None
    aceite_registrado = None
    if request.method == "POST" and form.is_valid():
        dados = form.cleaned_data
        empresa = dados["empresa"]
        contrato = ContratoIntegracaoContabil.objects.filter(
            empresa=empresa,
            status=StatusContratoIntegracaoContabil.VALIDADO,
            formato_entrega="PACOTE_ZIP_V2",
        ).order_by("-versao").first()
        if not contrato:
            messages.error(request, "A empresa não possui contrato validado para o pacote ZIP v2.")
        else:
            competencia = dados["competencia"]
            ano, mes = (int(parte) for parte in competencia.split("-", 1))
            data_inicio = date(ano, mes, 1)
            data_fim = (
                date(ano + 1, 1, 1) - timedelta(days=1)
                if mes == 12
                else date(ano, mes + 1, 1) - timedelta(days=1)
            )
            filiais = Filial.objects.select_related("empresa").filter(
                empresa=empresa, is_active=True
            ).order_by("nome")
            pacote_bytes, _resultado, _documentos, _xmls = _pacote_contabil_zip(
                competencia, data_inicio, data_fim, filiais, None, empresa.pk
            )
            relatorio = validar_amostra_contabil(
                pacote_bytes=pacote_bytes,
                empresa=empresa,
                contrato_integracao=contrato,
            )
            if dados["registrar_aceite"]:
                if not relatorio["aprovado"]:
                    messages.error(request, "O aceite não foi registrado porque existem portões pendentes.")
                else:
                    aceite_registrado, criado = registrar_aceite_amostra(
                        empresa=empresa,
                        competencia=competencia,
                        contrato_integracao=contrato,
                        pacote_bytes=pacote_bytes,
                        relatorio_validacao=relatorio,
                        referencia_aceite=dados["referencia_aceite"],
                        usuario=request.user,
                        ip=request.META.get("REMOTE_ADDR") or None,
                    )
                    messages.success(
                        request,
                        "Aceite da amostra registrado." if criado else "Esta mesma amostra já possuía aceite.",
                    )
    aceites = AceiteAmostraContabil.objects.select_related(
        "empresa", "contrato_integracao", "registrado_por"
    ).order_by("-registrado_em")[:20]
    return render(
        request,
        "financeiro/validar_amostra_contabil.html",
        {"form": form, "relatorio": relatorio, "aceite_registrado": aceite_registrado, "aceites": aceites},
    )

@require_GET
def api_pacote_contabil_mensal(request):
    token = (request.headers.get("X-Contabilidade-Key") or "").strip()
    if not token:
        return JsonResponse({"detail": "Informe a chave X-Contabilidade-Key."}, status=401)
    chave = ChaveIntegracaoContabil.objects.select_related("empresa").filter(
        token_hash=ChaveIntegracaoContabil.calcular_hash(token)
    ).first()
    if not chave or not chave.vigente:
        return JsonResponse({"detail": "Chave de integração inválida, expirada ou revogada."}, status=401)
    if not settings.DEBUG and not request.is_secure():
        return JsonResponse({"detail": "A API contábil exige HTTPS em produção."}, status=400)
    try:
        competencia, data_inicio, data_fim = _periodo_competencia(request)
    except ValidationError as erro:
        return JsonResponse({"detail": str(erro)}, status=400)
    filiais = Filial.objects.select_related("empresa").filter(empresa=chave.empresa, is_active=True).order_by("nome")
    filial_parametro = (request.GET.get("filial") or "").strip()
    filial_id = None
    if filial_parametro:
        if not filial_parametro.isdigit() or not filiais.filter(pk=filial_parametro).exists():
            return JsonResponse({"detail": "Filial fora do escopo da chave."}, status=403)
        filial_id = int(filial_parametro)
    resultado = _resultado_financeiro_periodo(data_inicio, data_fim, filial_id, chave.empresa_id)
    pacote = _payload_pacote_contabil(data_inicio, data_fim, filiais, filial_id, chave.empresa_id, resultado)
    ChaveIntegracaoContabil.objects.filter(pk=chave.pk).update(ultima_utilizacao_em=timezone.now())
    LogAuditoria.objects.create(
        modulo="financeiro",
        acao="API_PACOTE_CONTABIL",
        descricao=f"Pacote mensal {competencia} consultado pela API.",
        objeto_tipo="ChaveIntegracaoContabil",
        objeto_id=str(chave.pk),
        ip=request.META.get("REMOTE_ADDR") or None,
    )
    return JsonResponse({"contrato": "accounting_monthly_api_v1", "competencia": competencia, "pacote": pacote}, encoder=DjangoJSONEncoder)
@login_required
@role_required(*RELATORIOS)
def diagnostico_contabil_json(request):
    diagnostico = diagnosticar_adaptador_contabil()
    _filiais, _filial_id, _consolidado, empresa_id = _escopo_filiais_financeiro(request)
    contrato_contabil = resumo_contrato_contabil(Empresa.objects.filter(pk=empresa_id).first())
    diagnostico["contrato_integracao_contabil"] = contrato_contabil
    diagnostico["envio_permitido"] = bool(
        has_role(request.user, SISTEMA)
        and contrato_contabil.get("validado")
        and contrato_contabil.get("formato_entrega") == "ADAPTADOR_SERVIDOR_V1"
    )
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

    contrato_contabil = resumo_contrato_contabil(empresa)
    if not contrato_contabil.get("validado"):
        messages.error(request, "Valide com o contador uma versão do contrato contábil antes de qualquer envio por adaptador.")
        return redirect(destino)
    if contrato_contabil.get("formato_entrega") != "ADAPTADOR_SERVIDOR_V1":
        messages.error(request, "O contrato validado não autoriza envio por adaptador do servidor.")
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
    contas_qs = _queryset_no_escopo_financeiro(
        request,
        ContaMovimentoFinanceiro.objects.select_related("filial", "filial__empresa"),
    )
    contas_lista = list(contas_qs)
    return render(request, "financeiro/contas_movimento.html", {
        "contas_movimento": contas_lista,
        "total_contas_movimento": len(contas_lista),
        "saldo_total": sum((conta.saldo_atual for conta in contas_lista), Decimal("0.00")),
    })


@login_required
@role_required(*SISTEMA)
def conta_movimento_form(request, pk=None):
    contas = _queryset_no_escopo_financeiro(request, ContaMovimentoFinanceiro.objects.all())
    conta = get_object_or_404(contas, pk=pk) if pk else None
    form = ContaMovimentoFinanceiroForm(request.POST or None, instance=conta, user=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Conta de movimento salva.")
        return redirect("financeiro:contas_movimento")
    return render(request, "financeiro/conta_movimento_form.html", {"form": form, "conta": conta})


@login_required
@role_required(*SISTEMA)
def transferencia_form(request):
    form = TransferenciaFinanceiraForm(request.POST or None, initial={"data": timezone.localdate()}, user=request.user)
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
            messages.success(request, "Transferencia registrada com os dois lançamentos financeiros.")
            return redirect("financeiro:livro")
    return render(request, "financeiro/transferencia_form.html", {
        "form": form,
        "transferencias_recentes": _queryset_no_escopo_financeiro(
            request,
            TransferenciaFinanceira.objects.select_related(
                "conta_origem", "conta_destino", "conta_origem__filial", "conta_destino__filial", "usuario"
            ),
            campo_filial="conta_origem__filial",
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
    lancamentos = _queryset_no_escopo_financeiro(
        request, LancamentoFinanceiro.objects.all(), campo_filial="conta__filial"
    )
    lancamento = get_object_or_404(lancamentos, pk=pk)
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
            messages.success(request, "Estorno registrado com lançamento inverso.")
    return redirect("financeiro:livro")


@login_required
@role_required(*SISTEMA)
def conta_form(request, pk=None):
    contas = _queryset_no_escopo_financeiro(request, ContaFinanceira.objects.all())
    conta = get_object_or_404(contas, pk=pk) if pk else None
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
    conta = get_object_or_404(
        _queryset_no_escopo_financeiro(request, ContaFinanceira.objects.all()), pk=pk
    )
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
    conta = get_object_or_404(
        _queryset_no_escopo_financeiro(request, ContaFinanceira.objects.all()), pk=pk
    )
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
def plano_contas(request):
    empresas = _escopo_filiais_financeiro(request)[0].values("empresa")
    contas = ContaContabil.objects.filter(empresa__in=empresas).select_related("empresa", "conta_pai").order_by("empresa", "codigo")
    page_obj = Paginator(contas, 50).get_page(request.GET.get("page"))
    return render(request, "financeiro/plano_contas.html", {"contas_contabeis": page_obj, "page_obj": page_obj})


@login_required
@role_required(*SISTEMA)
def conta_contabil_form(request, pk=None):
    empresas = _escopo_filiais_financeiro(request)[0].values("empresa")
    conta = get_object_or_404(ContaContabil.objects.filter(empresa__in=empresas), pk=pk) if pk else None
    if request.method == "POST":
        form = ContaContabilForm(request.POST, instance=conta, user=request.user)
        if form.is_valid():
            conta_salva = form.save()
            LogAuditoria.objects.create(
                usuario=request.user,
                modulo="financeiro",
                acao="ALTERACAO_CONTA_CONTABIL" if conta else "CADASTRO_CONTA_CONTABIL",
                descricao=f"Conta contábil {conta_salva.codigo} - {conta_salva.nome} salva.",
                objeto_tipo="ContaContabil",
                objeto_id=str(conta_salva.pk),
                ip=request.META.get("REMOTE_ADDR"),
            )
            messages.success(request, "Conta contábil salva.")
            return redirect("financeiro:plano_contas")
    else:
        form = ContaContabilForm(instance=conta, user=request.user)
    return render(request, "financeiro/conta_contabil_form.html", {"form": form, "conta_contabil": conta})


@login_required
@role_required(*SISTEMA)
def centros_custo(request):
    empresas = _escopo_filiais_financeiro(request)[0].values("empresa")
    centros = CentroCusto.objects.filter(empresa__in=empresas).select_related("empresa").order_by("empresa", "nome")
    return render(request, "financeiro/centros_custo.html", {"centros": centros})


@login_required
@role_required(*SISTEMA)
def centro_custo_form(request, pk=None):
    empresas = _escopo_filiais_financeiro(request)[0].values("empresa")
    centro = get_object_or_404(CentroCusto.objects.filter(empresa__in=empresas), pk=pk) if pk else None
    if request.method == "POST":
        form = CentroCustoForm(request.POST, instance=centro, user=request.user)
        if form.is_valid():
            centro_salvo = form.save()
            LogAuditoria.objects.create(
                usuario=request.user,
                modulo="financeiro",
                acao="ALTERACAO_CENTRO_CUSTO" if centro else "CADASTRO_CENTRO_CUSTO",
                descricao=f"Centro de custo {centro_salvo.codigo} - {centro_salvo.nome} salvo.",
                objeto_tipo="CentroCusto",
                objeto_id=str(centro_salvo.pk),
                ip=request.META.get("REMOTE_ADDR"),
            )
            messages.success(request, "Centro de custo salvo.")
            return redirect("financeiro:centros_custo")
    else:
        form = CentroCustoForm(instance=centro, user=request.user)
    return render(request, "financeiro/centro_custo_form.html", {"form": form, "centro": centro})


@login_required
@role_required(*SISTEMA)
def categorias(request):
    categorias_qs = CategoriaFinanceira.objects.filter(empresa__in=_escopo_filiais_financeiro(request)[0].values("empresa")).select_related("conta_contabil").order_by("tipo", "nome")
    return render(request, "financeiro/categorias.html", {"categorias": categorias_qs})


@login_required
@role_required(*SISTEMA)
def categoria_form(request, pk=None):
    categoria = get_object_or_404(CategoriaFinanceira.objects.filter(empresa__in=_escopo_filiais_financeiro(request)[0].values("empresa")), pk=pk) if pk else None
    if request.method == "POST":
        form = CategoriaFinanceiraForm(request.POST, instance=categoria, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Categoria financeira salva.")
            return redirect("financeiro:categorias")
    else:
        form = CategoriaFinanceiraForm(instance=categoria, user=request.user)
    return render(request, "financeiro/categoria_form.html", {"form": form, "categoria": categoria})
@login_required
@role_required(*RELATORIOS)
def conciliacao_extratos(request):
    filiais, _, _, _ = _escopo_filiais_financeiro(request)
    pode_importar = has_role(request.user, SISTEMA)
    form = ImportacaoExtratoFinanceiroForm(request.POST or None, request.FILES or None, user=request.user)
    if request.method == "POST":
        if not pode_importar:
            raise PermissionDenied("Seu perfil não pode importar extratos financeiros.")
        if form.is_valid():
            arquivo = form.cleaned_data["arquivo"]
            try:
                importacao, criada = importar_extrato(
                    conta=form.cleaned_data["conta"],
                    arquivo_nome=arquivo.name,
                    conteudo=arquivo.read(),
                    adaptador_codigo=form.cleaned_data.get("adaptador") or "CSV_GENERICO",
                    usuario=request.user,
                    ip=request.META.get("REMOTE_ADDR"),
                )
            except ValidationError as exc:
                messages.error(request, " ".join(exc.messages))
            else:
                if criada:
                    messages.success(
                        request,
                        f"Extrato importado: {importacao.conciliadas_automaticamente} conciliações automáticas, "
                        f"{importacao.pendentes} pendências, {importacao.ambiguas} ambiguidades e "
                        f"{importacao.duplicadas} duplicidades ignoradas.",
                    )
                else:
                    messages.warning(request, "Este mesmo arquivo já havia sido importado nesta conta.")
                return redirect("financeiro:conciliacao_extratos")
        else:
            messages.error(request, "Revise os campos destacados antes de importar o extrato.")

    itens = ItemExtratoFinanceiro.objects.select_related(
        "conta", "conta__filial", "importacao", "lancamento",
    ).filter(conta__filial__in=filiais)
    status = (request.GET.get("status") or "").strip()
    conta_id = (request.GET.get("conta") or "").strip()
    q = (request.GET.get("q") or "").strip()
    if status in StatusItemExtratoFinanceiro.values:
        itens = itens.filter(status=status)
    if conta_id.isdigit():
        itens = itens.filter(conta_id=conta_id)
    if q:
        itens = itens.filter(
            Q(descricao__icontains=q)
            | Q(referencia_externa__icontains=q)
            | Q(importacao__arquivo_nome__icontains=q)
        )
    pagina = Paginator(itens, 50).get_page(request.GET.get("page"))
    query = request.GET.copy()
    query.pop("page", None)
    importacoes = ImportacaoExtratoFinanceiro.objects.select_related("conta", "conta__filial").filter(
        conta__filial__in=filiais
    )[:10]
    return render(request, "financeiro/conciliacao_extratos.html", {
        "form": form,
        "pagina": pagina,
        "query_sem_pagina": query.urlencode(),
        "importacoes": importacoes,
        "contas_opcoes": ContaMovimentoFinanceiro.objects.filter(ativa=True, filial__in=filiais).select_related("filial"),
        "status_opcoes": StatusItemExtratoFinanceiro.choices,
        "status": status,
        "conta_id": conta_id,
        "q": q,
        "pode_importar": pode_importar,
        "erros_adaptadores": getattr(form, "erros_adaptadores", []),
        "total_pendente": ItemExtratoFinanceiro.objects.filter(conta__filial__in=filiais, status=StatusItemExtratoFinanceiro.PENDENTE).count(),
        "total_ambiguo": ItemExtratoFinanceiro.objects.filter(conta__filial__in=filiais, status=StatusItemExtratoFinanceiro.AMBIGUO).count(),
        "total_parcial": ItemExtratoFinanceiro.objects.filter(conta__filial__in=filiais, status=StatusItemExtratoFinanceiro.PARCIAL).count(),
        "total_conciliado": ItemExtratoFinanceiro.objects.filter(conta__filial__in=filiais, status=StatusItemExtratoFinanceiro.CONCILIADO).count(),
    })


@login_required
@role_required(*RELATORIOS)
def item_extrato_detalhe(request, pk):
    filiais, _, _, _ = _escopo_filiais_financeiro(request)
    item = get_object_or_404(
        ItemExtratoFinanceiro.objects.select_related("conta", "conta__filial", "importacao", "lancamento")
        .prefetch_related("movimentos_recebiveis__recebivel__pagamento__forma_pagamento"),
        pk=pk,
        conta__filial__in=filiais,
    )
    possui_rateios = item.movimentos_recebiveis.exists()
    inicio = item.data - timedelta(days=3)
    fim = item.data + timedelta(days=3)
    candidatos = []
    if item.status != StatusItemExtratoFinanceiro.CONCILIADO and not possui_rateios:
        candidatos = LancamentoFinanceiro.objects.select_related("conta", "pagamento_venda").filter(
            conta=item.conta,
            tipo=item.tipo,
            valor=item.valor,
            data__range=(inicio, fim),
            conciliacao_bancaria__isnull=True,
            item_extrato__isnull=True,
        )[:20]

    saldo_alocar = item.saldo_alocar_recebiveis
    recebiveis_candidatos = []
    if item.status != StatusItemExtratoFinanceiro.CONCILIADO:
        recebiveis_candidatos = [
            {
                "objeto": recebivel,
                "valor_sugerido": min(recebivel.valor_liquido_previsto, saldo_alocar),
            }
            for recebivel in candidatos_recebivel_item(item)
        ]

    return render(request, "financeiro/item_extrato_detalhe.html", {
        "item": item,
        "candidatos": candidatos,
        "recebiveis_candidatos": recebiveis_candidatos,
        "valor_alocado": item.valor_alocado_recebiveis,
        "saldo_alocar": saldo_alocar,
        "possui_rateios": possui_rateios,
        "pode_conciliar": has_role(request.user, SISTEMA),
    })


@login_required
@role_required(*SISTEMA)
def conciliar_item_extrato_view(request, pk):
    if request.method != "POST":
        return redirect("financeiro:item_extrato_detalhe", pk=pk)
    filiais, _, _, _ = _escopo_filiais_financeiro(request)
    item = get_object_or_404(ItemExtratoFinanceiro, pk=pk, conta__filial__in=filiais)
    lancamento = get_object_or_404(
        LancamentoFinanceiro.objects.filter(conta__filial__in=filiais),
        pk=request.POST.get("lancamento_id"),
    )
    try:
        conciliar_item_extrato(
            item=item,
            lancamento=lancamento,
            usuario=request.user,
            ip=request.META.get("REMOTE_ADDR"),
        )
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(request, f"Item do extrato conciliado com o lançamento #{lancamento.pk}.")
    return redirect("financeiro:item_extrato_detalhe", pk=pk)
@login_required
@role_required(*SISTEMA)
def conciliar_item_recebivel_view(request, pk):
    if request.method != "POST":
        return redirect("financeiro:item_extrato_detalhe", pk=pk)
    filiais, _, _, _ = _escopo_filiais_financeiro(request)
    item = get_object_or_404(ItemExtratoFinanceiro, pk=pk, conta__filial__in=filiais)
    recebivel = get_object_or_404(
        RecebivelEletronico.objects.filter(pagamento__venda__filial__in=filiais),
        pk=request.POST.get("recebivel_id"),
    )
    form = AlocacaoRecebivelForm(request.POST)
    if not form.is_valid():
        erros = " ".join(
            str(mensagem)
            for mensagens in form.errors.values()
            for mensagem in mensagens
        )
        messages.error(request, erros)
        return redirect("financeiro:item_extrato_detalhe", pk=pk)

    try:
        conciliar_recebivel_com_item(
            item=item,
            recebivel=recebivel,
            valor_alocado=form.cleaned_data["valor_alocado"],
            usuario=request.user,
            ip=request.META.get("REMOTE_ADDR"),
        )
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        recebivel.refresh_from_db()
        messages.success(
            request,
            f"R$ {form.cleaned_data['valor_alocado']:.2f} alocados ao recebível "
            f"#{recebivel.pk}: {recebivel.get_status_display()}.",
        )
    return redirect("financeiro:item_extrato_detalhe", pk=pk)


@login_required
@role_required(*RELATORIOS)
def modelo_extrato_csv(request):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="modelo_conciliacao_extrato.csv"'
    response.write("\ufeff")
    writer = csv.writer(response, delimiter=";")
    writer.writerow(["data", "tipo", "valor", "descricao", "referencia"])
    writer.writerow([timezone.localdate().strftime("%d/%m/%Y"), "credito", "150,00", "Recebimento identificado", "NSU-EXEMPLO-001"])
    return response


@login_required
@role_required(*RELATORIOS)
def agenda_recebiveis(request):
    filiais, filial_id, permite_consolidado, empresa_id = _escopo_filiais_financeiro(request)
    if request.method == "POST":
        if not has_role(request.user, SISTEMA):
            raise PermissionDenied("Seu perfil não pode sincronizar a agenda de recebíveis.")
        resultado = sincronizar_recebiveis(filiais=filiais)
        LogAuditoria.objects.create(
            usuario=request.user,
            modulo="financeiro",
            acao="SINCRONIZA_AGENDA_RECEBIVEIS",
            descricao=(
                f"Agenda sincronizada: {resultado['criados']} criado(s) e "
                f"{resultado['sem_regra']} pagamento(s) sem regra."
            ),
            objeto_tipo="RecebivelEletronico",
            ip=request.META.get("REMOTE_ADDR"),
        )
        if resultado["criados"]:
            messages.success(request, f"{resultado['criados']} recebível(is) incluído(s) na agenda.")
        if resultado["sem_regra"]:
            messages.warning(
                request,
                f"{resultado['sem_regra']} pagamento(s) eletrônico(s) continuam sem regra ativa de liquidação.",
            )
        if not resultado["criados"] and not resultado["sem_regra"]:
            messages.info(request, "A agenda já estava atualizada.")
        return redirect("financeiro:agenda_recebiveis")

    data_inicio, data_fim = _periodo_from_request(request)
    status = (request.GET.get("status") or "").strip()
    forma_id = (request.GET.get("forma") or "").strip()
    q = (request.GET.get("q") or "").strip()
    recebiveis = RecebivelEletronico.objects.select_related(
        "pagamento__venda__filial__empresa", "pagamento__forma_pagamento", "regra"
    ).filter(
        pagamento__venda__filial__in=filiais,
        data_prevista__range=(data_inicio, data_fim),
    )
    if filial_id:
        recebiveis = recebiveis.filter(pagamento__venda__filial_id=filial_id)
    if status == "ATRASADO":
        recebiveis = recebiveis.filter(
            status=StatusRecebivelEletronico.PENDENTE,
            data_prevista__lt=timezone.localdate(),
        )
    elif status in StatusRecebivelEletronico.values:
        recebiveis = recebiveis.filter(status=status)
    if forma_id.isdigit():
        recebiveis = recebiveis.filter(pagamento__forma_pagamento_id=forma_id)
    if q:
        busca = (
            Q(pagamento__nsu__icontains=q)
            | Q(pagamento__transacao_externa_id__icontains=q)
            | Q(pagamento__codigo_autorizacao__icontains=q)
        )
        if q.isdigit():
            busca |= Q(pagamento__venda_id=int(q))
        recebiveis = recebiveis.filter(busca)

    resumo = recebiveis.aggregate(
        bruto=Sum("valor_bruto"),
        taxas=Sum("taxa_prevista"),
        liquido=Sum("valor_liquido_previsto"),
    )
    pagina = Paginator(recebiveis, 50).get_page(request.GET.get("page"))
    query = request.GET.copy()
    query.pop("page", None)
    from apps.vendas.models import FormaPagamento, PagamentoVenda, StatusPagamento

    eletronicos = ["PIX", "CARTAO", "DEBITO", "CREDITO", "VALE_ALIMENTACAO", "VALE_REFEICAO"]
    pagamentos_sem_regra = PagamentoVenda.objects.filter(
        venda__filial__in=filiais,
        status=StatusPagamento.CONFIRMADO,
        forma_pagamento__tipo__in=eletronicos,
        recebivel_eletronico__isnull=True,
    ).count()
    return render(request, "financeiro/agenda_recebiveis.html", {
        "pagina": pagina,
        "query_sem_pagina": query.urlencode(),
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "filiais_opcoes": filiais,
        "filial_id": str(filial_id or ""),
        "permite_consolidado": permite_consolidado,
        "status": status,
        "status_opcoes": StatusRecebivelEletronico.choices,
        "forma_id": forma_id,
        "formas_opcoes": FormaPagamento.objects.filter(tipo__in=eletronicos, ativo=True).order_by("nome"),
        "q": q,
        "total_bruto": resumo["bruto"] or Decimal("0.00"),
        "total_taxas": resumo["taxas"] or Decimal("0.00"),
        "total_liquido": resumo["liquido"] or Decimal("0.00"),
        "total_atrasados": recebiveis.filter(
            status=StatusRecebivelEletronico.PENDENTE,
            data_prevista__lt=timezone.localdate(),
        ).count(),
        "pagamentos_sem_regra": pagamentos_sem_regra,
        "pode_configurar": has_role(request.user, SISTEMA),
    })


@login_required
@role_required(*RELATORIOS)
def agenda_recebiveis_csv(request):
    filiais, filial_id, _, _ = _escopo_filiais_financeiro(request)
    data_inicio, data_fim = _periodo_from_request(request)
    recebiveis = RecebivelEletronico.objects.select_related(
        "pagamento__venda__filial", "pagamento__forma_pagamento"
    ).filter(
        pagamento__venda__filial__in=filiais,
        data_prevista__range=(data_inicio, data_fim),
    )
    if filial_id:
        recebiveis = recebiveis.filter(pagamento__venda__filial_id=filial_id)
    status = (request.GET.get("status") or "").strip()
    forma_id = (request.GET.get("forma") or "").strip()
    q = (request.GET.get("q") or "").strip()
    if status == "ATRASADO":
        recebiveis = recebiveis.filter(
            status=StatusRecebivelEletronico.PENDENTE,
            data_prevista__lt=timezone.localdate(),
        )
    elif status in StatusRecebivelEletronico.values:
        recebiveis = recebiveis.filter(status=status)
    if forma_id.isdigit():
        recebiveis = recebiveis.filter(pagamento__forma_pagamento_id=forma_id)
    if q:
        busca = (
            Q(pagamento__nsu__icontains=q)
            | Q(pagamento__transacao_externa_id__icontains=q)
            | Q(pagamento__codigo_autorizacao__icontains=q)
        )
        if q.isdigit():
            busca |= Q(pagamento__venda_id=int(q))
        recebiveis = recebiveis.filter(busca)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="agenda_recebiveis_{data_inicio}_{data_fim}.csv"'
    response.write("﻿")
    writer = csv.writer(response, delimiter=";")
    writer.writerow([
        "Venda", "Filial", "Forma", "NSU", "Data da venda", "Data prevista",
        "Valor bruto", "Taxa prevista", "Valor líquido previsto", "Data da liquidação",
        "Valor liquidado", "Diferença", "Referência da liquidação", "Status",
    ])
    for item in recebiveis.iterator():
        writer.writerow([
            item.pagamento.venda_id,
            item.pagamento.venda.filial,
            item.pagamento.forma_pagamento,
            item.pagamento.nsu,
            item.data_venda.strftime("%d/%m/%Y"),
            item.data_prevista.strftime("%d/%m/%Y"),
            str(item.valor_bruto).replace(".", ","),
            str(item.taxa_prevista).replace(".", ","),
            str(item.valor_liquido_previsto).replace(".", ","),
            item.data_liquidacao.strftime("%d/%m/%Y") if item.data_liquidacao else "",
            str(item.valor_liquidado).replace(".", ",") if item.valor_liquidado is not None else "",
            str((item.valor_liquidado - item.valor_liquido_previsto)).replace(".", ",") if item.valor_liquidado is not None else "",
            item.referencia_liquidacao,
            "Atrasado" if item.esta_atrasado else item.get_status_display(),
        ])
    return response


@login_required
@role_required(*SISTEMA)
def regras_liquidacao(request):
    filiais, _, _, _ = _escopo_filiais_financeiro(request)
    regras = RegraLiquidacaoEletronica.objects.select_related(
        "filial__empresa", "forma_pagamento"
    ).filter(filial__in=filiais)
    return render(request, "financeiro/regras_liquidacao.html", {"regras": regras})


@login_required
@role_required(*SISTEMA)
def regra_liquidacao_form(request, pk=None):
    filiais, _, _, _ = _escopo_filiais_financeiro(request)
    regra = get_object_or_404(RegraLiquidacaoEletronica.objects.filter(filial__in=filiais), pk=pk) if pk else None
    form = RegraLiquidacaoEletronicaForm(request.POST or None, instance=regra, user=request.user)
    if request.method == "POST" and form.is_valid():
        regra_salva = form.save(commit=False)
        regra_salva.full_clean()
        regra_salva.save()
        LogAuditoria.objects.create(
            usuario=request.user,
            modulo="financeiro",
            acao="CONFIGURA_REGRA_LIQUIDACAO",
            descricao=(
                f"Regra #{regra_salva.pk} salva para {regra_salva.filial} / "
                f"{regra_salva.forma_pagamento}: D+{regra_salva.prazo_dias}, "
                f"{regra_salva.taxa_percentual}% + R$ {regra_salva.taxa_fixa}."
            ),
            objeto_tipo="RegraLiquidacaoEletronica",
            objeto_id=str(regra_salva.pk),
            ip=request.META.get("REMOTE_ADDR"),
        )
        messages.success(request, "Regra de liquidação salva.")
        return redirect("financeiro:regras_liquidacao")
    return render(request, "financeiro/regra_liquidacao_form.html", {"form": form, "regra": regra})
