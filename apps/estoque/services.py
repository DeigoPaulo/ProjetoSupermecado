import hashlib
import json
import uuid
from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Q, Sum
from django.utils import timezone

from apps.auditoria.models import LogAuditoria

from .models import (
    ComposicaoProduto,
    ConferenciaFisicaValidadeLote,
    ContagemLoteInventarioValidade,
    DesmembramentoProduto,
    EscopoLoteInventarioValidade,
    Estoque,
    ExecucaoManutencaoInventarioValidade,
    InventarioEstoque,
    ItemInventarioEstoque,
    OrigemItemInventarioValidade,
    ItemProducaoComposicaoProduto,
    ItemDesmembramentoProduto,
    LoteEstoque,
    MovimentacaoEstoque,
    MovimentacaoLoteEstoque,
    OrdemProducaoComposicao,
    OrigemInventario,
    PerdaEstoque,
    ProducaoComposicaoProduto,
    RetificacaoCapacidadeLoteEstoque,
    StatusDesmembramentoProduto,
    StatusInventario,
    StatusExecucaoManutencaoInventarioValidade,
    StatusOrdemProducaoComposicao,
    StatusProducaoComposicao,
    StatusTratamentoValidade,
    TipoDesmembramentoProduto,
    TipoMovimentacaoEstoque,
    TipoPerdaEstoque,
    TipoSaidaDesmembramento,
    consumir_lotes_movimentacao,
    criar_lote_movimentacao,
    movimentar_estoque,
    restaurar_lotes_movimentacao,
)


PRAZO_INVENTARIO_VALIDADE = timedelta(hours=24)

NIVEIS_RISCO_INVENTARIO = {
    "CRITICO": "Crítico",
    "ALTO": "Alto",
    "MEDIO": "Médio",
    "BAIXO": "Baixo",
}


def calcular_fila_inventario_risco(estoques, *, momento=None):
    """Prioriza contagens sem alterar saldo nem materializar dados derivados."""
    momento = momento or timezone.now()
    hoje = timezone.localdate(momento)
    estoques = list(estoques.select_related("produto", "filial"))
    if not estoques:
        return []

    filial_ids = {estoque.filial_id for estoque in estoques}
    produto_ids = {estoque.produto_id for estoque in estoques}
    chaves = {(estoque.filial_id, estoque.produto_id) for estoque in estoques}

    ultimas_contagens = {}
    itens_aplicados = (
        ItemInventarioEstoque.objects.filter(
            inventario__filial_id__in=filial_ids,
            inventario__status=StatusInventario.APLICADO,
            produto_id__in=produto_ids,
            quantidade_contada__isnull=False,
        )
        .select_related("inventario")
        .order_by("inventario__filial_id", "produto_id", "-inventario__aplicado_em", "-id")
    )
    for item in itens_aplicados:
        chave = (item.inventario.filial_id, item.produto_id)
        if chave in chaves and chave not in ultimas_contagens:
            ultimas_contagens[chave] = item

    perdas_recentes = {
        (row["filial_id"], row["produto_id"]): row["total"] or Decimal("0")
        for row in PerdaEstoque.objects.filter(
            filial_id__in=filial_ids,
            produto_id__in=produto_ids,
            data__gte=momento - timedelta(days=90),
        )
        .values("filial_id", "produto_id")
        .annotate(total=Sum("quantidade"))
    }

    lotes_por_chave = {}
    lotes = LoteEstoque.objects.filter(
        filial_id__in=filial_ids,
        produto_id__in=produto_ids,
        quantidade_atual__gt=0,
        validade__isnull=False,
        validade__lte=hoje + timedelta(days=30),
    ).values("filial_id", "produto_id", "validade")
    for lote in lotes:
        chave = (lote["filial_id"], lote["produto_id"])
        resumo = lotes_por_chave.setdefault(chave, {"vencido": False, "proximo": False})
        if lote["validade"] < hoje:
            resumo["vencido"] = True
        else:
            resumo["proximo"] = True

    fila = []
    for estoque in estoques:
        chave = (estoque.filial_id, estoque.produto_id)
        score = 0
        motivos = []
        disponivel = estoque.quantidade_disponivel
        minimo = estoque.produto.estoque_minimo
        ultima = ultimas_contagens.get(chave)
        lotes_risco = lotes_por_chave.get(chave, {})
        perda = perdas_recentes.get(chave, Decimal("0"))

        if disponivel < 0:
            score += 100
            motivos.append("saldo disponível negativo")
        elif disponivel <= 0:
            score += 45
            motivos.append("produto sem saldo disponível")
        elif minimo > 0 and disponivel <= minimo:
            score += 25
            motivos.append("saldo no mínimo ou abaixo dele")

        if lotes_risco.get("vencido"):
            score += 80
            motivos.append("lote vencido com saldo")
        if lotes_risco.get("proximo"):
            score += 30
            motivos.append("lote vence em até 30 dias")

        if perda > 0:
            score += min(35, 15 + int(perda))
            motivos.append(f"perdas recentes: {perda}")

        ultima_data = ultima.inventario.aplicado_em if ultima else None
        ultima_diferenca = abs(ultima.diferenca) if ultima else Decimal("0")
        if ultima_diferenca > 0:
            score += min(45, 20 + int(ultima_diferenca))
            motivos.append(f"última divergência: {ultima.diferenca}")
        if ultima_data is None:
            score += 45
            motivos.append("produto nunca contado")
            dias_sem_contagem = None
        else:
            dias_sem_contagem = (momento.date() - ultima_data.date()).days
            if dias_sem_contagem >= 90:
                score += 35
                motivos.append(f"sem contagem há {dias_sem_contagem} dias")
            elif dias_sem_contagem >= 30:
                score += 20
                motivos.append(f"sem contagem há {dias_sem_contagem} dias")

        if score >= 100:
            nivel = "CRITICO"
        elif score >= 60:
            nivel = "ALTO"
        elif score >= 30:
            nivel = "MEDIO"
        else:
            nivel = "BAIXO"
        fila.append(
            {
                "estoque": estoque,
                "score": score,
                "nivel": nivel,
                "nivel_label": NIVEIS_RISCO_INVENTARIO[nivel],
                "motivos": motivos,
                "ultima_contagem": ultima_data,
                "dias_sem_contagem": dias_sem_contagem,
            }
        )

    return sorted(fila, key=lambda item: (-item["score"], item["estoque"].produto.nome.lower()))


@transaction.atomic
def criar_inventario_risco(*, filial, estoques, usuario, descricao="", ip=None):
    estoques = list(
        Estoque.objects.select_for_update()
        .filter(pk__in=[estoque.pk for estoque in estoques], filial=filial)
        .select_related("produto")
    )
    if not estoques:
        raise ValidationError("Selecione ao menos um produto da fila de risco.")
    inventario = InventarioEstoque.objects.create(
        filial=filial,
        usuario=usuario,
        descricao=descricao or f"Contagem orientada a risco - {timezone.localdate():%d/%m/%Y}",
        origem=OrigemInventario.RISCO,
    )
    ItemInventarioEstoque.objects.bulk_create(
        [
            ItemInventarioEstoque(
                inventario=inventario,
                produto=estoque.produto,
                quantidade_sistema=estoque.quantidade_atual,
                quantidade_contada=None,
                diferenca=Decimal("0"),
                observacao="Sugerido pela fila de risco",
            )
            for estoque in estoques
        ]
    )
    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="estoque",
        acao="PLANO_INVENTARIO_RISCO",
        descricao=f"Inventário {inventario.id} criado com {len(estoques)} item(ns) priorizados por risco.",
        objeto_tipo="InventarioEstoque",
        objeto_id=str(inventario.id),
        ip=ip,
    )
    return inventario

