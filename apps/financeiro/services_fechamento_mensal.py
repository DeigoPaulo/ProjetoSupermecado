import hashlib
import json
from calendar import monthrange
from datetime import date, datetime
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q, Sum
from django.utils import timezone

from apps.accounts.models import PerfilUsuario, TipoPerfil
from apps.auditoria.models import LogAuditoria
from apps.empresas.models import Empresa, Filial
from apps.estoque.models import FechamentoEstoqueContabil
from apps.fiscal.models import DocumentoFiscal, HomologacaoFiscal, StatusDocumentoFiscal, StatusHomologacaoFiscal

from .models import (
    CompetenciaFinanceiroContabil,
    ContaFinanceira,
    ContaMovimentoFinanceiro,
    EventoCompetenciaFinanceiroContabil,
    FechamentoMensalSnapshot,
    ItemExtratoFinanceiro,
    LancamentoFinanceiro,
    MovimentoRecebivelEletronico,
    RecebivelEletronico,
    StatusCompetenciaFinanceiroContabil,
    StatusContaFinanceira,
    StatusItemExtratoFinanceiro,
    StatusRecebivelEletronico,
    TipoContaFinanceira,
    TipoEventoCompetenciaFinanceiroContabil,
    TipoLancamentoFinanceiro,
    TipoMovimentoRecebivelEletronico,
)
from .services_dre import calcular_dre_gerencial, serializar_dre_json


CONTRATO_FECHAMENTO = "financial_monthly_close_v1"
ZERO = Decimal("0.00")


def normalizar_competencia(competencia):
    if isinstance(competencia, str):
        try:
            ano, mes = (int(parte) for parte in competencia.split("-", 1))
            competencia = date(ano, mes, 1)
        except (TypeError, ValueError):
            raise ValidationError("Competência inválida. Informe AAAA-MM.")
    if not isinstance(competencia, date) or competencia.day != 1:
        raise ValidationError("A competência deve usar o primeiro dia do mês.")
    return competencia


def periodo_competencia(competencia):
    competencia = normalizar_competencia(competencia)
    return competencia, date(
        competencia.year,
        competencia.month,
        monthrange(competencia.year, competencia.month)[1],
    )


