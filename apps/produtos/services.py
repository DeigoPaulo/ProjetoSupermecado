import csv
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from io import TextIOWrapper

from django.db import transaction

from apps.auditoria.models import LogAuditoria

from .models import Categoria, Marca, Produto, UnidadeMedida


CABECALHOS_OBRIGATORIOS = {"codigo_barras", "nome", "categoria", "preco_venda"}


def _decimal(valor, padrao="0"):
    if valor in [None, ""]:
        return Decimal(padrao)
    texto = str(valor).strip().replace(".", "").replace(",", ".")
    try:
        return Decimal(texto)
    except InvalidOperation as exc:
        raise ValueError(f"Valor decimal invalido: {valor}") from exc


def _boolean(valor):
    return str(valor or "").strip().lower() in {"1", "sim", "s", "true", "verdadeiro", "yes"}


def _unidade(valor):
    valor = str(valor or UnidadeMedida.UNIDADE).strip().upper()
    choices = {choice[0] for choice in UnidadeMedida.choices}
    return valor if valor in choices else UnidadeMedida.UNIDADE


@transaction.atomic
def importar_produtos_csv(arquivo, *, atualizar_existentes=True):
    stream = TextIOWrapper(arquivo.file, encoding="utf-8-sig")
    reader = csv.DictReader(stream, delimiter=";")
    if reader.fieldnames and len(reader.fieldnames) == 1:
        stream.seek(0)
        reader = csv.DictReader(stream, delimiter=",")

    fieldnames = {campo.strip() for campo in (reader.fieldnames or [])}
    faltando = CABECALHOS_OBRIGATORIOS - fieldnames
    if faltando:
        raise ValueError(f"Cabecalhos obrigatorios ausentes: {', '.join(sorted(faltando))}")

    criados = 0
    atualizados = 0
    ignorados = 0
    erros = []

    for numero_linha, row in enumerate(reader, start=2):
        try:
            codigo = (row.get("codigo_barras") or "").strip()
            nome = (row.get("nome") or "").strip()
            categoria_nome = (row.get("categoria") or "").strip()
            if not codigo or not nome or not categoria_nome:
                raise ValueError("codigo_barras, nome e categoria sao obrigatorios.")

            categoria, _ = Categoria.all_objects.get_or_create(nome=categoria_nome)
            marca = None
            marca_nome = (row.get("marca") or "").strip()
            if marca_nome:
                marca, _ = Marca.all_objects.get_or_create(nome=marca_nome)

            dados = {
                "codigo_interno": (row.get("codigo_interno") or "").strip(),
                "nome": nome,
                "descricao": (row.get("descricao") or "").strip(),
                "categoria": categoria,
                "marca": marca,
                "unidade": _unidade(row.get("unidade")),
                "produto_pesavel": _boolean(row.get("produto_pesavel")),
                "preco_custo": _decimal(row.get("preco_custo"), "0"),
                "preco_venda": _decimal(row.get("preco_venda"), "0"),
                "estoque_minimo": _decimal(row.get("estoque_minimo"), "0"),
                "vendido_no_pdv": not str(row.get("vendido_no_pdv") or "").strip() or _boolean(row.get("vendido_no_pdv")),
                "vendido_no_marketplace": _boolean(row.get("vendido_no_marketplace")),
                "is_active": not str(row.get("is_active") or "").strip() or _boolean(row.get("is_active")),
            }

            produto = Produto.all_objects.filter(codigo_barras=codigo).first()
            if produto:
                if not atualizar_existentes:
                    ignorados += 1
                    continue
                for campo, valor in dados.items():
                    setattr(produto, campo, valor)
                produto.save()
                atualizados += 1
            else:
                Produto.all_objects.create(codigo_barras=codigo, **dados)
                criados += 1
        except Exception as exc:
            erros.append(f"Linha {numero_linha}: {exc}")

    return {
        "criados": criados,
        "atualizados": atualizados,
        "ignorados": ignorados,
        "erros": erros,
    }


def produtos_para_reajuste(*, categoria=None, marca=None):
    queryset = Produto.objects.select_related("categoria", "marca").order_by("nome")
    if categoria:
        queryset = queryset.filter(categoria=categoria)
    if marca:
        queryset = queryset.filter(marca=marca)
    return queryset


def calcular_preco_reajustado(valor, percentual):
    fator = Decimal("1") + (percentual / Decimal("100"))
    return (valor * fator).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def simular_reajuste_precos(*, categoria=None, marca=None, percentual, aplicar_em_promocional=False):
    produtos = produtos_para_reajuste(categoria=categoria, marca=marca)
    preview = []
    for produto in produtos[:100]:
        item = {
            "produto": produto,
            "preco_venda_atual": produto.preco_venda,
            "preco_venda_novo": calcular_preco_reajustado(produto.preco_venda, percentual),
            "preco_promocional_atual": produto.preco_promocional,
            "preco_promocional_novo": None,
        }
        if aplicar_em_promocional and produto.preco_promocional is not None:
            item["preco_promocional_novo"] = calcular_preco_reajustado(produto.preco_promocional, percentual)
        preview.append(item)
    return preview, produtos.count()


@transaction.atomic
def aplicar_reajuste_precos(*, usuario, categoria=None, marca=None, percentual, motivo, aplicar_em_promocional=False, supervisor=None, ip=None):
    produtos = list(produtos_para_reajuste(categoria=categoria, marca=marca).select_for_update())
    for produto in produtos:
        produto.preco_venda = calcular_preco_reajustado(produto.preco_venda, percentual)
        update_fields = ["preco_venda", "updated_at"]
        if aplicar_em_promocional and produto.preco_promocional is not None:
            produto.preco_promocional = calcular_preco_reajustado(produto.preco_promocional, percentual)
            update_fields.append("preco_promocional")
        produto.save(update_fields=update_fields)

    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="produtos",
        acao="REAJUSTE_PRECO_MASSA",
        descricao=(
            f"Reajuste de {percentual}% aplicado em {len(produtos)} produto(s). "
            f"Categoria={categoria or '-'}; Marca={marca or '-'}; Motivo={motivo}; "
            f"Autorizado por={supervisor or '-'}"
        ),
        objeto_tipo="Produto",
        objeto_id="lote",
        ip=ip,
    )
    return len(produtos)