@transaction.atomic
def criar_inventario_divergencias_validade(
    *,
    filial,
    lotes,
    usuario,
    descricao="",
    ip=None,
):
    ids_selecionados = {lote.pk for lote in lotes if lote.pk}
    if not ids_selecionados:
        raise ValidationError("Selecione ao menos um lote divergente.")
    if len(ids_selecionados) > 200:
        raise ValidationError("Selecione no máximo 200 lotes por inventário.")
    lotes_bloqueados = list(
        LoteEstoque.objects.select_for_update()
        .filter(pk__in=ids_selecionados, filial=filial, quantidade_atual__gt=0)
        .select_related("produto", "filial", "filial__empresa")
        .order_by("id")
    )
    if len(lotes_bloqueados) != len(ids_selecionados):
        raise ValidationError("A seleção contém lote inválido, sem saldo ou fora da filial.")

    conferencias = []
    lotes_por_produto = {}
    for lote in lotes_bloqueados:
        conferencia = conferencia_fisica_vigente_lote(lote)
        if not conferencia or conferencia.diferenca_snapshot == 0:
            raise ValidationError(
                "Todos os lotes selecionados devem possuir conferência divergente e ainda válida."
            )
        conferencias.append(conferencia)
        lotes_por_produto.setdefault(lote.produto_id, []).append(lote)

    conteudo_chave = {
        "contrato": "inventory_expiry_divergence_inventory_draft_v1",
        "empresa_id": filial.empresa_id,
        "filial_id": filial.pk,
        "conferencias": sorted(conferencia.conteudo_sha256 for conferencia in conferencias),
    }
    chave_origem_base = hashlib.sha256(
        json.dumps(conteudo_chave, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    inventarios_mesma_origem = InventarioEstoque.objects.filter(
        Q(chave_origem=chave_origem_base) | Q(chave_origem_base=chave_origem_base)
    )
    existente = (
        inventarios_mesma_origem.filter(
            status__in=[StatusInventario.ABERTO, StatusInventario.APLICADO]
        )
        .order_by("-criado_em", "-pk")
        .first()
    )
    if existente:
        return existente, False

    numero_tentativa = inventarios_mesma_origem.count() + 1
    chave_origem = (
        chave_origem_base
        if numero_tentativa == 1
        else hashlib.sha256(
            f"{chave_origem_base}:tentativa:{numero_tentativa}".encode("utf-8")
        ).hexdigest()
    )
    estoques = list(
        Estoque.objects.select_for_update()
        .filter(filial=filial, produto_id__in=lotes_por_produto)
        .select_related("produto")
        .order_by("produto_id")
    )
    estoques_por_produto = {estoque.produto_id: estoque for estoque in estoques}
    if set(estoques_por_produto) != set(lotes_por_produto):
        raise ValidationError("Não foi possível localizar o saldo agregado de todos os produtos selecionados.")

    lotes_escopo = list(
        LoteEstoque.objects.select_for_update()
        .filter(
            filial=filial,
            produto_id__in=lotes_por_produto,
            quantidade_atual__gt=0,
        )
        .select_related("produto")
        .order_by("produto_id", "id")
    )
    inventario = InventarioEstoque.objects.create(
        filial=filial,
        usuario=usuario,
        descricao=descricao or f"Divergências de validade - {timezone.localdate():%d/%m/%Y}",
        origem=OrigemInventario.DIVERGENCIA_VALIDADE,
        chave_origem=chave_origem,
        chave_origem_base=chave_origem_base,
        expira_em=timezone.now() + PRAZO_INVENTARIO_VALIDADE,
    )
    itens = []
    for produto_id, lotes_produto in lotes_por_produto.items():
        estoque = estoques_por_produto[produto_id]
        codigos = ", ".join(sorted({lote.codigo for lote in lotes_produto}))
        itens.append(
            ItemInventarioEstoque(
                inventario=inventario,
                produto=estoque.produto,
                quantidade_sistema=estoque.quantidade_atual,
                quantidade_contada=None,
                diferenca=Decimal("0.000"),
                observacao=(
                    f"Divergência de validade nos lotes {codigos[:160]}; "
                    "realizar contagem total do produto."
                )[:255],
            )
        )
    ItemInventarioEstoque.objects.bulk_create(itens)
    itens_por_produto = {
        item.produto_id: item
        for item in ItemInventarioEstoque.objects.filter(inventario=inventario)
    }
    lotes_por_id = {lote.pk: lote for lote in lotes_bloqueados}
    OrigemItemInventarioValidade.objects.bulk_create(
        [
            OrigemItemInventarioValidade(
                item=itens_por_produto[conferencia.produto_id_snapshot],
                conferencia=conferencia,
                lote=lotes_por_id[conferencia.lote_id],
            )
            for conferencia in conferencias
        ]
    )
    origens_por_lote = {
        origem.lote_id: origem
        for origem in OrigemItemInventarioValidade.objects.filter(item__inventario=inventario)
    }
    EscopoLoteInventarioValidade.objects.bulk_create(
        [
            EscopoLoteInventarioValidade(
                item=itens_por_produto[lote.produto_id],
                lote=lote,
                origem=origens_por_lote.get(lote.pk),
            )
            for lote in lotes_escopo
        ]
    )
    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="estoque",
        acao="PLANO_INVENTARIO_DIVERGENCIA_VALIDADE",
        descricao=(
            f"Inventário {inventario.id} criado em rascunho com {len(itens)} produto(s) "
            f"a partir de {len(lotes_bloqueados)} lote(s) divergente(s). Nenhum saldo foi ajustado."
        ),
        objeto_tipo="InventarioEstoque",
        objeto_id=str(inventario.pk),
        ip=ip,
    )
    return inventario, True

@transaction.atomic
def registrar_contagem_lote_inventario_validade(
    *,
    escopo,
    quantidade_contada,
    usuario,
    observacao="",
    confirmar_dados=False,
    ip=None,
):
    escopo = (
        EscopoLoteInventarioValidade.objects.select_for_update()
        .select_related(
            "item__inventario", "item__produto", "lote",
            "origem__conferencia",
        )
        .get(pk=escopo.pk)
    )
    inventario = escopo.item.inventario
    if inventario.origem != OrigemInventario.DIVERGENCIA_VALIDADE:
        raise ValidationError("A contagem por lote é exclusiva do inventário de divergência de validade.")
    if inventario.status != StatusInventario.ABERTO:
        raise ValidationError("Apenas inventários abertos aceitam contagem por lote.")
    if inventario.prazo_operacional_expirado:
        raise ValidationError("O prazo operacional deste inventário expirou; abra um novo inventário.")
    if not confirmar_dados:
        raise ValidationError("Confirme a contagem física do lote específico.")

    lote = LoteEstoque.objects.select_for_update().get(pk=escopo.lote_id)
    quantidade_contada = Decimal(quantidade_contada)
    observacao = (observacao or "").strip()
    if quantidade_contada < 0:
        raise ValidationError("A quantidade contada no lote não pode ser negativa.")
    if quantidade_contada > lote.quantidade_maxima_auditada and not observacao:
        raise ValidationError(
            "Justifique a sobra física que supera a capacidade atualmente auditada do lote."
        )

    contado_em = timezone.now()
    conferencia_sha256 = (
        escopo.origem.conferencia.conteudo_sha256 if escopo.origem_id else ""
    )
    conteudo = {
        "contrato": "inventory_expiry_lot_count_v1",
        "inventario_id": inventario.pk,
        "item_id": escopo.item_id,
        "escopo_id": escopo.pk,
        "origem_id": escopo.origem_id,
        "conferencia_sha256": conferencia_sha256,
        "lote_id": lote.pk,
        "lote_codigo": lote.codigo,
        "quantidade_sistema": str(lote.quantidade_atual),
        "quantidade_contada": str(quantidade_contada),
        "observacao": observacao,
        "usuario_id": usuario.pk,
        "contado_em": contado_em.isoformat(),
    }
    conteudo_sha256 = hashlib.sha256(
        json.dumps(conteudo, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    contagem = ContagemLoteInventarioValidade.objects.create(
        escopo=escopo,
        quantidade_sistema_snapshot=lote.quantidade_atual,
        quantidade_contada=quantidade_contada,
        observacao=observacao,
        contado_por=usuario,
        contado_em=contado_em,
        conteudo_sha256=conteudo_sha256,
    )
    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="estoque",
        acao="CONTAGEM_LOTE_INVENTARIO_VALIDADE",
        descricao=(
            f"Inventário {inventario.pk}, lote {lote.codigo}: saldo do sistema "
            f"{lote.quantidade_atual}, contagem física {quantidade_contada}. Nenhum saldo foi ajustado."
        ),
        objeto_tipo="ContagemLoteInventarioValidade",
        objeto_id=str(contagem.pk),
        ip=ip,
    )
    return contagem

@transaction.atomic
def cancelar_inventario(*, inventario, usuario, supervisor, motivo, ip=None):
    inventario = InventarioEstoque.objects.select_for_update().get(pk=inventario.pk)
    motivo = (motivo or "").strip()
    if inventario.status != StatusInventario.ABERTO:
        raise ValidationError("Apenas inventários abertos podem ser cancelados.")
    if supervisor is None:
        raise ValidationError("O cancelamento exige autorização de supervisor.")
    if len(motivo) < 10:
        raise ValidationError("Informe uma justificativa de cancelamento com ao menos 10 caracteres.")

    inventario.status = StatusInventario.CANCELADO
    inventario.encerrado_em = timezone.now()
    inventario.encerrado_por = supervisor
    inventario.motivo_encerramento = motivo
    inventario.save(
        update_fields=[
            "status", "encerrado_em", "encerrado_por", "motivo_encerramento",
        ]
    )
    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="estoque",
        acao="CANCELAMENTO_INVENTARIO",
        descricao=(
            f"Inventário {inventario.pk} cancelado sem movimentar estoque. "
            f"Motivo: {motivo}.{_autorizacao_texto(supervisor)}"
        ),
        objeto_tipo="InventarioEstoque",
        objeto_id=str(inventario.pk),
        ip=ip,
    )
    return inventario


@transaction.atomic
def expirar_inventarios_validade_vencidos(*, momento=None):
    momento = momento or timezone.now()
    inventarios = list(
        InventarioEstoque.objects.select_for_update()
        .filter(
            origem=OrigemInventario.DIVERGENCIA_VALIDADE,
            status=StatusInventario.ABERTO,
            expira_em__isnull=False,
            expira_em__lte=momento,
        )
        .order_by("pk")
    )
    for inventario in inventarios:
        inventario.status = StatusInventario.EXPIRADO
        inventario.encerrado_em = momento
        inventario.motivo_encerramento = (
            "Prazo operacional de 24 horas encerrado automaticamente sem ajuste de estoque."
        )
        inventario.save(
            update_fields=["status", "encerrado_em", "motivo_encerramento"]
        )
        LogAuditoria.objects.create(
            usuario=None,
            modulo="estoque",
            acao="EXPIRACAO_INVENTARIO_VALIDADE",
            descricao=(
                f"Inventário {inventario.pk} expirado automaticamente. "
                "Escopos, contagens e evidências foram preservados; nenhum saldo foi alterado."
            ),
            objeto_tipo="InventarioEstoque",
            objeto_id=str(inventario.pk),
        )
    return inventarios



def _registrar_execucao_manutencao_validade(
    *, execucao_id, status, iniciada_em, finalizada_em, expirados_total=0,
    erro_codigo="", erro_resumo="",
):
    conteudo = {
        "contrato": "inventory_expiry_maintenance_run_v1",
        "execucao_id": str(execucao_id),
        "status": status,
        "iniciada_em": iniciada_em.isoformat(),
        "finalizada_em": finalizada_em.isoformat(),
        "expirados_total": int(expirados_total),
        "erro_codigo": erro_codigo,
        "erro_resumo": erro_resumo,
    }
    digest = hashlib.sha256(
        json.dumps(conteudo, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return ExecucaoManutencaoInventarioValidade.objects.create(
        execucao_id=execucao_id,
        status=status,
        iniciada_em=iniciada_em,
        finalizada_em=finalizada_em,
        expirados_total=expirados_total,
        erro_codigo=erro_codigo,
        erro_resumo=erro_resumo,
        conteudo_sha256=digest,
    )


def executar_manutencao_inventarios_validade(*, momento=None):
    """Expira rascunhos vencidos e registra uma execução sanitizada e imutável."""
    iniciada_em = momento or timezone.now()
    execucao_id = uuid.uuid4()
    try:
        with transaction.atomic():
            expirados = expirar_inventarios_validade_vencidos(momento=iniciada_em)
            registro = _registrar_execucao_manutencao_validade(
                execucao_id=execucao_id,
                status=StatusExecucaoManutencaoInventarioValidade.SUCESSO,
                iniciada_em=iniciada_em,
                finalizada_em=timezone.now(),
                expirados_total=len(expirados),
            )
        return expirados, registro
    except Exception as exc:
        _registrar_execucao_manutencao_validade(
            execucao_id=execucao_id,
            status=StatusExecucaoManutencaoInventarioValidade.FALHA,
            iniciada_em=iniciada_em,
            finalizada_em=timezone.now(),
            erro_codigo=exc.__class__.__name__[:100],
            erro_resumo="Falha ao encerrar inventários de validade vencidos.",
        )
        raise


def diagnostico_manutencao_inventarios_validade(*, momento=None, idade_maxima_horas=26, inventarios=None):
    momento = momento or timezone.now()
    ultima = ExecucaoManutencaoInventarioValidade.objects.order_by("-finalizada_em", "-id").first()
    base = inventarios if inventarios is not None else InventarioEstoque.objects.all()
    vencidos_abertos = base.filter(
        origem=OrigemInventario.DIVERGENCIA_VALIDADE,
        status=StatusInventario.ABERTO,
        expira_em__isnull=False,
        expira_em__lte=momento,
    ).count()
    if ultima is None:
        estado, nivel = "NAO_EXECUTADA", "warning"
        mensagem = "A manutenção automática de validade ainda não possui execução registrada."
        idade_horas = None
    else:
        idade_horas = max(0, (momento - ultima.finalizada_em).total_seconds() / 3600)
        if ultima.status == StatusExecucaoManutencaoInventarioValidade.FALHA:
            estado, nivel = "FALHA", "danger"
            mensagem = "A última manutenção de validade falhou e precisa de verificação."
        elif idade_horas > idade_maxima_horas:
            estado, nivel = "ATRASADA", "warning"
            mensagem = "A manutenção de validade está atrasada."
        else:
            estado, nivel = "EM_DIA", "success"
            mensagem = "A manutenção de validade está em dia."
    return {
        "contrato": "inventory_expiry_maintenance_status_v1",
        "estado": estado,
        "nivel": nivel,
        "mensagem": mensagem,
        "idade_maxima_horas": idade_maxima_horas,
        "idade_horas": round(idade_horas, 1) if idade_horas is not None else None,
        "vencidos_abertos": vencidos_abertos,
        "ultima_execucao_em": ultima.finalizada_em.isoformat() if ultima else "",
        "ultima_execucao_em_display": timezone.localtime(ultima.finalizada_em).strftime("%d/%m/%Y %H:%M") if ultima else "Nunca",
        "ultima_status": ultima.status if ultima else "",
        "ultima_status_display": ultima.get_status_display() if ultima else "Não executada",
        "ultima_expirados_total": ultima.expirados_total if ultima else 0,
        "ultima_erro_codigo": ultima.erro_codigo if ultima else "",
        "sem_dados_sensiveis": True,
    }


def _autorizacao_texto(supervisor):
    return f" Autorizado por: {supervisor}." if supervisor else ""

TIPOS_COM_CONSERVACAO_MASSA = {
    TipoDesmembramentoProduto.ACOUGUE,
    TipoDesmembramentoProduto.HORTIFRUTI,
}


def _conservacao_massa_aplicavel(*, tipo, produto_origem, destinos):
    return bool(
        tipo in TIPOS_COM_CONSERVACAO_MASSA
        and produto_origem.unidade == "KG"
        and all(destino["produto"].unidade == "KG" for destino in destinos)
    )


def _resumo_conservacao_massa(*, tipo, produto_origem, quantidade_origem, destinos):
    quantidade_total = sum((destino["quantidade"] for destino in destinos), Decimal("0.000"))
    aplicavel = _conservacao_massa_aplicavel(tipo=tipo, produto_origem=produto_origem, destinos=destinos)
    excesso = max(quantidade_total - quantidade_origem, Decimal("0.000")) if aplicavel else Decimal("0.000")
    nao_classificada = max(quantidade_origem - quantidade_total, Decimal("0.000")) if aplicavel else Decimal("0.000")
    rendimento_total = ((quantidade_total / quantidade_origem) * Decimal("100")).quantize(Decimal("0.01"))
    return {
        "aplicavel": aplicavel,
        "valida": not aplicavel or (excesso == 0 and nao_classificada == 0),
        "quantidade_total": quantidade_total,
        "excesso": excesso,
        "nao_classificada": nao_classificada,
        "rendimento_total": rendimento_total,
    }


def _normalizar_data_lote(valor, rotulo):
    if not valor or isinstance(valor, date):
        return valor
    try:
        return date.fromisoformat(str(valor))
    except ValueError as exc:
        raise ValidationError(f"Informe uma data de {rotulo} valida.") from exc


def _conteudo_conferencia_fisica_lote(
    *,
    lote,
    quantidade_sistema,
    quantidade_observada,
    diferenca,
    observacao,
    usuario,
    momento,
):
    return {
        "contrato": "inventory_expiry_physical_check_v1",
        "empresa_id": lote.filial.empresa_id,
        "filial_id": lote.filial_id,
        "filial_nome": lote.filial.nome,
        "produto_id": lote.produto_id,
        "produto_nome": lote.produto.nome,
        "produto_codigo_barras": lote.produto.codigo_barras or "",
        "lote_id": lote.pk,
        "lote_codigo": lote.codigo,
        "validade": lote.validade.isoformat() if lote.validade else "",
        "quantidade_sistema": format(quantidade_sistema, ".3f"),
        "quantidade_observada": format(quantidade_observada, ".3f"),
        "diferenca": format(diferenca, ".3f"),
        "custo_unitario": format(lote.custo_unitario, ".2f"),
        "tratamento_status": lote.tratamento_validade_status,
        "observacao": observacao,
        "usuario_id": usuario.pk,
        "conferido_em": momento.isoformat(),
    }


def conferencia_fisica_vigente_lote(lote, *, momento=None):
    momento = momento or timezone.now()
    conferencia = (
        ConferenciaFisicaValidadeLote.objects.filter(lote_id=lote.pk)
        .order_by("-conferido_em", "-id")
        .first()
    )
    if not conferencia or timezone.localdate(conferencia.conferido_em) != timezone.localdate(momento):
        return None
    if (
        conferencia.lote_codigo_snapshot != lote.codigo
        or conferencia.validade_snapshot != lote.validade
        or conferencia.quantidade_sistema_snapshot != lote.quantidade_atual
        or conferencia.custo_unitario_snapshot != lote.custo_unitario
        or conferencia.filial_id_snapshot != lote.filial_id
        or conferencia.produto_id_snapshot != lote.produto_id
    ):
        return None
    return conferencia


@transaction.atomic
def registrar_conferencia_fisica_validade_lote(
    *,
    lote,
    quantidade_observada,
    observacao,
    confirmar_dados,
    usuario,
    ip=None,
):
    if not confirmar_dados:
        raise ValidationError("Confirme a conferência física do lote.")
    observacao = (observacao or "").strip()
    quantidade_observada = Decimal(quantidade_observada)
    lote = (
        LoteEstoque.objects.select_for_update()
        .select_related("produto", "filial", "filial__empresa")
        .get(pk=lote.pk)
    )
    hoje = timezone.localdate()
    if lote.quantidade_atual <= 0 or not lote.validade or lote.validade > hoje + timedelta(days=30):
        raise ValidationError("A conferência de validade exige lote com saldo vencido ou a vencer em até 30 dias.")
    if quantidade_observada < 0:
        raise ValidationError("A quantidade observada não pode ser negativa.")
    quantidade_sistema = lote.quantidade_atual
    diferenca = quantidade_observada - quantidade_sistema
    if diferenca != 0 and not observacao:
        raise ValidationError("Explique a divergência entre a quantidade observada e o saldo do sistema.")
    momento = timezone.now()
    conteudo = _conteudo_conferencia_fisica_lote(
        lote=lote,
        quantidade_sistema=quantidade_sistema,
        quantidade_observada=quantidade_observada,
        diferenca=diferenca,
        observacao=observacao,
        usuario=usuario,
        momento=momento,
    )
    conteudo_sha256 = hashlib.sha256(
        json.dumps(conteudo, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    conferencia = ConferenciaFisicaValidadeLote.objects.create(
        lote=lote,
        empresa=lote.filial.empresa,
        filial_id_snapshot=lote.filial_id,
        filial_nome_snapshot=lote.filial.nome,
        produto_id_snapshot=lote.produto_id,
        produto_nome_snapshot=lote.produto.nome,
        produto_codigo_barras_snapshot=lote.produto.codigo_barras or "",
        lote_codigo_snapshot=lote.codigo,
        validade_snapshot=lote.validade,
        quantidade_sistema_snapshot=quantidade_sistema,
        quantidade_observada=quantidade_observada,
        diferenca_snapshot=diferenca,
        custo_unitario_snapshot=lote.custo_unitario,
        tratamento_status_snapshot=lote.tratamento_validade_status,
        observacao=observacao,
        conferido_por=usuario,
        conferido_em=momento,
        conteudo_sha256=conteudo_sha256,
    )
    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="estoque",
        acao="CONFERENCIA_FISICA_VALIDADE_LOTE",
        descricao=(
            f"Lote {lote.codigo} de {lote.produto} / {lote.filial}: saldo do sistema "
            f"{quantidade_sistema}, observado {quantidade_observada}, diferença {diferenca}. "
            "Nenhuma quantidade foi ajustada."
        ),
        objeto_tipo="ConferenciaFisicaValidadeLote",
        objeto_id=str(conferencia.pk),
        ip=ip,
    )
    return conferencia

@transaction.atomic
def planejar_tratamento_validade_lote(*, lote, status, observacao, usuario, ip=None):
    observacao = (observacao or "").strip()
    if status not in {
        StatusTratamentoValidade.SEPARADO,
        StatusTratamentoValidade.DEVOLUCAO_PLANEJADA,
        StatusTratamentoValidade.PROMOCAO_PLANEJADA,
        StatusTratamentoValidade.DESCARTE_PLANEJADO,
    }:
        raise ValidationError("Tratamento de validade inválido.")
    if not observacao:
        raise ValidationError("Informe a orientação ou observação do tratamento.")
    lote = LoteEstoque.objects.select_for_update().select_related("produto", "filial").get(pk=lote.pk)
    hoje = timezone.localdate()
    if lote.quantidade_atual <= 0 or not lote.validade or lote.validade > hoje + timedelta(days=30):
        raise ValidationError("O plano só pode ser registrado para lote com saldo vencido ou a vencer em até 30 dias.")
    if status == StatusTratamentoValidade.PROMOCAO_PLANEJADA and lote.validade < hoje:
        raise ValidationError("Lote vencido não pode receber promoção planejada.")
    anterior = lote.tratamento_validade_status
    if anterior == status and lote.tratamento_validade_observacao == observacao:
        return lote, False
    lote.tratamento_validade_status = status
    lote.tratamento_validade_observacao = observacao
    lote.tratamento_validade_por = usuario
    lote.tratamento_validade_em = timezone.now()
    lote.save(update_fields=["tratamento_validade_status", "tratamento_validade_observacao", "tratamento_validade_por", "tratamento_validade_em", "atualizado_em"])
    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="estoque",
        acao="PLANEJAMENTO_TRATAMENTO_VALIDADE",
        descricao=(
            f"Lote {lote.codigo} de {lote.produto} / {lote.filial}: tratamento "
            f"{anterior} -> {status}. Nenhuma quantidade foi baixada."
        ),
        objeto_tipo="LoteEstoque",
        objeto_id=str(lote.pk),
        ip=ip,
    )
    return lote, True

def saldo_rastreado_lotes(*, produto, filial, bloquear=False):
    lotes = LoteEstoque.objects.filter(
        produto=produto,
        filial=filial,
        quantidade_atual__gt=0,
    )
    if bloquear:
        lotes = lotes.select_for_update()
    return sum((lote.quantidade_atual for lote in lotes), Decimal("0.000"))


@transaction.atomic
def atribuir_saldo_historico_lote(
    *,
    estoque,
    codigo,
    quantidade,
    custo_unitario,
    usuario,
    motivo,
    fabricacao=None,
    validade=None,
    supervisor=None,
    ip=None,
):
    motivo = (motivo or "").strip()
    codigo = (codigo or "").strip()
    if not motivo:
        raise ValidationError("Informe o motivo da atribuicao.")
    if not codigo:
        raise ValidationError("Informe o código do lote.")
    if quantidade <= 0:
        raise ValidationError("Quantidade deve ser maior que zero.")
    if custo_unitario < 0:
        raise ValidationError("Custo unitario não pode ser negativo.")

    estoque = Estoque.objects.select_for_update().select_related("produto", "filial").get(pk=estoque.pk)
    lotes_atuais = list(
        LoteEstoque.objects.select_for_update().filter(
            produto=estoque.produto,
            filial=estoque.filial,
            quantidade_atual__gt=0,
        )
    )
    saldo_rastreado = sum((lote.quantidade_atual for lote in lotes_atuais), Decimal("0.000"))
    saldo_sem_lote = estoque.quantidade_atual - saldo_rastreado
    if saldo_sem_lote < quantidade:
        raise ValidationError(
            f"A quantidade excede o saldo sem lote disponivel ({saldo_sem_lote})."
        )

    lote = LoteEstoque(
        produto=estoque.produto,
        filial=estoque.filial,
        codigo=codigo,
        fabricacao=fabricacao,
        validade=validade,
        quantidade_inicial=quantidade,
        quantidade_atual=quantidade,
        custo_unitario=custo_unitario,
        origem_referencia=f"atribuicao_historico:estoque:{estoque.id}",
    )
    lote.full_clean()
    lote.save()
    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="estoque",
        acao="ATRIBUICAO_SALDO_HISTORICO_LOTE",
        descricao=(
            f"{quantidade} de {estoque.produto} / {estoque.filial} atribuido ao lote {codigo} "
            f"sem alterar o saldo agregado. Motivo: {motivo}.{_autorizacao_texto(supervisor)}"
        ),
        objeto_tipo="LoteEstoque",
        objeto_id=str(lote.id),
        ip=ip,
    )
    return lote


def reconciliar_lotes_reducao_inventario(*, produto, filial, saldo_novo, movimentacao):
    lotes = list(
        LoteEstoque.objects.select_for_update().filter(
            produto=produto,
            filial=filial,
            quantidade_atual__gt=0,
        ).order_by(F("validade").asc(nulls_last=True), "criado_em", "id")
    )
    saldo_rastreado = sum((lote.quantidade_atual for lote in lotes), Decimal("0.000"))
    excesso_rastreado = max(saldo_rastreado - saldo_novo, Decimal("0.000"))
    reduzido = Decimal("0.000")
    for lote in lotes:
        if excesso_rastreado <= 0:
            break
        quantidade = min(lote.quantidade_atual, excesso_rastreado)
        lote.quantidade_atual -= quantidade
        lote.save(update_fields=["quantidade_atual", "atualizado_em"])
        MovimentacaoLoteEstoque.objects.create(
            movimentacao=movimentacao,
            lote=lote,
            quantidade=quantidade,
            custo_unitario=lote.custo_unitario,
        )
        excesso_rastreado -= quantidade
        reduzido += quantidade
    return reduzido


def _aplicar_inventario_divergencia_validade(*, inventario, itens, usuario, supervisor, ip=None):
    if supervisor is None:
        raise ValidationError("A aplicação da reconciliação por lote exige autorização de supervisor.")

    escopos = list(
        EscopoLoteInventarioValidade.objects.select_for_update()
        .filter(item__inventario=inventario)
        .select_related("item__produto", "lote", "origem__conferencia")
        .order_by("item_id", "lote_id")
    )
    if not escopos:
        raise ValidationError("O inventário não possui escopo de lotes para reconciliar.")

    contagens_por_escopo = {}
    for escopo in escopos:
        contagem = (
            ContagemLoteInventarioValidade.objects.select_for_update()
            .filter(escopo=escopo)
            .order_by("-contado_em", "-id")
            .first()
        )
        if not contagem:
            raise ValidationError("Todos os lotes do produto precisam de contagem física específica.")
        contagens_por_escopo[escopo.pk] = contagem

    produto_ids = {item.produto_id for item in itens}
    estoques = {
        estoque.produto_id: estoque
        for estoque in Estoque.objects.select_for_update().filter(
            filial=inventario.filial,
            produto_id__in=produto_ids,
        )
    }
    lotes = list(
        LoteEstoque.objects.select_for_update()
        .filter(filial=inventario.filial, produto_id__in=produto_ids)
        .order_by("produto_id", "id")
    )
    lotes_por_produto = {}
    for lote in lotes:
        lotes_por_produto.setdefault(lote.produto_id, []).append(lote)

    escopos_por_item = {}
    for escopo in escopos:
        escopos_por_item.setdefault(escopo.item_id, []).append(escopo)

    for item in itens:
        estoque = estoques.get(item.produto_id)
        if not estoque:
            raise ValidationError(f"Não foi localizado o saldo agregado de {item.produto}.")
        escopos_item = escopos_por_item.get(item.pk, [])
        if not escopos_item:
            raise ValidationError(f"O produto {item.produto} não possui lotes no escopo da contagem.")

        contagens = [contagens_por_escopo[escopo.pk] for escopo in escopos_item]
        total_contado_lotes = sum(
            (contagem.quantidade_contada for contagem in contagens), Decimal("0.000")
        )
        if total_contado_lotes != item.quantidade_contada:
            raise ValidationError(
                f"A soma contada nos lotes de {item.produto} ({total_contado_lotes}) "
                f"não corresponde à contagem total do produto ({item.quantidade_contada})."
            )

        lotes_item = lotes_por_produto.get(item.produto_id, [])
        ids_escopo = {escopo.lote_id for escopo in escopos_item}
        lotes_positivos_fora_escopo = [
            lote for lote in lotes_item if lote.quantidade_atual > 0 and lote.pk not in ids_escopo
        ]
        if lotes_positivos_fora_escopo:
            codigos = ", ".join(lote.codigo for lote in lotes_positivos_fora_escopo[:5])
            raise ValidationError(
                f"Existem lotes novos fora do escopo da contagem de {item.produto}: {codigos}."
            )

        saldo_rastreado = sum((lote.quantidade_atual for lote in lotes_item), Decimal("0.000"))
        if saldo_rastreado != estoque.quantidade_atual:
            raise ValidationError(
                f"O saldo agregado de {item.produto} não corresponde integralmente aos lotes rastreados."
            )

        item.quantidade_sistema = estoque.quantidade_atual
        item.diferenca = item.quantidade_contada - estoque.quantidade_atual
        item.save(update_fields=["quantidade_sistema", "diferenca"])

        lotes_item_por_id = {lote.pk: lote for lote in lotes_item}
        for escopo in escopos_item:
            lote = lotes_item_por_id[escopo.lote_id]
            contagem = contagens_por_escopo[escopo.pk]
            if lote.quantidade_atual != contagem.quantidade_sistema_snapshot:
                raise ValidationError(
                    f"O saldo do lote {lote.codigo} mudou após a contagem; faça uma nova contagem física."
                )
            if contagem.quantidade_contada > lote.quantidade_maxima_auditada:
                justificativa = (contagem.observacao or "").strip()
                if not justificativa:
                    raise ValidationError(
                        f"Justifique a sobra física acima da capacidade do lote {lote.codigo}."
                    )
                capacidade_adicional_anterior = lote.quantidade_acrescimos_auditados
                acrescimo_autorizado = (
                    contagem.quantidade_contada - lote.quantidade_maxima_auditada
                )
                nova_capacidade_adicional = (
                    capacidade_adicional_anterior + acrescimo_autorizado
                )
                nova_capacidade = lote.quantidade_inicial + nova_capacidade_adicional
                aplicado_em = timezone.now()
                conteudo_retificacao = {
                    "contrato": "inventory_lot_capacity_rectification_v1",
                    "inventario_id": inventario.pk,
                    "lote_id": lote.pk,
                    "lote_codigo": lote.codigo,
                    "contagem_sha256": contagem.conteudo_sha256,
                    "quantidade_inicial": str(lote.quantidade_inicial),
                    "capacidade_adicional_anterior": str(capacidade_adicional_anterior),
                    "acrescimo_autorizado": str(acrescimo_autorizado),
                    "nova_capacidade": str(nova_capacidade),
                    "quantidade_contada": str(contagem.quantidade_contada),
                    "justificativa": justificativa,
                    "solicitado_por_id": contagem.contado_por_id,
                    "autorizado_por_id": supervisor.pk,
                    "aplicado_em": aplicado_em.isoformat(),
                }
                conteudo_sha256 = hashlib.sha256(
                    json.dumps(
                        conteudo_retificacao,
                        sort_keys=True,
                        separators=(",", ":"),
                        ensure_ascii=False,
                    ).encode("utf-8")
                ).hexdigest()
                retificacao = RetificacaoCapacidadeLoteEstoque.objects.create(
                    lote=lote,
                    inventario=inventario,
                    contagem=contagem,
                    quantidade_inicial_snapshot=lote.quantidade_inicial,
                    capacidade_adicional_anterior=capacidade_adicional_anterior,
                    acrescimo_autorizado=acrescimo_autorizado,
                    nova_capacidade=nova_capacidade,
                    quantidade_contada=contagem.quantidade_contada,
                    justificativa=justificativa,
                    solicitado_por=contagem.contado_por,
                    autorizado_por=supervisor,
                    aplicado_em=aplicado_em,
                    conteudo_sha256=conteudo_sha256,
                )
                lote.quantidade_acrescimos_auditados = nova_capacidade_adicional
                LogAuditoria.objects.create(
                    usuario=usuario,
                    modulo="estoque",
                    acao="RETIFICACAO_CAPACIDADE_LOTE",
                    descricao=(
                        f"Lote {lote.codigo}: capacidade adicional autorizada em "
                        f"{acrescimo_autorizado}; capacidade total {nova_capacidade}. "
                        f"Justificativa: {justificativa}.{_autorizacao_texto(supervisor)}"
                    ),
                    objeto_tipo="RetificacaoCapacidadeLoteEstoque",
                    objeto_id=str(retificacao.pk),
                    ip=ip,
                )
            diferenca_lote = contagem.quantidade_contada - lote.quantidade_atual
            if diferenca_lote == 0:
                continue
            movimentacao = MovimentacaoEstoque.objects.create(
                produto=item.produto,
                filial=inventario.filial,
                tipo=TipoMovimentacaoEstoque.AJUSTE,
                quantidade=diferenca_lote,
                motivo=f"Inventário por lote: {inventario.descricao}",
                referencia=f"inventario:{inventario.id}:lote:{lote.id}",
                usuario=usuario,
            )
            MovimentacaoLoteEstoque.objects.create(
                movimentacao=movimentacao,
                lote=lote,
                quantidade=abs(diferenca_lote),
                custo_unitario=lote.custo_unitario,
            )
            lote.quantidade_atual = contagem.quantidade_contada
            lote.full_clean()
            lote.save(update_fields=[
                "quantidade_atual", "quantidade_acrescimos_auditados", "atualizado_em"
            ])

        estoque.quantidade_atual = item.quantidade_contada
        estoque.full_clean()
        estoque.save(update_fields=["quantidade_atual", "atualizado_em"])

    inventario.status = StatusInventario.APLICADO
    inventario.aplicado_em = timezone.now()
    inventario.save(update_fields=["status", "aplicado_em"])
    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="estoque",
        acao="APLICACAO_INVENTARIO_VALIDADE_POR_LOTE",
        descricao=(
            f"Inventário {inventario.id} aplicado diretamente em {len(escopos)} lote(s), "
            f"com soma por produto validada.{_autorizacao_texto(supervisor)}"
        ),
        objeto_tipo="InventarioEstoque",
        objeto_id=str(inventario.id),
        ip=ip,
    )
    return inventario

@transaction.atomic
def aplicar_inventario(*, inventario, usuario, supervisor=None, ip=None):
    inventario = InventarioEstoque.objects.select_for_update().get(pk=inventario.pk)
    if inventario.status != StatusInventario.ABERTO:
        raise ValidationError("Apenas inventários abertos podem ser aplicados.")
    if inventario.prazo_operacional_expirado:
        raise ValidationError("O prazo operacional deste inventário expirou; abra um novo inventário.")

    itens = list(inventario.itens.select_related("produto"))
    if not itens:
        raise ValidationError("Inclua ao menos um item antes de aplicar o inventário.")
    pendentes = [item for item in itens if item.quantidade_contada is None]
    if pendentes:
        raise ValidationError(f"Existem {len(pendentes)} item(ns) sem contagem física.")
    if inventario.origem == OrigemInventario.DIVERGENCIA_VALIDADE:
        return _aplicar_inventario_divergencia_validade(
            inventario=inventario,
            itens=itens,
            usuario=usuario,
            supervisor=supervisor,
            ip=ip,
        )

    for item in itens:
        estoque, _ = Estoque.objects.select_for_update().get_or_create(produto=item.produto, filial=inventario.filial)
        item.quantidade_sistema = estoque.quantidade_atual
        item.diferenca = item.quantidade_contada - estoque.quantidade_atual
        item.save(update_fields=["quantidade_sistema", "diferenca"])

        estoque.quantidade_atual = item.quantidade_contada
        estoque.full_clean()
        estoque.save()

        if item.diferenca != 0:
            movimentacao = MovimentacaoEstoque.objects.create(
                produto=item.produto,
                filial=inventario.filial,
                tipo=TipoMovimentacaoEstoque.AJUSTE,
                quantidade=item.diferenca,
                motivo=f"Inventario: {inventario.descricao}",
                referencia=f"inventario:{inventario.id}",
                usuario=usuario,
            )
            if item.diferenca < 0:
                reconciliar_lotes_reducao_inventario(
                    produto=item.produto,
                    filial=inventario.filial,
                    saldo_novo=item.quantidade_contada,
                    movimentacao=movimentacao,
                )

    inventario.status = StatusInventario.APLICADO
    inventario.aplicado_em = timezone.now()
    inventario.save(update_fields=["status", "aplicado_em"])

    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="estoque",
        acao="APLICACAO_INVENTARIO",
        descricao=f"Inventario {inventario.id} aplicado com {len(itens)} item(ns).{_autorizacao_texto(supervisor)}",
        objeto_tipo="InventarioEstoque",
        objeto_id=str(inventario.id),
        ip=ip,
    )
    return inventario