def _json_canonico(valor):
    return json.dumps(
        serializar_dre_json(valor),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def calcular_hash_snapshot(conteudo):
    return hashlib.sha256(_json_canonico(conteudo).encode("utf-8")).hexdigest()


def conteudo_economico_snapshot(snapshot):
    return {
        "contrato": CONTRATO_FECHAMENTO,
        "competencia": snapshot.competencia.competencia.isoformat(),
        "versao": snapshot.versao,
        "periodo": {"inicio": snapshot.data_inicio.isoformat(), "fim": snapshot.data_fim.isoformat()},
        "filiais": snapshot.filiais_snapshot,
        "dre": snapshot.dre_snapshot,
        "financeiro": snapshot.financeiro_snapshot,
        "contas": snapshot.contas_snapshot,
        "recebiveis": snapshot.recebiveis_snapshot,
        "inventario": snapshot.inventario_snapshot,
        "fiscal": snapshot.fiscal_snapshot,
        "diagnostico": snapshot.diagnostico_snapshot,
        "com_ressalvas": snapshot.com_ressalvas,
    }


def validar_hash_snapshot(snapshot):
    return calcular_hash_snapshot(conteudo_economico_snapshot(snapshot)) == snapshot.conteudo_sha256


def _hash_fechamento_estoque(fechamento):
    linhas = [
        {
            "produto_id": item.produto_id,
            "codigo_interno": item.codigo_interno,
            "codigo_barras": item.codigo_barras,
            "nome_produto": item.nome_produto,
            "ncm": item.ncm,
            "cest": item.cest,
            "unidade": item.unidade,
            "quantidade_fisica": str(item.quantidade_fisica),
            "quantidade_reservada": str(item.quantidade_reservada),
            "quantidade_disponivel": str(item.quantidade_disponivel),
            "custo_medio": str(item.custo_medio),
            "valor_custo": str(item.valor_custo),
        }
        for item in fechamento.itens.all().order_by("produto_id")
    ]
    conteudo = {
        "filial_id": fechamento.filial_id,
        "data_referencia": fechamento.data_referencia.isoformat(),
        "criterio_custo": fechamento.criterio_custo,
        "itens": linhas,
    }
    return hashlib.sha256(_json_canonico(conteudo).encode("utf-8")).hexdigest()


def _snapshot_inventario(filiais, data_fim):
    fechamentos = list(
        FechamentoEstoqueContabil.objects.filter(
            filial__in=filiais, data_referencia=data_fim
        ).select_related("filial").prefetch_related("itens").order_by("filial_id")
    )
    por_filial = {item.filial_id: item for item in fechamentos}
    referencias = []
    faltantes = []
    hashes_invalidos = []
    for filial in filiais:
        fechamento = por_filial.get(filial.pk)
        if not fechamento:
            faltantes.append({"filial_id": filial.pk, "filial": filial.nome})
            continue
        hash_calculado = _hash_fechamento_estoque(fechamento)
        if hash_calculado != fechamento.conteudo_sha256:
            hashes_invalidos.append({"filial_id": filial.pk, "fechamento_id": fechamento.pk})
        referencias.append(
            {
                "id": fechamento.pk,
                "filial_id": filial.pk,
                "filial": filial.nome,
                "data_referencia": fechamento.data_referencia.isoformat(),
                "valor_total_custo": format(fechamento.valor_total_custo, "f"),
                "criterio_custo": fechamento.criterio_custo,
                "conteudo_sha256": fechamento.conteudo_sha256,
            }
        )
    return {
        "data_referencia": data_fim.isoformat(),
        "valor_total_custo": format(sum((item.valor_total_custo for item in fechamentos), ZERO), "f"),
        "fechamentos": referencias,
        "filiais_sem_fechamento": faltantes,
        "hashes_invalidos": hashes_invalidos,
    }


def _snapshot_financeiro(empresa, filiais, data_inicio, data_fim):
    lancamentos_periodo = LancamentoFinanceiro.objects.filter(
        conta__filial__in=filiais, data__range=(data_inicio, data_fim)
    )
    operacionais = lancamentos_periodo.exclude(origem="TRANSFERENCIA")
    receitas = operacionais.filter(tipo=TipoLancamentoFinanceiro.ENTRADA).aggregate(total=Sum("valor"))["total"] or ZERO
    despesas = operacionais.filter(tipo=TipoLancamentoFinanceiro.SAIDA).aggregate(total=Sum("valor"))["total"] or ZERO
    transferencias = lancamentos_periodo.filter(origem="TRANSFERENCIA")
    estornos = lancamentos_periodo.filter(estorno_de__isnull=False)

    saldos = []
    for conta in ContaMovimentoFinanceiro.objects.filter(filial__in=filiais).select_related("filial").order_by("filial_id", "pk"):
        movimentos = conta.lancamentos.filter(data__lte=data_fim).values("tipo").annotate(total=Sum("valor"))
        totais = {item["tipo"]: item["total"] for item in movimentos}
        saldo = conta.saldo_inicial + totais.get(TipoLancamentoFinanceiro.ENTRADA, ZERO) - totais.get(TipoLancamentoFinanceiro.SAIDA, ZERO)
        saldos.append(
            {
                "conta_id": conta.pk,
                "filial_id": conta.filial_id,
                "filial": conta.filial.nome,
                "nome": conta.nome,
                "tipo": conta.tipo,
                "saldo": format(saldo, "f"),
            }
        )

    conciliados = lancamentos_periodo.filter(conciliacao_bancaria__isnull=False)
    pendentes = lancamentos_periodo.filter(conciliacao_bancaria__isnull=True)
    valor_total = lancamentos_periodo.aggregate(total=Sum("valor"))["total"] or ZERO
    valor_conciliado = conciliados.aggregate(total=Sum("valor"))["total"] or ZERO
    itens_extrato = ItemExtratoFinanceiro.objects.filter(conta__filial__in=filiais, data__range=(data_inicio, data_fim))
    ambiguos = itens_extrato.filter(status=StatusItemExtratoFinanceiro.AMBIGUO)
    parciais = itens_extrato.filter(status=StatusItemExtratoFinanceiro.PARCIAL)
    percentual = (valor_conciliado / valor_total * Decimal("100")) if valor_total else ZERO
    return {
        "contrato": "financial_result_snapshot_v1",
        "empresa_id": empresa.pk,
        "receitas_realizadas": format(receitas, "f"),
        "despesas_realizadas": format(despesas, "f"),
        "resultado": format(receitas - despesas, "f"),
        "transferencias": {
            "quantidade": transferencias.count(),
            "valor": format(transferencias.aggregate(total=Sum("valor"))["total"] or ZERO, "f"),
        },
        "estornos": {
            "quantidade": estornos.count(),
            "valor": format(estornos.aggregate(total=Sum("valor"))["total"] or ZERO, "f"),
        },
        "saldos_contas": saldos,
        "conciliacao": {
            "conciliados": conciliados.count(),
            "pendentes": pendentes.count(),
            "ambiguos": ambiguos.count(),
            "parciais": parciais.count(),
            "valor_total": format(valor_total, "f"),
            "valor_conciliado": format(valor_conciliado, "f"),
            "valor_pendente": format(valor_total - valor_conciliado, "f"),
            "percentual": format(percentual.quantize(Decimal("0.01")), "f"),
        },
    }


def _snapshot_contas(filiais, data_inicio, data_fim):
    contas = ContaFinanceira.objects.filter(
        filial__in=filiais, criado_em__date__lte=data_fim
    ).select_related("filial")
    limitacoes = []
    if contas.filter(status=StatusContaFinanceira.CANCELADA).exists():
        limitacoes.append(
            "Contas canceladas não possuem timestamp estruturado; não são reconstruídas retroativamente."
        )
    resultado = {"PAGAR": {}, "RECEBER": {}, "limitacoes": limitacoes}
    for tipo in (TipoContaFinanceira.PAGAR, TipoContaFinanceira.RECEBER):
        grupo = contas.filter(tipo=tipo).exclude(status=StatusContaFinanceira.CANCELADA)
        abertas = [conta for conta in grupo if not conta.data_pagamento or conta.data_pagamento > data_fim]
        vencidas = [conta for conta in abertas if conta.vencimento <= data_fim]
        realizadas = [
            conta for conta in grupo
            if conta.data_pagamento and data_inicio <= conta.data_pagamento <= data_fim
        ]
        resultado[tipo] = {
            "quantidade_aberta": len(abertas),
            "valor_aberto": format(sum((conta.valor for conta in abertas), ZERO), "f"),
            "quantidade_vencida": len(vencidas),
            "valor_vencido": format(sum((conta.valor for conta in vencidas), ZERO), "f"),
            "quantidade_realizada_periodo": len(realizadas),
            "valor_realizado_periodo": format(sum((conta.valor_pago or ZERO for conta in realizadas), ZERO), "f"),
        }
    return resultado


def _snapshot_recebiveis(filiais, data_inicio, data_fim):
    recebiveis = list(
        RecebivelEletronico.objects.filter(
            pagamento__venda__filial__in=filiais,
            data_venda__range=(data_inicio, data_fim),
        ).order_by("pk")
    )
    pendentes = [item for item in recebiveis if not item.data_liquidacao or item.data_liquidacao > data_fim]
    liquidados = [item for item in recebiveis if item.data_liquidacao and item.data_liquidacao <= data_fim]
    antecipados = [item for item in liquidados if item.status == StatusRecebivelEletronico.ANTECIPADO]
    divergentes = [item for item in liquidados if item.status == StatusRecebivelEletronico.DIVERGENTE]
    movimentos = MovimentoRecebivelEletronico.objects.filter(
        recebivel__pagamento__venda__filial__in=filiais,
        data__range=(data_inicio, data_fim),
    )
    chargebacks = movimentos.filter(tipo=TipoMovimentoRecebivelEletronico.CHARGEBACK)
    bruto = sum((item.valor_bruto for item in recebiveis), ZERO)
    previsto = sum((item.valor_liquido_previsto for item in recebiveis), ZERO)
    liquidado = sum((item.valor_liquidado or ZERO for item in liquidados), ZERO)
    custos = sum((max(item.valor_bruto - (item.valor_liquidado or ZERO), ZERO) for item in liquidados), ZERO)
    divergencias = sum(((item.valor_liquidado or ZERO) - item.valor_liquido_previsto for item in liquidados), ZERO)
    return {
        "pendentes": len(pendentes),
        "liquidados": len(liquidados),
        "antecipados": len(antecipados),
        "divergentes": len(divergentes),
        "chargebacks": chargebacks.count(),
        "valor_chargebacks": format(chargebacks.aggregate(total=Sum("valor"))["total"] or ZERO, "f"),
        "valor_bruto": format(bruto, "f"),
        "valor_liquido_previsto": format(previsto, "f"),
        "valor_liquidado": format(liquidado, "f"),
        "custos_liquidacao": format(custos, "f"),
        "divergencias_liquidacao": format(divergencias, "f"),
        "limitacoes": [
            "O status histórico é reconstruído por data_liquidacao; alterações de status sem evento datado não são inventadas."
        ],
    }


def _snapshot_fiscal(empresa, filiais, data_inicio, data_fim):
    documentos = DocumentoFiscal.objects.filter(
        filial__in=filiais,
    ).filter(
        Q(venda__data__date__range=(data_inicio, data_fim))
        | Q(venda__isnull=True, criado_em__date__range=(data_inicio, data_fim))
    ).order_by("pk")
    referencias = [
        {
            "id": item.pk,
            "filial_id": item.filial_id,
            "tipo": item.tipo_documento,
            "serie": item.serie,
            "numero": item.numero,
            "status": item.status,
            "valor_total": format(item.valor_total, "f"),
        }
        for item in documentos
    ]
    hash_agregado = hashlib.sha256(_json_canonico(referencias).encode("utf-8")).hexdigest()
    homologadas = HomologacaoFiscal.objects.filter(
        configuracao__filial__in=filiais,
        status=StatusHomologacaoFiscal.CONCLUIDA,
    ).values_list("configuracao__filial_id", flat=True)
    homologacao_pendente = set(homologadas) != {filial.pk for filial in filiais}
    return {
        "empresa_id": empresa.pk,
        "quantidade": len(referencias),
        "valor_total": format(sum((item.valor_total for item in documentos), ZERO), "f"),
        "emitidos": documentos.filter(status=StatusDocumentoFiscal.EMITIDO).count(),
        "cancelados": documentos.filter(status=StatusDocumentoFiscal.CANCELADO).count(),
        "pendentes": documentos.filter(status__in=[StatusDocumentoFiscal.RASCUNHO, StatusDocumentoFiscal.PRONTO, StatusDocumentoFiscal.CONTINGENCIA]).count(),
        "rejeitados": documentos.filter(status__in=[StatusDocumentoFiscal.REJEITADO, StatusDocumentoFiscal.DENEGADO]).count(),
        "referencias": referencias,
        "hash_agregado_sha256": hash_agregado,
        "homologacao_fiscal_externa_pendente": homologacao_pendente,
    }


def diagnosticar_fechamento_mensal(empresa, competencia):
    competencia = normalizar_competencia(competencia)
    data_inicio, data_fim = periodo_competencia(competencia)
    filiais = list(Filial.objects.filter(empresa=empresa, is_active=True).order_by("pk"))
    bloqueios = []
    alertas = []
    hoje = timezone.localdate()
    if data_inicio > hoje:
        bloqueios.append({"codigo": "COMPETENCIA_FUTURA", "mensagem": "Competência futura não pode ser fechada."})
    elif data_fim > hoje:
        bloqueios.append({"codigo": "COMPETENCIA_EM_ANDAMENTO", "mensagem": "A competência só pode ser fechada no último dia do mês ou depois."})
    if not filiais:
        bloqueios.append({"codigo": "SEM_FILIAIS_ATIVAS", "mensagem": "A empresa não possui filiais ativas para o fechamento."})

    estado = CompetenciaFinanceiroContabil.objects.filter(empresa=empresa, competencia=competencia).first()
    if estado and estado.status == StatusCompetenciaFinanceiroContabil.FECHADA:
        bloqueios.append({"codigo": "COMPETENCIA_JA_FECHADA", "mensagem": "A competência já está fechada."})

    filial_ids = [filial.pk for filial in filiais]
    dre = calcular_dre_gerencial(data_inicio=data_inicio, data_fim=data_fim, filial_ids=filial_ids)
    if not dre["cmv"]["cmv_completo"]:
        bloqueios.append({"codigo": "CMV_INCOMPLETO", "mensagem": "O CMV possui itens sem custo histórico congelado."})
    if dre["reconciliacao_cmv"]["estado"] in {"DIVERGENTE", "INCOMPLETO"}:
        bloqueios.append({"codigo": f"CMV_{dre['reconciliacao_cmv']['estado']}", "mensagem": "A reconciliação de CMV não está apta ao fechamento."})

    inventario = _snapshot_inventario(filiais, data_fim)
    for item in inventario["filiais_sem_fechamento"]:
        bloqueios.append({"codigo": "ESTOQUE_SEM_FECHAMENTO", "mensagem": f"Falta fechamento de estoque exato para {item['filial']}."})
    if inventario["hashes_invalidos"]:
        bloqueios.append({"codigo": "ESTOQUE_HASH_INVALIDO", "mensagem": "Um fechamento de estoque obrigatório possui hash inválido."})

    financeiro = _snapshot_financeiro(empresa, filiais, data_inicio, data_fim)
    conciliacao = financeiro["conciliacao"]
    if conciliacao["ambiguos"] or conciliacao["parciais"]:
        bloqueios.append({"codigo": "CONCILIACAO_AMBIGUA_PARCIAL", "mensagem": "Existem itens de extrato ambíguos ou parcialmente alocados."})
    if conciliacao["pendentes"]:
        alertas.append({"codigo": "CONCILIACAO_PENDENTE", "mensagem": "Existem lançamentos ainda não conciliados no período."})

    nao_classificados = dre["saidas_nao_classificadas"]["quantidade"] + dre["entradas_nao_classificadas"]["quantidade"]
    if nao_classificados:
        alertas.append({"codigo": "DRE_NAO_CLASSIFICADA", "mensagem": "A DRE possui entradas ou saídas não classificadas."})
    tributos = next(linha for linha in dre["linhas"] if linha["codigo"] == "tributos_resultado")
    if tributos["valor"] is None:
        alertas.append({"codigo": "TRIBUTOS_NAO_APURADOS", "mensagem": "Tributos sobre o resultado não foram apurados."})

    contas = _snapshot_contas(filiais, data_inicio, data_fim)
    recebiveis = _snapshot_recebiveis(filiais, data_inicio, data_fim)
    if recebiveis["divergentes"]:
        alertas.append({"codigo": "RECEBIVEIS_DIVERGENTES", "mensagem": "Existem recebíveis divergentes; a diferença realizada permanece registrada na DRE."})
    fiscal = _snapshot_fiscal(empresa, filiais, data_inicio, data_fim)
    if fiscal["homologacao_fiscal_externa_pendente"]:
        alertas.append({"codigo": "HOMOLOGACAO_FISCAL_EXTERNA_PENDENTE", "mensagem": "A homologação fiscal externa permanece pendente; o fechamento é somente gerencial interno."})

    return {
        "contrato": CONTRATO_FECHAMENTO,
        "empresa": {"id": empresa.pk, "nome": empresa.nome_fantasia},
        "competencia": competencia,
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "pronto": not bloqueios,
        "bloqueios": bloqueios,
        "alertas": alertas,
        "com_ressalvas": bool(alertas),
        "filiais": [{"id": filial.pk, "nome": filial.nome, "cnpj": filial.cnpj} for filial in filiais],
        "dre": dre,
        "cmv": dre["cmv"],
        "estoque": inventario,
        "financeiro": financeiro,
        "contas": contas,
        "recebiveis": recebiveis,
        "conciliacao": conciliacao,
        "fiscal": fiscal,
    }


def _usuario_autorizado(usuario, empresa):
    if usuario and usuario.is_active and usuario.is_superuser:
        return True
    return bool(
        usuario
        and usuario.is_active
        and PerfilUsuario.objects.filter(
            usuario=usuario,
            is_active=True,
            filial__empresa=empresa,
            tipo__in=[TipoPerfil.ADMINISTRADOR, TipoPerfil.CONTABILIDADE],
        ).exists()
    )


@transaction.atomic
def fechar_competencia(*, empresa, competencia, usuario, confirmacao, observacao="", ip=None):
    competencia = normalizar_competencia(competencia)
    if not _usuario_autorizado(usuario, empresa):
        raise PermissionDenied("O fechamento exige Master, Administração ou Contabilidade da empresa.")
    confirmacao_esperada = f"Confirmo o fechamento da competência {competencia:%m/%Y}"
    if (confirmacao or "").strip() != confirmacao_esperada:
        raise ValidationError(f"Digite exatamente: {confirmacao_esperada}")

    empresa = Empresa.objects.select_for_update().get(pk=empresa.pk)
    estado, _ = CompetenciaFinanceiroContabil.objects.get_or_create(
        empresa=empresa, competencia=competencia
    )
    estado = CompetenciaFinanceiroContabil.objects.select_for_update().get(pk=estado.pk)
    if estado.status == StatusCompetenciaFinanceiroContabil.FECHADA:
        raise ValidationError("A competência já está fechada.")
    diagnostico = diagnosticar_fechamento_mensal(empresa, competencia)
    if diagnostico["bloqueios"]:
        raise ValidationError(
            "Fechamento bloqueado: " + "; ".join(item["mensagem"] for item in diagnostico["bloqueios"])
        )
    ultima_versao = estado.snapshots.order_by("-versao").values_list("versao", flat=True).first() or 0
    versao = ultima_versao + 1
    dados = {
        "contrato": CONTRATO_FECHAMENTO,
        "competencia": competencia.isoformat(),
        "versao": versao,
        "periodo": {"inicio": diagnostico["data_inicio"].isoformat(), "fim": diagnostico["data_fim"].isoformat()},
        "filiais": diagnostico["filiais"],
        "dre": serializar_dre_json(diagnostico["dre"]),
        "financeiro": diagnostico["financeiro"],
        "contas": diagnostico["contas"],
        "recebiveis": diagnostico["recebiveis"],
        "inventario": diagnostico["estoque"],
        "fiscal": diagnostico["fiscal"],
        "diagnostico": {
            "bloqueios": diagnostico["bloqueios"],
            "alertas": diagnostico["alertas"],
        },
        "com_ressalvas": diagnostico["com_ressalvas"],
    }
    sha256 = calcular_hash_snapshot(dados)
    try:
        snapshot = FechamentoMensalSnapshot.objects.create(
            competencia=estado,
            versao=versao,
            data_inicio=diagnostico["data_inicio"],
            data_fim=diagnostico["data_fim"],
            filiais_snapshot=dados["filiais"],
            dre_snapshot=dados["dre"],
            financeiro_snapshot=dados["financeiro"],
            contas_snapshot=dados["contas"],
            recebiveis_snapshot=dados["recebiveis"],
            inventario_snapshot=dados["inventario"],
            fiscal_snapshot=dados["fiscal"],
            diagnostico_snapshot=dados["diagnostico"],
            conteudo_sha256=sha256,
            com_ressalvas=dados["com_ressalvas"],
            fechado_por=usuario,
            observacao=(observacao or "").strip(),
        )
    except IntegrityError as exc:
        raise ValidationError("Outra tentativa já criou esta versão de fechamento.") from exc
    estado.status = StatusCompetenciaFinanceiroContabil.FECHADA
    estado.fechamento_vigente = snapshot
    estado.full_clean()
    estado.save(update_fields=["status", "fechamento_vigente", "atualizado_em"])
    EventoCompetenciaFinanceiroContabil.objects.create(
        competencia=estado,
        snapshot=snapshot,
        tipo=TipoEventoCompetenciaFinanceiroContabil.FECHAMENTO,
        usuario=usuario,
        motivo=(observacao or "").strip(),
        ip=ip,
    )
    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="financeiro",
        acao="FECHAR_COMPETENCIA_FINANCEIRO_CONTABIL",
        descricao=f"Competência {competencia:%m/%Y} fechada na versão {versao}, SHA-256 {sha256}.",
        objeto_tipo="FechamentoMensalSnapshot",
        objeto_id=str(snapshot.pk),
        ip=ip,
    )
    return snapshot


