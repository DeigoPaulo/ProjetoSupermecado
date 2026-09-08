from apps.compras.models import EntradaCompra, StatusEntradaCompra
from apps.empresas.models import Filial
from apps.vendas.models import StatusVenda, Venda

from .diagnostico_snapshots import diagnostico_prontidao_piloto_real
from .models import (
    FechamentoEstoqueContabil,
    InventarioEstoque,
    PerdaEstoque,
    StatusInventario,
    TipoPerdaEstoque,
)


CONTRATO_PREVIA_PILOTO = "inventory_pilot_candidate_preview_v1"
LIMITE_MAXIMO_POR_TIPO = 100


def _produtos_dos_itens(objeto):
    return sorted({item.produto_id for item in objeto.itens.all()})


def _candidato(objeto, *, data, produto_ids):
    return {
        "id": objeto.pk,
        "data": data.isoformat() if data else None,
        "produto_ids": produto_ids,
        "produtos_total": len(produto_ids),
    }


def previsualizar_candidatos_piloto(*, filial_id, limite_por_tipo=20):
    """Lista candidatos recentes sem escolher IDs, alterar dados ou acessar a rede."""
    if limite_por_tipo < 1 or limite_por_tipo > LIMITE_MAXIMO_POR_TIPO:
        raise ValueError(
            f"O limite por tipo deve ficar entre 1 e {LIMITE_MAXIMO_POR_TIPO}."
        )
    filial = Filial.objects.select_related("empresa").get(pk=filial_id)
    prontidao = diagnostico_prontidao_piloto_real(filial_id=filial.pk)

    entradas = list(
        EntradaCompra.objects.filter(
            filial=filial, status=StatusEntradaCompra.FINALIZADA
        )
        .prefetch_related("itens")
        .order_by("-data_recebimento", "-id")[:limite_por_tipo]
    )
    vendas = list(
        Venda.objects.filter(
            filial=filial,
            status=StatusVenda.FINALIZADA,
            documentos_fiscais__isnull=True,
        )
        .prefetch_related("itens")
        .order_by("-data", "-id")[:limite_por_tipo]
    )
    perdas = list(
        PerdaEstoque.objects.filter(
            filial=filial,
            tipo=TipoPerdaEstoque.VENCIMENTO,
            lote__isnull=False,
        )
        .order_by("-data", "-id")[:limite_por_tipo]
    )
    inventarios = list(
        InventarioEstoque.objects.filter(
            filial=filial, status=StatusInventario.APLICADO
        )
        .prefetch_related("itens")
        .order_by("-aplicado_em", "-id")[:limite_por_tipo]
    )
    fechamentos = list(
        FechamentoEstoqueContabil.objects.filter(filial=filial)
        .prefetch_related("itens")
        .order_by("-data_referencia", "-id")[:limite_por_tipo]
    )

    candidatos = {
        "entradas": [
            _candidato(
                item,
                data=item.data_recebimento,
                produto_ids=_produtos_dos_itens(item),
            )
            for item in entradas
        ],
        "vendas_sem_documento_fiscal": [
            _candidato(item, data=item.data, produto_ids=_produtos_dos_itens(item))
            for item in vendas
        ],
        "perdas_por_vencimento_com_lote": [
            _candidato(item, data=item.data, produto_ids=[item.produto_id])
            for item in perdas
        ],
        "inventarios_aplicados": [
            _candidato(
                item,
                data=item.aplicado_em,
                produto_ids=_produtos_dos_itens(item),
            )
            for item in inventarios
        ],
        "fechamentos": [
            _candidato(
                item,
                data=item.data_referencia,
                produto_ids=_produtos_dos_itens(item),
            )
            for item in fechamentos
        ],
    }
    produtos_por_tipo = []
    for itens in candidatos.values():
        produtos_por_tipo.append(
            {produto_id for item in itens for produto_id in item["produto_ids"]}
        )
    produtos_com_fluxo_completo = sorted(set.intersection(*produtos_por_tipo))

    impedimentos = []
    if not prontidao["pronta_para_aceite"]:
        impedimentos.append(
            {
                "codigo": prontidao["estado"],
                "mensagem": prontidao["motivo"],
            }
        )
    rotulos = {
        "entradas": "entrada finalizada",
        "vendas_sem_documento_fiscal": "venda finalizada sem documento fiscal",
        "perdas_por_vencimento_com_lote": "perda por vencimento vinculada a lote",
        "inventarios_aplicados": "inventário aplicado",
        "fechamentos": "fechamento de estoque",
    }
    for chave, itens in candidatos.items():
        if not itens:
            impedimentos.append(
                {
                    "codigo": f"SEM_{chave.upper()}",
                    "mensagem": f"Nenhum candidato recente para {rotulos[chave]}.",
                }
            )
    if all(candidatos.values()) and not produtos_com_fluxo_completo:
        impedimentos.append(
            {
                "codigo": "SEM_PRODUTO_COMUM_NA_JANELA",
                "mensagem": "Os candidatos recentes não compartilham um mesmo produto nas cinco etapas.",
            }
        )

    return {
        "contrato": CONTRATO_PREVIA_PILOTO,
        "filial": {
            "id": filial.pk,
            "nome": filial.nome,
            "empresa_id": filial.empresa_id,
            "empresa_nome": filial.empresa.nome_fantasia,
        },
        "limite_por_tipo": limite_por_tipo,
        "janela_limitada": True,
        "seleciona_automaticamente": False,
        "somente_leitura": True,
        "comunicacao_externa": False,
        "prontidao_piloto_real": prontidao,
        "candidatos": candidatos,
        "produtos_com_fluxo_completo": produtos_com_fluxo_completo,
        "possui_candidatos_compativeis": bool(produtos_com_fluxo_completo),
        "impedimentos": impedimentos,
    }