@transaction.atomic
def registrar_perda_lote_validade(*, lote, quantidade, motivo, usuario, supervisor=None, ip=None):
    motivo = (motivo or "").strip()
    lote = LoteEstoque.objects.select_for_update().select_related("produto", "filial").get(pk=lote.pk)
    quantidade = Decimal(quantidade)
    if not motivo:
        raise ValidationError("Informe o motivo da perda.")
    if not lote.validade or lote.validade >= timezone.localdate():
        raise ValidationError("A baixa por vencimento exige lote efetivamente vencido.")
    if lote.tratamento_validade_status != StatusTratamentoValidade.DESCARTE_PLANEJADO:
        raise ValidationError("Registre primeiro o descarte planejado deste lote.")
    if quantidade <= 0 or quantidade > lote.quantidade_atual:
        raise ValidationError("A quantidade deve ser positiva e não pode superar o saldo do lote.")
    conferencia = conferencia_fisica_vigente_lote(lote)
    if not conferencia:
        raise ValidationError("Registre uma conferência física válida hoje antes da baixa.")
    if quantidade > conferencia.quantidade_observada:
        raise ValidationError("A baixa não pode superar a quantidade observada na conferência física.")
    perda = PerdaEstoque.objects.create(
        lote=lote, produto=lote.produto, filial=lote.filial, usuario=usuario,
        tipo=TipoPerdaEstoque.VENCIMENTO, quantidade=quantidade, motivo=motivo,
        custo_unitario_no_momento=lote.custo_unitario,
        preco_venda_no_momento=lote.produto.preco_venda,
        valor_custo_estimado=lote.custo_unitario * quantidade,
        valor_venda_estimado=lote.produto.preco_venda * quantidade,
    )
    movimentar_estoque(
        produto=lote.produto, filial=lote.filial, tipo=TipoMovimentacaoEstoque.PERDA,
        quantidade=quantidade, usuario=usuario, motivo=f"Perda/VENCIMENTO: {motivo}",
        referencia=f"perda:{perda.id}:lote:{lote.id}", custo_unitario=lote.custo_unitario,
        lote_id=lote.id,
    )
    lote.refresh_from_db()
    if lote.quantidade_atual == 0:
        lote.tratamento_validade_status = StatusTratamentoValidade.BAIXA_CONCLUIDA
        lote.tratamento_validade_por = usuario
        lote.tratamento_validade_em = timezone.now()
        lote.save(update_fields=["tratamento_validade_status", "tratamento_validade_por", "tratamento_validade_em", "atualizado_em"])
    LogAuditoria.objects.create(
        usuario=usuario, modulo="estoque", acao="REGISTRO_PERDA_LOTE_VALIDADE",
        descricao=(f"Perda {perda.id} vinculada ao lote {lote.codigo}: {quantidade}. {_autorizacao_texto(supervisor)}"),
        objeto_tipo="PerdaEstoque", objeto_id=str(perda.pk), ip=ip,
    )
    return perda

