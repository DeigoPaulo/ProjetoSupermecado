import hashlib
import json

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction

from .services_sincronizacao import enfileirar_evento


def _revisao_payload(payload):
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:24]


def _categoria_hierarquia_payload(categoria):
    itens = []
    atual = categoria
    visitados = set()
    while atual and atual.pk not in visitados:
        itens.append({"nome": atual.nome, "nivel": atual.nivel})
        visitados.add(atual.pk)
        atual = atual.parent
    return list(reversed(itens))


def _informacao_nutricional_payload(produto):
    try:
        informacao = produto.informacao_nutricional
    except ObjectDoesNotExist:
        return None
    campos_decimais = (
        "porcao_quantidade", "porcoes_por_embalagem", "valor_energetico_kcal",
        "carboidratos_g", "acucares_totais_g", "acucares_adicionados_g",
        "proteinas_g", "gorduras_totais_g", "gorduras_saturadas_g",
        "gorduras_trans_g", "fibra_alimentar_g", "sodio_mg",
    )
    payload = {
        "base_calculo": informacao.base_calculo,
        "porcao_unidade": informacao.porcao_unidade,
        "medida_caseira": informacao.medida_caseira,
        "ingredientes": informacao.ingredientes,
        "alergicos": informacao.alergicos,
        "gluten": informacao.gluten,
        "lactose": informacao.lactose,
    }
    payload.update({
        campo: str(getattr(informacao, campo)) if getattr(informacao, campo) is not None else None
        for campo in campos_decimais
    })
    return payload


def _produtos_similares_payload(produto):
    return [
        {
            "codigo_barras": similar.codigo_barras,
            "codigo_interno": similar.codigo_interno,
            "nome": similar.nome,
        }
        for similar in produto.produtos_similares.order_by("codigo_barras")
    ]


def produto_snapshot_payload(produto, *, empresa=None):
    return {
        "contrato": "produto_snapshot_v1",
        "codigo_barras": produto.codigo_barras,
        "codigo_interno": produto.codigo_interno,
        "nome": produto.nome,
        "descricao": produto.descricao,
        "categoria": {"nome": produto.categoria.nome},
        "categoria_hierarquia": _categoria_hierarquia_payload(produto.categoria),
        "tipo_produto": produto.tipo_produto,
        "marca": {"nome": produto.marca.nome} if produto.marca else None,
        "unidade": produto.unidade,
        "unidade_compra": produto.unidade_compra,
        "fator_conversao_compra": str(produto.fator_conversao_compra),
        "peso_liquido": str(produto.peso_liquido) if produto.peso_liquido is not None else None,
        "peso_bruto": str(produto.peso_bruto) if produto.peso_bruto is not None else None,
        "codigos_adicionais": [
            {
                "codigo": item.codigo,
                "tipo": item.tipo,
                "fator_conversao": str(item.fator_conversao),
                "permite_venda": item.permite_venda,
                "is_active": item.is_active,
            }
            for item in produto.codigos_adicionais.order_by("id")
        ],
        "configuracoes_balanca": [
            {
                "setor_codigo": item.setor.codigo,
                "setor_nome": item.setor.nome,
                "plu": item.plu,
                "tara_kg": str(item.tara_kg),
                "validade_dias": item.validade_dias,
                "is_active": item.is_active,
            }
            for item in produto.configuracoes_balanca.select_related("setor").filter(
                empresa=empresa
            ).order_by("setor__codigo", "plu")
        ] if empresa else [],        "produto_pesavel": produto.produto_pesavel,
        "preco_custo": str(produto.preco_custo),
        "margem_desejada_percentual": (
            str(produto.margem_desejada_percentual)
            if produto.margem_desejada_percentual is not None
            else None
        ),
        "preco_venda": str(produto.preco_venda),
        "preco_promocional": str(produto.preco_promocional) if produto.preco_promocional is not None else None,
        "estoque_minimo": str(produto.estoque_minimo),
        "exige_lote": produto.exige_lote,
        "vendido_no_pdv": produto.vendido_no_pdv,
        "vendido_no_marketplace": produto.vendido_no_marketplace,
        "informacao_nutricional": _informacao_nutricional_payload(produto),
        "produtos_similares": _produtos_similares_payload(produto),
        "ncm": produto.ncm,
        "cest": produto.cest,
        "origem_mercadoria": produto.origem_mercadoria,
        "cst_icms": produto.cst_icms,
        "csosn": produto.csosn,
        "aliquota_icms": str(produto.aliquota_icms or 0),
        "reducao_base_icms": str(produto.reducao_base_icms) if produto.reducao_base_icms is not None else None,
        "aliquota_fcp": str(produto.aliquota_fcp) if produto.aliquota_fcp is not None else None,
        "codigo_beneficio_fiscal": produto.codigo_beneficio_fiscal,
        "cst_pis": produto.cst_pis,
        "aliquota_pis": str(produto.aliquota_pis) if produto.aliquota_pis is not None else None,
        "cst_cofins": produto.cst_cofins,
        "aliquota_cofins": str(produto.aliquota_cofins) if produto.aliquota_cofins is not None else None,
        "cst_ipi": produto.cst_ipi,
        "codigo_enquadramento_ipi": produto.codigo_enquadramento_ipi,
        "aliquota_ipi": str(produto.aliquota_ipi) if produto.aliquota_ipi is not None else None,
        "cst_ibs_cbs": produto.cst_ibs_cbs,
        "classificacao_tributaria_ibs_cbs": produto.classificacao_tributaria_ibs_cbs,
        "is_active": produto.is_active,
    }


