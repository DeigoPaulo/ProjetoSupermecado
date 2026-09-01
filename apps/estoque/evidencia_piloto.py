import hashlib
import json
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.compras.models import EntradaCompra, StatusEntradaCompra
from apps.fiscal.models import DocumentoFiscal
from apps.vendas.models import StatusVenda, Venda

from .diagnostico_snapshots import diagnostico_prontidao_piloto_real
from .models import (
    Estoque,
    FechamentoEstoqueContabil,
    InventarioEstoque,
    LoteEstoque,
    MovimentacaoEstoque,
    MovimentacaoLoteEstoque,
    PerdaEstoque,
    STATUS_TRATAMENTO_LOTE_VENDAVEL,
    StatusInventario,
    TipoMovimentacaoEstoque,
)


CONTRATO_EVIDENCIA_PILOTO = "inventory_pilot_end_to_end_evidence_v3"


def _falhar_se(condicao, mensagem):
    if condicao:
        raise ValidationError(mensagem)


def gerar_evidencia_fluxo_estoque_piloto(
    *, entrada_id, venda_id, perda_id, inventario_id, fechamento_id, momento=None,
    dados_sinteticos=False,
):
    """Confere vínculos persistidos sem alterar dados nem acessar serviços externos."""
    momento = momento or timezone.now()
    entrada = EntradaCompra.objects.prefetch_related("itens").get(pk=entrada_id)
    venda = Venda.objects.prefetch_related("itens").get(pk=venda_id)
    perda = PerdaEstoque.objects.select_related("lote").get(pk=perda_id)
    inventario = InventarioEstoque.objects.prefetch_related(
        "itens__origens_validade__conferencia",
        "itens__escopos_validade__lote",
        "itens__escopos_validade__contagens",
    ).get(pk=inventario_id)
    fechamento = FechamentoEstoqueContabil.objects.prefetch_related("itens").get(
        pk=fechamento_id
    )

    filial_ids = {
        entrada.filial_id,
        venda.filial_id,
        perda.filial_id,
        inventario.filial_id,
        fechamento.filial_id,
    }
    _falhar_se(len(filial_ids) != 1, "Os registros do ensaio devem pertencer à mesma filial.")
    _falhar_se(entrada.status != StatusEntradaCompra.FINALIZADA, "A entrada do ensaio não está finalizada.")
    _falhar_se(venda.status != StatusVenda.FINALIZADA, "A venda do ensaio não está finalizada.")
    _falhar_se(inventario.status != StatusInventario.APLICADO, "O inventário do ensaio não está aplicado.")

    produtos_entrada = set(entrada.itens.values_list("produto_id", flat=True))
    produtos_venda = set(venda.itens.values_list("produto_id", flat=True))
    produtos_inventario = set(inventario.itens.values_list("produto_id", flat=True))
    produtos_fechamento = set(fechamento.itens.values_list("produto_id", flat=True))
    produtos_comuns = (
        produtos_entrada
        & produtos_venda
        & produtos_inventario
        & produtos_fechamento
        & {perda.produto_id}
    )
    _falhar_se(len(produtos_comuns) != 1, "O ensaio deve possuir um único produto comum em todas as etapas.")
    produto_id = produtos_comuns.pop()

    movimentos_compra = MovimentacaoEstoque.objects.filter(
        filial_id=entrada.filial_id,
        produto_id=produto_id,
        tipo=TipoMovimentacaoEstoque.ENTRADA,
        referencia=f"entrada_compra:{entrada.pk}",
    )
    camadas_compra = MovimentacaoLoteEstoque.objects.filter(
        movimentacao__in=movimentos_compra
    ).select_related("lote")
    movimento_venda = MovimentacaoEstoque.objects.filter(
        filial_id=venda.filial_id,
        produto_id=produto_id,
        tipo=TipoMovimentacaoEstoque.VENDA,
        referencia=f"venda:{venda.pk}",
    ).first()
    camadas_venda = list(
        MovimentacaoLoteEstoque.objects.filter(movimentacao=movimento_venda)
        .select_related("lote")
        .order_by("lote__validade", "lote_id")
    ) if movimento_venda else []
    movimento_perda = MovimentacaoEstoque.objects.filter(
        filial_id=perda.filial_id,
        produto_id=produto_id,
        tipo=TipoMovimentacaoEstoque.PERDA,
        referencia=f"perda:{perda.pk}:lote:{perda.lote_id}",
    ).first()
    camada_perda = MovimentacaoLoteEstoque.objects.filter(
        movimentacao=movimento_perda, lote_id=perda.lote_id
    ).first() if movimento_perda else None
    movimentos_inventario = MovimentacaoEstoque.objects.filter(
        filial_id=inventario.filial_id,
        produto_id=produto_id,
        tipo=TipoMovimentacaoEstoque.AJUSTE,
        referencia__startswith=f"inventario:{inventario.pk}:lote:",
    )
    camadas_inventario = MovimentacaoLoteEstoque.objects.filter(
        movimentacao__in=movimentos_inventario
    )
    origens_inventario = inventario.itens.filter(produto_id=produto_id).values_list(
        "origens_validade__lote_id", flat=True
    )
    estoque = Estoque.objects.get(filial_id=entrada.filial_id, produto_id=produto_id)
    saldo_lotes = sum(
        (
            lote.quantidade_atual
            for lote in LoteEstoque.objects.filter(produto_id=produto_id, filial_id=entrada.filial_id)
        ),
        Decimal("0.000"),
    )
    item_fechamento = fechamento.itens.get(produto_id=produto_id)

    hoje = timezone.localdate(momento)
    data_venda = timezone.localdate(movimento_venda.data) if movimento_venda else hoje
    snapshots_venda = [
        {
            "lote_id": camada.lote_id,
            "codigo": camada.lote_codigo_snapshot,
            "validade": (
                camada.lote_validade_snapshot.isoformat()
                if camada.lote_validade_snapshot else None
            ),
            "tratamento_status": camada.tratamento_status_snapshot,
            "quantidade": str(camada.quantidade),
            "snapshot_sha256": camada.snapshot_sha256,
            "snapshot_integro": camada.snapshot_integro,
        }
        for camada in camadas_venda
    ]
    verificacoes = {
        "entrada_finalizada": entrada.status == StatusEntradaCompra.FINALIZADA,
        "entrada_criou_camadas": camadas_compra.count() == entrada.itens.filter(produto_id=produto_id).count(),
        "venda_finalizada": venda.status == StatusVenda.FINALIZADA,
        "nenhum_documento_fiscal_criado": not DocumentoFiscal.objects.filter(venda=venda).exists(),
        "venda_possui_alocacao_lote": bool(camadas_venda),
        "venda_snapshot_lote_preservado": bool(camadas_venda) and all(
            camada.lote_codigo_snapshot and camada.snapshot_integro for camada in camadas_venda
        ),
        "venda_nao_consumiu_lote_vencido": bool(camadas_venda) and all(
            camada.lote_validade_snapshot is None
            or camada.lote_validade_snapshot >= data_venda
            for camada in camadas_venda
        ),
        "venda_consumiu_somente_tratamento_liberado": bool(camadas_venda) and all(
            camada.tratamento_status_snapshot in STATUS_TRATAMENTO_LOTE_VENDAVEL
            for camada in camadas_venda
        ),
        "perda_vinculada_ao_lote_exato": bool(camada_perda) and perda.lote_id == camada_perda.lote_id,
        "perda_lote_vencido": bool(perda.lote.validade and perda.lote.validade < hoje),
        "inventario_originado_no_lote_divergente": perda.lote_id in set(origens_inventario),
        "inventario_ajustou_lote_exato": camadas_inventario.filter(lote_id=perda.lote_id).exists(),
        "saldo_agregado_confere_com_lotes": estoque.quantidade_atual == saldo_lotes,
        "fechamento_confere_com_saldo_final": item_fechamento.quantidade_fisica == estoque.quantidade_atual,
        "fechamento_possui_hash": len(fechamento.conteudo_sha256 or "") == 64,
    }
    prontidao_piloto_real = diagnostico_prontidao_piloto_real(
        filial_id=entrada.filial_id
    )
    prontidao_piloto_real["aplicada_ao_aceite"] = not dados_sinteticos
    if not dados_sinteticos:
        verificacoes["filial_pronta_para_piloto_real"] = prontidao_piloto_real[
            "pronta_para_aceite"
        ]
    payload = {
        "contrato": CONTRATO_EVIDENCIA_PILOTO,
        "gerado_em": momento.isoformat(),
        "filial_id": entrada.filial_id,
        "produto_id": produto_id,
        "objetos": {
            "entrada_id": entrada.pk,
            "venda_id": venda.pk,
            "perda_id": perda.pk,
            "inventario_id": inventario.pk,
            "fechamento_id": fechamento.pk,
        },
        "alocacoes_venda_snapshot": snapshots_venda,
        "prontidao_piloto_real": prontidao_piloto_real,
        "quantidades": {
            "entrada": str(sum((item.quantidade for item in entrada.itens.filter(produto_id=produto_id)), Decimal("0.000"))),
            "venda": str(sum((item.quantidade for item in venda.itens.filter(produto_id=produto_id)), Decimal("0.000"))),
            "perda": str(perda.quantidade),
            "saldo_final": str(estoque.quantidade_atual),
            "saldo_lotes": str(saldo_lotes),
        },
        "verificacoes": verificacoes,
        "valida": all(verificacoes.values()),
        "somente_leitura": True,
        "comunicacao_externa": False,
        "dados_sinteticos": bool(dados_sinteticos),
    }
    payload["conteudo_sha256"] = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return payload