@transaction.atomic
def registrar_perda_estoque(*, produto, filial, usuario, tipo, quantidade, motivo, supervisor=None, ip=None):
    custo_unitario = produto.preco_custo
    preco_venda = produto.preco_venda
    perda = PerdaEstoque.objects.create(
        produto=produto,
        filial=filial,
        usuario=usuario,
        tipo=tipo,
        quantidade=quantidade,
        motivo=motivo,
        custo_unitario_no_momento=custo_unitario,
        preco_venda_no_momento=preco_venda,
        valor_custo_estimado=custo_unitario * quantidade,
        valor_venda_estimado=preco_venda * quantidade,
    )
    movimentar_estoque(
        produto=produto,
        filial=filial,
        tipo=TipoMovimentacaoEstoque.PERDA,
        quantidade=quantidade,
        usuario=usuario,
        motivo=f"Perda/{tipo}: {motivo}",
        referencia=f"perda:{perda.id}",
        custo_unitario=custo_unitario,
    )
    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="estoque",
        acao="REGISTRO_PERDA",
        descricao=f"Perda {perda.id}: {produto} - {quantidade}. Motivo: {motivo}.{_autorizacao_texto(supervisor)}",
        objeto_tipo="PerdaEstoque",
        objeto_id=str(perda.id),
        ip=ip,
    )
    return perda


