from .models import Produto


CONTRATO_INVENTARIO_CBENEF_LEGADO = "produto_cbenef_legado_inventory_v1"
ESTADO_FALLBACK_EMISSIVO = "AINDA_EXISTE_CONSUMIDOR_EMISSIVO"
DECISAO_REMOCAO_COLUNA = "NAO_PODE_REMOVER_COLUNA"


def diagnostico_cbenef_legado():
    produtos = Produto.all_objects.exclude(codigo_beneficio_fiscal="").order_by("pk")
    itens = list(
        produtos.values(
            "id",
            "codigo_barras",
            "codigo_interno",
            "codigo_beneficio_fiscal",
        )
    )
    return {
        "contrato": CONTRATO_INVENTARIO_CBENEF_LEGADO,
        "quantidade_produtos": len(itens),
        "produtos": itens,
        "estado_fallback_emissivo": ESTADO_FALLBACK_EMISSIVO,
        "decisao_remocao_coluna": DECISAO_REMOCAO_COLUNA,
        "somente_leitura": True,
    }
