import hashlib
import json

from django.db import transaction

from .services_sincronizacao import enfileirar_evento


def _revisao_payload(payload):
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:24]


def produto_snapshot_payload(produto):
    return {
        "contrato": "produto_snapshot_v1",
        "codigo_barras": produto.codigo_barras,
        "codigo_interno": produto.codigo_interno,
        "nome": produto.nome,
        "descricao": produto.descricao,
        "categoria": {"nome": produto.categoria.nome},
        "marca": {"nome": produto.marca.nome} if produto.marca else None,
        "unidade": produto.unidade,
        "produto_pesavel": produto.produto_pesavel,
        "preco_custo": str(produto.preco_custo),
        "preco_venda": str(produto.preco_venda),
        "preco_promocional": str(produto.preco_promocional) if produto.preco_promocional is not None else None,
        "estoque_minimo": str(produto.estoque_minimo),
        "exige_lote": produto.exige_lote,
        "vendido_no_pdv": produto.vendido_no_pdv,
        "vendido_no_marketplace": produto.vendido_no_marketplace,
        "ncm": produto.ncm,
        "cest": produto.cest,
        "origem_mercadoria": produto.origem_mercadoria,
        "cst_icms": produto.cst_icms,
        "csosn": produto.csosn,
        "aliquota_icms": str(produto.aliquota_icms or 0),
        "is_active": produto.is_active,
    }


def enfileirar_snapshot_produto(*, produto, empresa, filial=None):
    payload = produto_snapshot_payload(produto)
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

    from .models import ModoImplantacao

    if empresa.modo_implantacao == ModoImplantacao.LOCAL or not empresa.sincronizacao_automatica:
        raise ValueError("A empresa deve estar em modo hibrido/agente com sincronizacao automatica ativa.")
    if filial and filial.empresa_id != empresa.pk:
        raise ValueError("Filial nao encontrada para a empresa informada.")

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