@transaction.atomic
def confirmar_producao_composicao(
    *,
    composicao,
    filial,
    quantidade_final,
    usuario,
    motivo,
    observacao="",
    codigo_lote="",
    fabricacao=None,
    validade=None,
    supervisor=None,
    ip=None,
):
    if not motivo:
        raise ValidationError("Informe o motivo da produção.")
    if quantidade_final <= 0:
        raise ValidationError("Quantidade final da composição deve ser maior que zero.")

    composicao = (
        ComposicaoProduto.objects.select_for_update()
        .select_related("empresa", "filial", "produto_final")
        .prefetch_related("itens__produto_componente")
        .get(pk=composicao.pk)
    )
    if not composicao.is_active:
        raise ValidationError("Composição inativa não pode ser produzida.")
    if composicao.filial_id and composicao.filial_id != filial.id:
        raise ValidationError("Composição pertence a outra filial.")
    codigo_lote = (codigo_lote or "").strip()
    fabricacao = _normalizar_data_lote(fabricacao, "fabricacao")
    validade = _normalizar_data_lote(validade, "validade")
    if composicao.produto_final.exige_lote and not codigo_lote:
        raise ValidationError("O produto final exige lote.")
    if (fabricacao or validade) and not codigo_lote:
        raise ValidationError("Informe o lote ao preencher fabricação ou validade.")
    if fabricacao and validade and fabricacao > validade:
        raise ValidationError("A validade não pode ser anterior a fabricação.")

    itens_receita = list(composicao.itens.select_related("produto_componente"))
    if not itens_receita:
        raise ValidationError("Inclua ao menos um componente na composição.")
    fator = quantidade_final / composicao.quantidade_final

    consumos = []
    custo_total = Decimal("0.00")
    for item_receita in itens_receita:
        if item_receita.produto_componente_id == composicao.produto_final_id:
            raise ValidationError("Produto final não pode ser componente da própria composição.")
        quantidade_consumida = item_receita.quantidade * fator
        estoque_componente, _ = Estoque.objects.select_for_update().get_or_create(
            produto=item_receita.produto_componente,
            filial=filial,
        )
        if estoque_componente.quantidade_disponivel < quantidade_consumida:
            raise ValidationError(f"Estoque insuficiente do componente {item_receita.produto_componente}.")
        custo_unitario = Decimal(item_receita.produto_componente.preco_custo)
        custo_item = custo_unitario * quantidade_consumida
        custo_total += custo_item
        consumos.append((item_receita.produto_componente, quantidade_consumida, custo_unitario, custo_item, estoque_componente))

    producao = ProducaoComposicaoProduto.objects.create(
        composicao=composicao,
        empresa=filial.empresa,
        filial=filial,
        produto_final=composicao.produto_final,
        quantidade_final=quantidade_final,
        custo_total=custo_total,
        usuario=usuario,
        motivo=motivo,
        observacao=observacao,
    )

    for produto_componente, quantidade_consumida, custo_unitario, custo_item, estoque_componente in consumos:
        ItemProducaoComposicaoProduto.objects.create(
            producao=producao,
            produto_componente=produto_componente,
            quantidade_consumida=quantidade_consumida,
            custo_unitario=custo_unitario,
            custo_total=custo_item,
        )
        estoque_componente.quantidade_atual -= quantidade_consumida
        estoque_componente.full_clean()
        estoque_componente.save()
        movimento_componente = MovimentacaoEstoque.objects.create(
            produto=produto_componente,
            filial=filial,
            tipo=TipoMovimentacaoEstoque.DESMEMBRAMENTO,
            quantidade=-quantidade_consumida,
            motivo=f"Composicao {producao.id}: consumo de componente",
            referencia=f"composicao:{producao.id}:componente:{produto_componente.id}",
            custo_unitario=custo_unitario,
            custo_total=custo_item,
            usuario=usuario,
        )
        consumir_lotes_movimentacao(
            movimentacao=movimento_componente,
            quantidade=quantidade_consumida,
        )

    estoque_final, _ = Estoque.objects.select_for_update().get_or_create(produto=composicao.produto_final, filial=filial)
    estoque_final.quantidade_atual += quantidade_final
    estoque_final.full_clean()
    estoque_final.save()
    movimento_final = MovimentacaoEstoque.objects.create(
        produto=composicao.produto_final,
        filial=filial,
        tipo=TipoMovimentacaoEstoque.DESMEMBRAMENTO,
        quantidade=quantidade_final,
        motivo=f"Composicao {producao.id}: entrada do produto final",
        referencia=f"composicao:{producao.id}:final",
        custo_unitario=custo_total / quantidade_final,
        custo_total=custo_total,
        usuario=usuario,
    )
    if codigo_lote:
        criar_lote_movimentacao(
            movimentacao=movimento_final,
            codigo_lote=codigo_lote,
            quantidade=quantidade_final,
            custo_unitario=custo_total / quantidade_final,
            fabricacao=fabricacao,
            validade=validade,
        )

    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="estoque",
        acao="PRODUCAO_COMPOSICAO",
        descricao=(
            f"Composicao {producao.id}: {quantidade_final} de {composicao.produto_final} gerado "
            f"com {len(consumos)} componente(s). Motivo: {motivo}.{_autorizacao_texto(supervisor)}"
        ),
        objeto_tipo="ProducaoComposicaoProduto",
        objeto_id=str(producao.id),
        ip=ip,
    )
    return producao