@transaction.atomic
def reabrir_competencia(*, competencia, usuario, motivo, confirmacao, ip=None):
    motivo = (motivo or "").strip()
    if len(motivo) < 15:
        raise ValidationError("A reabertura exige motivo com pelo menos 15 caracteres.")
    estado = CompetenciaFinanceiroContabil.objects.select_for_update().select_related("empresa", "fechamento_vigente").get(pk=competencia.pk)
    if not _usuario_autorizado(usuario, estado.empresa):
        raise PermissionDenied("A reabertura exige Master, Administração ou Contabilidade da empresa.")
    confirmacao_esperada = f"Confirmo a reabertura da competência {estado.competencia:%m/%Y}"
    if (confirmacao or "").strip() != confirmacao_esperada:
        raise ValidationError(f"Digite exatamente: {confirmacao_esperada}")
    if estado.status != StatusCompetenciaFinanceiroContabil.FECHADA or not estado.fechamento_vigente_id:
        raise ValidationError("Apenas competência fechada pode ser reaberta.")
    snapshot_anterior = estado.fechamento_vigente
    estado.status = StatusCompetenciaFinanceiroContabil.ABERTA
    estado.fechamento_vigente = None
    estado.full_clean()
    estado.save(update_fields=["status", "fechamento_vigente", "atualizado_em"])
    EventoCompetenciaFinanceiroContabil.objects.create(
        competencia=estado,
        snapshot=snapshot_anterior,
        tipo=TipoEventoCompetenciaFinanceiroContabil.REABERTURA,
        usuario=usuario,
        motivo=motivo,
        ip=ip,
    )
    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="financeiro",
        acao="REABRIR_COMPETENCIA_FINANCEIRO_CONTABIL",
        descricao=f"Competência {estado.competencia:%m/%Y} reaberta; snapshot v{snapshot_anterior.versao} preservado. Motivo: {motivo}",
        objeto_tipo="CompetenciaFinanceiroContabil",
        objeto_id=str(estado.pk),
        ip=ip,
    )
    return estado