def enfileirar_snapshot_produto(*, produto, empresa, filial=None):
    payload = produto_snapshot_payload(produto, empresa=empresa)
    revisao = _revisao_payload(payload)
    return enfileirar_evento(
        empresa=empresa,
        filial=filial,
        tipo="produto.atualizado",
        objeto_tipo="Produto",
        objeto_id=produto.pk,
        chave_idempotencia=f"produto:{empresa.pk}:{produto.pk}:snapshot:{revisao}",
        payload=payload,
    )


def estoque_snapshot_payload(estoque, *, movimentacao=None):
    payload = {
        "contrato": "estoque_saldo_v1",
        "codigo_barras": estoque.produto.codigo_barras,
        "codigo_interno": estoque.produto.codigo_interno,
        "produto_id": estoque.produto_id,
        "filial_cnpj": estoque.filial.cnpj,
        "filial_nome": estoque.filial.nome,
        "quantidade_atual": str(estoque.quantidade_atual),
        "quantidade_reservada": str(estoque.quantidade_reservada),
        "custo_medio": str(estoque.custo_medio),
    }
    if movimentacao:
        payload["movimentacao"] = {
            "id": movimentacao.pk,
            "tipo": movimentacao.tipo,
            "quantidade": str(movimentacao.quantidade),
            "motivo": movimentacao.motivo,
            "referencia": movimentacao.referencia,
            "data": movimentacao.data.isoformat(),
        }
    else:
        payload["origem"] = "carga_inicial"
    return payload


def enfileirar_snapshot_estoque(*, estoque, movimentacao=None):
    payload = estoque_snapshot_payload(estoque, movimentacao=movimentacao)
    if movimentacao:
        chave = f"estoque:{estoque.filial_id}:{estoque.produto_id}:movimentacao:{movimentacao.pk}"
    else:
        chave = f"estoque:{estoque.filial_id}:{estoque.produto_id}:snapshot:{_revisao_payload(payload)}"
    return enfileirar_evento(
        empresa=estoque.filial.empresa,
        filial=estoque.filial,
        tipo="estoque.saldo_atualizado",
        objeto_tipo="Estoque",
        objeto_id=estoque.pk,
        chave_idempotencia=chave,
        payload=payload,
    )

@transaction.atomic
def gerar_carga_inicial_sincronizacao(*, empresa, filial=None, limite=5000):
    from apps.estoque.models import Estoque

    if not empresa.sincronizacao_operacional_habilitada:
        raise ValueError("A empresa deve estar em modo hibrido/agente, com sincronizacao automática e URL HTTPS ativa.")
    if filial and filial.empresa_id != empresa.pk:
        raise ValueError("Filial não encontrada para a empresa informada.")

    try:
        limite = int(limite)
    except (TypeError, ValueError) as exc:
        raise ValueError("Informe um limite numerico valido.") from exc
    limite = max(1, min(limite, 100000))

    estoques = Estoque.objects.filter(filial__empresa=empresa).select_related(
        "produto",
        "produto__categoria",
        "produto__marca",
        "filial",
        "filial__empresa",
    )
    if filial:
        estoques = estoques.filter(filial=filial)

    resultado = {
        "estoques_processados": 0,
        "produtos_criados": 0,
        "saldos_criados": 0,
        "limite": limite,
    }
    for estoque in estoques.order_by("produto_id", "filial_id")[:limite]:
        _, produto_criado = enfileirar_snapshot_produto(
            produto=estoque.produto,
            empresa=empresa,
            filial=estoque.filial,
        )
        _, saldo_criado = enfileirar_snapshot_estoque(estoque=estoque)
        resultado["produtos_criados"] += int(produto_criado)
        resultado["saldos_criados"] += int(saldo_criado)
        resultado["estoques_processados"] += 1
    return resultado