@transaction.atomic
def cancelar_producao_composicao(*, producao, usuario, motivo, supervisor=None, ip=None):
    if not motivo:
        raise ValidationError("Informe o motivo do cancelamento.")

    producao = (
        ProducaoComposicaoProduto.objects.select_for_update()
        .select_related("filial", "produto_final")
        .prefetch_related("itens__produto_componente")
        .get(pk=producao.pk)
    )
    if producao.status != StatusProducaoComposicao.CONFIRMADO:
        raise ValidationError("Apenas composicoes confirmadas podem ser canceladas.")

    estoque_final, _ = Estoque.objects.select_for_update().get_or_create(produto=producao.produto_final, filial=producao.filial)
    if estoque_final.quantidade_disponivel < producao.quantidade_final:
        raise ValidationError("Produto final não possui saldo suficiente para cancelar a composição.")

    estoque_final.quantidade_atual -= producao.quantidade_final
    estoque_final.full_clean()
    estoque_final.save()
    movimento_final_cancelamento = MovimentacaoEstoque.objects.create(
        produto=producao.produto_final,
        filial=producao.filial,
        tipo=TipoMovimentacaoEstoque.DESMEMBRAMENTO,
        quantidade=-producao.quantidade_final,
        motivo=f"Cancelamento da composicao {producao.id}: {motivo}",
        referencia=f"composicao:{producao.id}:cancelamento:final",
        custo_unitario=producao.custo_total / producao.quantidade_final,
        custo_total=producao.custo_total,
        usuario=usuario,
    )
    movimento_final_origem = MovimentacaoEstoque.objects.filter(
        referencia=f"composicao:{producao.id}:final"
    ).first()
    alocacao_final = (
        movimento_final_origem.alocacoes_lote.select_related("lote").first()
        if movimento_final_origem
        else None
    )
    if alocacao_final:
        consumir_lotes_movimentacao(
            movimentacao=movimento_final_cancelamento,
            quantidade=producao.quantidade_final,
            lote_id=alocacao_final.lote_id,
            exigir_lote=True,
        )
    else:
        reconciliar_lotes_reducao_inventario(
            produto=producao.produto_final,
            filial=producao.filial,
            saldo_novo=estoque_final.quantidade_atual,
            movimentacao=movimento_final_cancelamento,
        )

    for item in producao.itens.select_related("produto_componente"):
        estoque_componente, _ = Estoque.objects.select_for_update().get_or_create(
            produto=item.produto_componente,
            filial=producao.filial,
        )
        estoque_componente.quantidade_atual += item.quantidade_consumida
        estoque_componente.full_clean()
        estoque_componente.save()
        movimento_reversao = MovimentacaoEstoque.objects.create(
            produto=item.produto_componente,
            filial=producao.filial,
            tipo=TipoMovimentacaoEstoque.DESMEMBRAMENTO,
            quantidade=item.quantidade_consumida,
            motivo=f"Cancelamento da composicao {producao.id}: retorno do componente",
            referencia=f"composicao:{producao.id}:cancelamento:componente:{item.id}",
            custo_unitario=item.custo_unitario,
            custo_total=item.custo_total,
            usuario=usuario,
        )
        movimento_origem = MovimentacaoEstoque.objects.filter(
            referencia=f"composicao:{producao.id}:componente:{item.produto_componente_id}"
        ).first()
        if movimento_origem:
            restaurar_lotes_movimentacao(
                movimentacao_origem=movimento_origem,
                movimentacao_reversao=movimento_reversao,
            )

    producao.status = StatusProducaoComposicao.CANCELADO
    producao.cancelado_em = timezone.now()
    producao.observacao = f"{producao.observacao}\nCancelado: {motivo}".strip()
    producao.save(update_fields=["status", "cancelado_em", "observacao"])

    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="estoque",
        acao="CANCELAMENTO_COMPOSICAO",
        descricao=f"Composicao {producao.id} cancelada. Motivo: {motivo}.{_autorizacao_texto(supervisor)}",
        objeto_tipo="ProducaoComposicaoProduto",
        objeto_id=str(producao.id),
        ip=ip,
    )
    return producao


