from collections import OrderedDict

from django.utils import timezone

from apps.empresas.models import Filial

from .models import (
    MovimentacaoLoteEstoque,
    STATUS_TRATAMENTO_LOTE_VENDAVEL,
    TipoMovimentacaoEstoque,
)


CONTRATO_DIAGNOSTICO_SNAPSHOTS_LOTE = "inventory_lot_snapshot_coverage_v1"


def _estado_cobertura(*, total, legadas, inconsistentes):
    if not total:
        return "SEM_VENDAS", "Sem vendas por lote", "info"
    if inconsistentes:
        return "INCONSISTENTE", "Requer investigação", "danger"
    if legadas:
        return "PARCIAL", "Cobertura parcial", "warning"
    return "COMPLETA", "Cobertura completa", "success"


def diagnostico_cobertura_snapshots_lote():
    """Mede cobertura histórica das vendas por lote sem alterar qualquer registro."""
    filiais = list(
        Filial.objects.select_related("empresa").order_by(
            "empresa__nome_fantasia", "nome", "id"
        )
    )
    linhas = OrderedDict()
    for filial in filiais:
        linhas[filial.pk] = {
            "filial_id": filial.pk,
            "filial_nome": filial.nome,
            "empresa_id": filial.empresa_id,
            "empresa_nome": filial.empresa.nome_fantasia,
            "total": 0,
            "integras": 0,
            "legadas": 0,
            "inconsistentes": 0,
        }

    campos = (
        "movimentacao_id",
        "movimentacao__filial_id",
        "movimentacao__data",
        "lote_id",
        "quantidade",
        "custo_unitario",
        "lote_codigo_snapshot",
        "lote_validade_snapshot",
        "tratamento_status_snapshot",
        "snapshot_sha256",
    )
    alocacoes = (
        MovimentacaoLoteEstoque.objects.filter(
            movimentacao__tipo=TipoMovimentacaoEstoque.VENDA
        )
        .values(*campos)
        .order_by("movimentacao__filial_id", "id")
    )
    for alocacao in alocacoes.iterator(chunk_size=1000):
        linha = linhas.get(alocacao["movimentacao__filial_id"])
        if linha is None:
            continue
        linha["total"] += 1
        codigo = alocacao["lote_codigo_snapshot"]
        tratamento = alocacao["tratamento_status_snapshot"]
        hash_registrado = alocacao["snapshot_sha256"]
        if not codigo or not tratamento or not hash_registrado:
            linha["legadas"] += 1
            continue
        hash_esperado = MovimentacaoLoteEstoque.calcular_snapshot_sha256(
            movimentacao_id=alocacao["movimentacao_id"],
            lote_id=alocacao["lote_id"],
            quantidade=alocacao["quantidade"],
            custo_unitario=alocacao["custo_unitario"],
            lote_codigo=codigo,
            lote_validade=alocacao["lote_validade_snapshot"],
            tratamento_status=tratamento,
        )
        data_venda = timezone.localdate(alocacao["movimentacao__data"])
        validade = alocacao["lote_validade_snapshot"]
        elegivel_na_venda = (
            tratamento in STATUS_TRATAMENTO_LOTE_VENDAVEL
            and (validade is None or validade >= data_venda)
        )
        if hash_registrado != hash_esperado or not elegivel_na_venda:
            linha["inconsistentes"] += 1
        else:
            linha["integras"] += 1

    totais = {"total": 0, "integras": 0, "legadas": 0, "inconsistentes": 0}
    resultado_filiais = []
    for linha in linhas.values():
        estado, estado_display, nivel = _estado_cobertura(
            total=linha["total"],
            legadas=linha["legadas"],
            inconsistentes=linha["inconsistentes"],
        )
        linha.update(
            {
                "estado": estado,
                "estado_display": estado_display,
                "nivel": nivel,
                "cobertura_percentual": round(
                    (linha["integras"] * 100 / linha["total"]), 2
                ) if linha["total"] else None,
                "cobertura_display": (
                    f"{round(linha['integras'] * 100 / linha['total'], 2)}%"
                    if linha["total"] else "Sem base"
                ),
            }
        )
        for chave in totais:
            totais[chave] += linha[chave]
        resultado_filiais.append(linha)

    estado, estado_display, nivel = _estado_cobertura(
        total=totais["total"],
        legadas=totais["legadas"],
        inconsistentes=totais["inconsistentes"],
    )
    totais.update(
        {
            "estado": estado,
            "estado_display": estado_display,
            "nivel": nivel,
            "cobertura_percentual": round(
                totais["integras"] * 100 / totais["total"], 2
            ) if totais["total"] else None,
            "cobertura_display": (
                f"{round(totais['integras'] * 100 / totais['total'], 2)}%"
                if totais["total"] else "Sem base"
            ),
        }
    )
    return {
        "contrato": CONTRATO_DIAGNOSTICO_SNAPSHOTS_LOTE,
        "escopo": "VENDAS_COM_ALOCACAO_POR_LOTE",
        "somente_leitura": True,
        "corrige_automaticamente": False,
        "totais": totais,
        "filiais": resultado_filiais,
    }