def validar_competencia_aberta(*, data_operacao, empresa=None, filial=None, operacao="operação"):
    if not data_operacao:
        data_operacao = timezone.localdate()
    if isinstance(data_operacao, datetime):
        data_operacao = data_operacao.date()
    empresa = empresa or getattr(filial, "empresa", None)
    if not empresa:
        raise ValidationError("Não foi possível identificar a empresa da operação financeira.")
    competencia = data_operacao.replace(day=1)
    if CompetenciaFinanceiroContabil.objects.filter(
        empresa=empresa,
        competencia=competencia,
        status=StatusCompetenciaFinanceiroContabil.FECHADA,
    ).exists():
        raise ValidationError(
            f"A competência {competencia:%m/%Y} está fechada. Reabra o período antes de registrar {operacao} retroativa."
        )


def obter_dre_competencia(*, empresa, data_inicio, data_fim, filial_ids):
    competencia_inicio, competencia_fim = periodo_competencia(data_inicio.replace(day=1))
    filiais_ativas = set(
        Filial.objects.filter(empresa=empresa, is_active=True).values_list("pk", flat=True)
    )
    periodo_exato = data_inicio == competencia_inicio and data_fim == competencia_fim
    escopo_completo = set(filial_ids) == filiais_ativas
    if periodo_exato and escopo_completo:
        estado = CompetenciaFinanceiroContabil.objects.filter(
            empresa=empresa,
            competencia=competencia_inicio,
            status=StatusCompetenciaFinanceiroContabil.FECHADA,
            fechamento_vigente__isnull=False,
        ).select_related("fechamento_vigente").first()
        if estado:
            snapshot = estado.fechamento_vigente
            if not validar_hash_snapshot(snapshot):
                raise ValidationError("O hash do fechamento mensal vigente é inválido.")
            return snapshot.dre_snapshot, {
                "status": estado.status,
                "versao": snapshot.versao,
                "hash": snapshot.conteudo_sha256,
                "fechado_em": snapshot.fechado_em,
                "fonte": "SNAPSHOT_FECHADO",
            }
    return calcular_dre_gerencial(
        data_inicio=data_inicio, data_fim=data_fim, filial_ids=filial_ids
    ), {
        "status": "ABERTA",
        "versao": None,
        "hash": "",
        "fechado_em": None,
        "fonte": "DINAMICA",
    }