@transaction.atomic
def confirmar_ordem_producao_composicao(
    *,
    ordem,
    usuario,
    codigo_lote="",
    fabricacao=None,
    validade=None,
    supervisor=None,
    ip=None,
):
    ordem = (
        OrdemProducaoComposicao.objects.select_for_update()
        .select_related("composicao", "filial", "produto_final")
        .get(pk=ordem.pk)
    )
    if ordem.status != StatusOrdemProducaoComposicao.PLANEJADA:
        raise ValidationError("Apenas ordens planejadas podem ser produzidas.")
    producao = confirmar_producao_composicao(
        composicao=ordem.composicao,
        filial=ordem.filial,
        quantidade_final=ordem.quantidade_planejada,
        usuario=usuario,
        motivo=f"Ordem de produção {ordem.id}: {ordem.motivo}",
        observacao=ordem.observacao,
        codigo_lote=codigo_lote,
        fabricacao=fabricacao,
        validade=validade,
        supervisor=supervisor,
        ip=ip,
    )
    ordem.status = StatusOrdemProducaoComposicao.PRODUZIDA
    ordem.producao_gerada = producao
    ordem.concluido_em = timezone.now()
    ordem.save(update_fields=["status", "producao_gerada", "concluido_em", "atualizado_em"])
    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="estoque",
        acao="ORDEM_PRODUCAO_COMPOSICAO_CONFIRMADA",
        descricao=f"Ordem de produção {ordem.id} confirmou a produção {producao.id}.{_autorizacao_texto(supervisor)}",
        objeto_tipo="OrdemProducaoComposicao",
        objeto_id=str(ordem.id),
        ip=ip,
    )
    return ordem


@transaction.atomic
def cancelar_ordem_producao_composicao(*, ordem, usuario, motivo, supervisor=None, ip=None):
    if not motivo:
        raise ValidationError("Informe o motivo do cancelamento.")
    ordem = OrdemProducaoComposicao.objects.select_for_update().get(pk=ordem.pk)
    if ordem.status != StatusOrdemProducaoComposicao.PLANEJADA:
        raise ValidationError("Apenas ordens planejadas podem ser canceladas.")
    ordem.status = StatusOrdemProducaoComposicao.CANCELADA
    ordem.observacao = f"{ordem.observacao}\nCancelada: {motivo}".strip()
    ordem.concluido_em = timezone.now()
    ordem.save(update_fields=["status", "observacao", "concluido_em", "atualizado_em"])
    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="estoque",
        acao="ORDEM_PRODUCAO_COMPOSICAO_CANCELADA",
        descricao=f"Ordem de produção {ordem.id} cancelada. Motivo: {motivo}.{_autorizacao_texto(supervisor)}",
        objeto_tipo="OrdemProducaoComposicao",
        objeto_id=str(ordem.id),
        ip=ip,
    )
    return ordem


@transaction.atomic
def confirmar_desmembramento_multidestino(
    *,
    filial,
    produto_origem,
    quantidade_origem,
    destinos,
    usuario,
    motivo,
    tipo=TipoDesmembramentoProduto.SIMPLES,
    observacao="",
    supervisor=None,
    ip=None,
):
    if quantidade_origem <= 0:
        raise ValidationError("As quantidades do desmembramento devem ser maiores que zero.")
    destinos = list(destinos or [])
    if not destinos:
        raise ValidationError("Inclua ao menos um produto destino no desmembramento.")
    for destino in destinos:
        if destino["quantidade"] <= 0:
            raise ValidationError("As quantidades do desmembramento devem ser maiores que zero.")
        if produto_origem == destino["produto"]:
            raise ValidationError("Produto origem e produto destino devem ser diferentes.")
        tipo_saida = destino.get("tipo_saida") or TipoSaidaDesmembramento.VENDAVEL
        if (
            tipo_saida != TipoSaidaDesmembramento.PERDA
            and destino["produto"].exige_lote
            and not (destino.get("lote") or "").strip()
        ):
            raise ValidationError(f"O produto destino {destino['produto']} exige lote.")

    estoque_origem, _ = Estoque.objects.select_for_update().get_or_create(produto=produto_origem, filial=filial)
    if estoque_origem.quantidade_disponivel < quantidade_origem:
        raise ValidationError("Estoque insuficiente para desmembrar o produto origem.")

    custo_origem = Decimal(produto_origem.preco_custo)
    custo_total_origem = custo_origem * quantidade_origem
    quantidade_total_destinos = sum(destino["quantidade"] for destino in destinos)
    if quantidade_total_destinos <= 0:
        raise ValidationError("As quantidades do desmembramento devem ser maiores que zero.")
    conservacao = _resumo_conservacao_massa(
        tipo=tipo,
        produto_origem=produto_origem,
        quantidade_origem=quantidade_origem,
        destinos=destinos,
    )
    if not conservacao["valida"]:
        if conservacao["excesso"]:
            detalhe = f"Excesso: {conservacao['excesso']:.3f} KG."
        else:
            detalhe = f"Quantidade não classificada: {conservacao['nao_classificada']:.3f} KG."
        raise ValidationError(
            f"Conservação de massa inválida: {quantidade_origem:.3f} KG de origem devem corresponder "
            f"aos {quantidade_total_destinos:.3f} KG de destinos, incluindo perdas. {detalhe}"
        )
    custo_unitario_base = custo_total_origem / quantidade_total_destinos

    desmembramento = DesmembramentoProduto.objects.create(
        empresa=filial.empresa,
        filial=filial,
        produto_origem=produto_origem,
        quantidade_origem=quantidade_origem,
        custo_total_origem=custo_total_origem,
        tipo=tipo,
        usuario=usuario,
        motivo=motivo,
        observacao=observacao,
    )

    estoque_origem.quantidade_atual -= quantidade_origem
    estoque_origem.full_clean()
    estoque_origem.save()
    movimento_origem = MovimentacaoEstoque.objects.create(
        produto=produto_origem,
        filial=filial,
        tipo=TipoMovimentacaoEstoque.DESMEMBRAMENTO,
        quantidade=-quantidade_origem,
        motivo=f"Desmembramento {desmembramento.id}: {motivo}",
        referencia=f"desmembramento:{desmembramento.id}:origem",
        custo_unitario=custo_origem,
        custo_total=custo_total_origem,
        usuario=usuario,
    )
    consumir_lotes_movimentacao(
        movimentacao=movimento_origem,
        quantidade=quantidade_origem,
    )

    for destino in destinos:
        produto_destino = destino["produto"]
        quantidade_destino = destino["quantidade"]
        tipo_saida = destino.get("tipo_saida") or TipoSaidaDesmembramento.VENDAVEL
        custo_total_item = custo_unitario_base * quantidade_destino
        percentual_rendimento = ((quantidade_destino / quantidade_origem) * Decimal("100")).quantize(Decimal("0.01"))
        item = ItemDesmembramentoProduto.objects.create(
            desmembramento=desmembramento,
            produto_destino=produto_destino,
            quantidade_gerada=quantidade_destino,
            unidade=produto_destino.unidade,
            custo_unitario_calculado=custo_unitario_base,
            custo_total=custo_total_item,
            percentual_rendimento=percentual_rendimento,
            percentual_rendimento_esperado=destino.get("percentual_rendimento_esperado"),
            lote=destino.get("lote", ""),
            validade=destino.get("validade"),
            tipo_saida=tipo_saida,
        )
        if tipo_saida == TipoSaidaDesmembramento.PERDA:
            preco_venda_destino = Decimal(produto_destino.preco_venda)
            PerdaEstoque.objects.create(
                produto=produto_destino,
                filial=filial,
                usuario=usuario,
                desmembramento_item=item,
                tipo=TipoPerdaEstoque.QUEBRA,
                quantidade=quantidade_destino,
                motivo=f"Desmembramento {desmembramento.id}: {motivo}",
                custo_unitario_no_momento=custo_unitario_base,
                preco_venda_no_momento=preco_venda_destino,
                valor_custo_estimado=custo_total_item,
                valor_venda_estimado=preco_venda_destino * quantidade_destino,
            )
            MovimentacaoEstoque.objects.create(
                produto=produto_destino,
                filial=filial,
                tipo=TipoMovimentacaoEstoque.PERDA,
                quantidade=-quantidade_destino,
                motivo=f"Desmembramento {desmembramento.id}: perda/descarte gerado",
                referencia=f"desmembramento:{desmembramento.id}:perda:item:{item.id}",
                custo_unitario=custo_unitario_base,
                custo_total=custo_total_item,
                usuario=usuario,
            )
        else:
            estoque_destino, _ = Estoque.objects.select_for_update().get_or_create(produto=produto_destino, filial=filial)
            estoque_destino.quantidade_atual += quantidade_destino
            estoque_destino.full_clean()
            estoque_destino.save()
            movimento_destino = MovimentacaoEstoque.objects.create(
                produto=produto_destino,
                filial=filial,
                tipo=TipoMovimentacaoEstoque.DESMEMBRAMENTO,
                quantidade=quantidade_destino,
                motivo=f"Desmembramento {desmembramento.id}: entrada de destino",
                referencia=f"desmembramento:{desmembramento.id}:item:{item.id}",
                custo_unitario=custo_unitario_base,
                custo_total=custo_total_item,
                usuario=usuario,
            )
            if item.lote:
                criar_lote_movimentacao(
                    movimentacao=movimento_destino,
                    codigo_lote=item.lote,
                    quantidade=quantidade_destino,
                    custo_unitario=custo_unitario_base,
                    validade=item.validade,
                )

    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="estoque",
        acao="DESMEMBRAMENTO_PRODUTO",
        descricao=(
            f"Desmembramento {desmembramento.id}: {quantidade_origem} de {produto_origem} gerou "
            f"{len(destinos)} destino(s). Motivo: {motivo}.{_autorizacao_texto(supervisor)}"
        ),
        objeto_tipo="DesmembramentoProduto",
        objeto_id=str(desmembramento.id),
        ip=ip,
    )
    return desmembramento


def confirmar_desmembramento_simples(
    *,
    filial,
    produto_origem,
    quantidade_origem,
    produto_destino,
    quantidade_destino,
    usuario,
    motivo,
    tipo=TipoDesmembramentoProduto.SIMPLES,
    tipo_saida_destino=TipoSaidaDesmembramento.VENDAVEL,
    observacao="",
    supervisor=None,
    ip=None,
):
    return confirmar_desmembramento_multidestino(
        filial=filial,
        produto_origem=produto_origem,
        quantidade_origem=quantidade_origem,
        destinos=[{"produto": produto_destino, "quantidade": quantidade_destino, "tipo_saida": tipo_saida_destino}],
        usuario=usuario,
        motivo=motivo,
        tipo=tipo,
        observacao=observacao,
        supervisor=supervisor,
        ip=ip,
    )


def simular_desmembramento_multidestino(
    *,
    filial,
    produto_origem,
    quantidade_origem,
    destinos,
    tipo=TipoDesmembramentoProduto.SIMPLES,
    **_,
):
    if quantidade_origem <= 0:
        raise ValidationError("As quantidades do desmembramento devem ser maiores que zero.")
    destinos = list(destinos or [])
    if not destinos:
        raise ValidationError("Inclua ao menos um produto destino no desmembramento.")
    for destino in destinos:
        if destino["quantidade"] <= 0:
            raise ValidationError("As quantidades do desmembramento devem ser maiores que zero.")
        if produto_origem == destino["produto"]:
            raise ValidationError("Produto origem e produto destino devem ser diferentes.")

    estoque_origem = Estoque.objects.filter(produto=produto_origem, filial=filial).first()
    saldo_origem = estoque_origem.quantidade_disponivel if estoque_origem else Decimal("0.000")
    custo_origem = Decimal(produto_origem.preco_custo)
    custo_total_origem = custo_origem * quantidade_origem
    quantidade_total_destinos = sum(destino["quantidade"] for destino in destinos)
    if quantidade_total_destinos <= 0:
        raise ValidationError("As quantidades do desmembramento devem ser maiores que zero.")
    conservacao = _resumo_conservacao_massa(
        tipo=tipo,
        produto_origem=produto_origem,
        quantidade_origem=quantidade_origem,
        destinos=destinos,
    )
    custo_unitario_destino = custo_total_origem / quantidade_total_destinos
    destinos_previstos = [
        {
            "produto": destino["produto"],
            "quantidade": destino["quantidade"],
            "tipo_saida": destino.get("tipo_saida") or TipoSaidaDesmembramento.VENDAVEL,
            "percentual_rendimento_esperado": destino.get("percentual_rendimento_esperado"),
            "percentual_rendimento": ((destino["quantidade"] / quantidade_origem) * Decimal("100")).quantize(Decimal("0.01")),
            "rendimento_abaixo_esperado": (
                destino.get("percentual_rendimento_esperado") is not None
                and ((destino["quantidade"] / quantidade_origem) * Decimal("100")).quantize(Decimal("0.01"))
                < destino.get("percentual_rendimento_esperado")
            ),
            "lote": destino.get("lote", ""),
            "validade": destino.get("validade"),
            "custo_total": custo_unitario_destino * destino["quantidade"],
        }
        for destino in destinos
    ]

    return {
        "filial": filial,
        "produto_origem": produto_origem,
        "quantidade_origem": quantidade_origem,
        "quantidade_destino": quantidade_total_destinos,
        "destinos": destinos_previstos,
        "saldo_origem": saldo_origem,
        "saldo_origem_apos": saldo_origem - quantidade_origem,
        "estoque_suficiente": saldo_origem >= quantidade_origem,
        "custo_total_origem": custo_total_origem,
        "custo_unitario_destino": custo_unitario_destino,
        "conservacao_massa_aplicada": conservacao["aplicavel"],
        "conservacao_massa_valida": conservacao["valida"],
        "excesso_quantidade": conservacao["excesso"],
        "quantidade_nao_classificada": conservacao["nao_classificada"],
        "rendimento_total": conservacao["rendimento_total"],
    }


def simular_desmembramento_simples(*, filial, produto_origem, quantidade_origem, produto_destino, quantidade_destino, **kwargs):
    return simular_desmembramento_multidestino(
        filial=filial,
        produto_origem=produto_origem,
        quantidade_origem=quantidade_origem,
        destinos=[
            {
                "produto": produto_destino,
                "quantidade": quantidade_destino,
                "tipo_saida": kwargs.get("tipo_saida_destino") or TipoSaidaDesmembramento.VENDAVEL,
                "percentual_rendimento_esperado": kwargs.get("percentual_rendimento_esperado"),
                "lote": kwargs.get("lote", ""),
                "validade": kwargs.get("validade"),
            }
        ],
    )


@transaction.atomic
def cancelar_desmembramento_produto(*, desmembramento, usuario, motivo, supervisor=None, ip=None):
    if not motivo:
        raise ValidationError("Informe o motivo do cancelamento.")

    desmembramento = (
        DesmembramentoProduto.objects.select_for_update()
        .select_related("filial", "produto_origem")
        .prefetch_related("itens__produto_destino")
        .get(pk=desmembramento.pk)
    )
    if desmembramento.status != StatusDesmembramentoProduto.CONFIRMADO:
        raise ValidationError("Apenas desmembramentos confirmados podem ser cancelados.")

    estoque_origem, _ = Estoque.objects.select_for_update().get_or_create(
        produto=desmembramento.produto_origem,
        filial=desmembramento.filial,
    )
    itens = list(desmembramento.itens.select_related("produto_destino"))
    if not itens:
        raise ValidationError("Desmembramento sem itens de destino não pode ser cancelado.")

    estoques_destino = {}
    for item in itens:
        if item.tipo_saida == TipoSaidaDesmembramento.PERDA:
            continue
        estoque_destino, _ = Estoque.objects.select_for_update().get_or_create(
            produto=item.produto_destino,
            filial=desmembramento.filial,
        )
        if estoque_destino.quantidade_disponivel < item.quantidade_gerada:
            raise ValidationError(
                f"Produto destino {item.produto_destino} nao possui saldo suficiente para reverter o desmembramento."
            )
        estoques_destino[item.id] = estoque_destino

    for item in itens:
        if item.tipo_saida == TipoSaidaDesmembramento.PERDA:
            item.perdas_geradas.all().delete()
            MovimentacaoEstoque.objects.create(
                produto=item.produto_destino,
                filial=desmembramento.filial,
                tipo=TipoMovimentacaoEstoque.PERDA,
                quantidade=item.quantidade_gerada,
                motivo=f"Cancelamento do desmembramento {desmembramento.id}: perda/descarte revertida",
                referencia=f"desmembramento:{desmembramento.id}:cancelamento:perda:item:{item.id}",
                custo_unitario=item.custo_unitario_calculado,
                custo_total=item.custo_total,
                usuario=usuario,
            )
            continue
        estoque_destino = estoques_destino[item.id]
        estoque_destino.quantidade_atual -= item.quantidade_gerada
        estoque_destino.full_clean()
        estoque_destino.save()
        movimento_cancelamento = MovimentacaoEstoque.objects.create(
            produto=item.produto_destino,
            filial=desmembramento.filial,
            tipo=TipoMovimentacaoEstoque.DESMEMBRAMENTO,
            quantidade=-item.quantidade_gerada,
            motivo=f"Cancelamento do desmembramento {desmembramento.id}: {motivo}",
            referencia=f"desmembramento:{desmembramento.id}:cancelamento:item:{item.id}",
            custo_unitario=item.custo_unitario_calculado,
            custo_total=item.custo_total,
            usuario=usuario,
        )
        if item.lote:
            consumir_lotes_movimentacao(
                movimentacao=movimento_cancelamento,
                quantidade=item.quantidade_gerada,
                codigo_lote=item.lote,
                exigir_lote=True,
            )
        else:
            reconciliar_lotes_reducao_inventario(
                produto=item.produto_destino,
                filial=desmembramento.filial,
                saldo_novo=estoque_destino.quantidade_atual,
                movimentacao=movimento_cancelamento,
            )

    estoque_origem.quantidade_atual += desmembramento.quantidade_origem
    estoque_origem.full_clean()
    estoque_origem.save()
    movimento_retorno_origem = MovimentacaoEstoque.objects.create(
        produto=desmembramento.produto_origem,
        filial=desmembramento.filial,
        tipo=TipoMovimentacaoEstoque.DESMEMBRAMENTO,
        quantidade=desmembramento.quantidade_origem,
        motivo=f"Cancelamento do desmembramento {desmembramento.id}: retorno da origem",
        referencia=f"desmembramento:{desmembramento.id}:cancelamento:origem",
        custo_unitario=desmembramento.custo_total_origem / desmembramento.quantidade_origem,
        custo_total=desmembramento.custo_total_origem,
        usuario=usuario,
    )
    movimento_baixa_origem = MovimentacaoEstoque.objects.filter(
        referencia=f"desmembramento:{desmembramento.id}:origem"
    ).first()
    if movimento_baixa_origem:
        restaurar_lotes_movimentacao(
            movimentacao_origem=movimento_baixa_origem,
            movimentacao_reversao=movimento_retorno_origem,
        )

    desmembramento.status = StatusDesmembramentoProduto.CANCELADO
    desmembramento.cancelado_em = timezone.now()
    desmembramento.observacao = f"{desmembramento.observacao}\nCancelado: {motivo}".strip()
    desmembramento.save(update_fields=["status", "cancelado_em", "observacao"])

    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="estoque",
        acao="CANCELAMENTO_DESMEMBRAMENTO",
        descricao=f"Desmembramento {desmembramento.id} cancelado. Motivo: {motivo}.{_autorizacao_texto(supervisor)}",
        objeto_tipo="DesmembramentoProduto",
        objeto_id=str(desmembramento.id),
        ip=ip,
    )
    return desmembramento
