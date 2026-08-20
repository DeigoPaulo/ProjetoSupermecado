import csv
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from io import TextIOWrapper

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.auditoria.models import LogAuditoria

from .models import (
    Categoria, Marca, OrigemMercadoria, Produto, StatusVersaoPreco, UnidadeMedida, VersaoPrecoProduto,
)


CABECALHOS_OBRIGATORIOS = {"codigo_barras", "nome", "categoria", "preco_venda"}
MODOS_IMPORTACAO = {"", "completo", "fiscal"}


def _decimal(valor, padrao="0"):
    if valor in [None, ""]:
        return Decimal(padrao)
    texto = str(valor).strip()
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return Decimal(texto)
    except InvalidOperation as exc:
        raise ValueError(f"Valor decimal invalido: {valor}") from exc


def _decimal_opcional(valor, rotulo):
    if valor in [None, ""]:
        return None
    resultado = _decimal(valor)
    if resultado < 0 or resultado > 100:
        raise ValueError(f"{rotulo} deve estar entre 0 e 100.")
    return resultado


def _codigo_numerico(valor, tamanho, rotulo):
    texto = str(valor or "").strip()
    codigo = "".join(filter(str.isdigit, texto))
    if codigo and len(codigo) != tamanho:
        raise ValueError(f"{rotulo} deve possuir {tamanho} digitos.")
    return codigo


def _origem_mercadoria(valor):
    origem = str(valor or "").strip()
    permitidas = {codigo for codigo, _rotulo in OrigemMercadoria.choices}
    if origem and origem not in permitidas:
        raise ValueError("Origem da mercadoria invalida.")
    return origem


def _boolean(valor):
    return str(valor or "").strip().lower() in {"1", "sim", "s", "true", "verdadeiro", "yes"}


def _unidade(valor):
    valor = str(valor or UnidadeMedida.UNIDADE).strip().upper()
    choices = {choice[0] for choice in UnidadeMedida.choices}
    return valor if valor in choices else UnidadeMedida.UNIDADE


@transaction.atomic
def importar_produtos_csv(
    arquivo,
    *,
    atualizar_existentes=True,
    usuario=None,
    ip=None,
):
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
    fiscais_atualizados = 0
    ignorados = 0
    erros = []

    for numero_linha, row in enumerate(reader, start=2):
        try:
            row = {
                str(chave).strip(): valor
                for chave, valor in row.items()
                if chave is not None
            }
            codigo = (row.get("codigo_barras") or "").strip()
            nome = (row.get("nome") or "").strip()
            categoria_nome = (row.get("categoria") or "").strip()
            modo_importacao = (row.get("_modo_importacao") or "").strip().lower()
            if modo_importacao not in MODOS_IMPORTACAO:
                raise ValueError("Modo de importacao invalido.")
            if not codigo or not nome or not categoria_nome:
                raise ValueError("codigo_barras, nome e categoria são obrigatorios.")

            produto = Produto.all_objects.filter(codigo_barras=codigo).first()
            if modo_importacao == "fiscal" and not produto:
                raise ValueError(
                    "Produto nao encontrado. A planilha fiscal atualiza apenas produtos existentes."
                )

            dados = {}
            marca = None
            if modo_importacao != "fiscal":
                categoria, _ = Categoria.all_objects.get_or_create(nome=categoria_nome)
                marca_nome = (row.get("marca") or "").strip()
                if marca_nome:
                    marca, _ = Marca.all_objects.get_or_create(nome=marca_nome)
                dados.update(
                    {
                        "nome": nome,
                        "categoria": categoria,
                        "preco_venda": _decimal(row.get("preco_venda"), "0"),
                    }
                )
            campos_comerciais_opcionais = {
                "codigo_interno": lambda valor: str(valor or "").strip(),
                "descricao": lambda valor: str(valor or "").strip(),
                "marca": lambda _valor: marca,
                "unidade": _unidade,
                "produto_pesavel": _boolean,
                "preco_custo": lambda valor: _decimal(valor, "0"),
                "estoque_minimo": lambda valor: _decimal(valor, "0"),
                "vendido_no_pdv": _boolean,
                "vendido_no_marketplace": _boolean,
                "is_active": _boolean,
            }
            for campo, normalizar in campos_comerciais_opcionais.items():
                if modo_importacao != "fiscal" and campo in fieldnames:
                    dados[campo] = normalizar(row.get(campo))


            campos_fiscais = {}
            normalizadores_fiscais = {
                "ncm": lambda valor: _codigo_numerico(valor, 8, "NCM"),
                "cest": lambda valor: _codigo_numerico(valor, 7, "CEST"),
                "origem_mercadoria": _origem_mercadoria,
                "cst_icms": lambda valor: _codigo_numerico(valor, 2, "CST ICMS"),
                "csosn": lambda valor: _codigo_numerico(valor, 3, "CSOSN"),
                "aliquota_icms": lambda valor: _decimal_opcional(valor, "Aliquota ICMS"),
                "reducao_base_icms": lambda valor: _decimal_opcional(valor, "Reducao da base ICMS"),
                "aliquota_fcp": lambda valor: _decimal_opcional(valor, "Aliquota FCP"),
                "codigo_beneficio_fiscal": lambda valor: str(valor or "").strip().upper(),
                "cst_pis": lambda valor: _codigo_numerico(valor, 2, "CST PIS"),
                "aliquota_pis": lambda valor: _decimal_opcional(valor, "Aliquota PIS"),
                "cst_cofins": lambda valor: _codigo_numerico(valor, 2, "CST COFINS"),
                "aliquota_cofins": lambda valor: _decimal_opcional(valor, "Aliquota COFINS"),
                "cst_ipi": lambda valor: _codigo_numerico(valor, 2, "CST IPI"),
                "codigo_enquadramento_ipi": lambda valor: _codigo_numerico(
                    valor, 3, "Codigo de enquadramento IPI"
                ),
                "aliquota_ipi": lambda valor: _decimal_opcional(valor, "Aliquota IPI"),
                "cst_ibs_cbs": lambda valor: _codigo_numerico(valor, 3, "CST IBS/CBS"),
                "classificacao_tributaria_ibs_cbs": lambda valor: _codigo_numerico(
                    valor, 6, "Classificacao tributaria IBS/CBS"
                ),
            }
            for campo, normalizar in normalizadores_fiscais.items():
                if campo in fieldnames:
                    campos_fiscais[campo] = normalizar(row.get(campo))
            dados.update(campos_fiscais)

            if produto:
                if not atualizar_existentes:
                    ignorados += 1
                    continue
                for campo, valor in dados.items():
                    setattr(produto, campo, valor)
                produto.full_clean()
                produto.save()
                atualizados += 1
                if modo_importacao == "fiscal":
                    fiscais_atualizados += 1
            else:
                produto = Produto(codigo_barras=codigo, **dados)
                produto.full_clean()
                produto.save()
                criados += 1
        except Exception as exc:
            erros.append(f"Linha {numero_linha}: {exc}")

    resultado = {
        "criados": criados,
        "atualizados": atualizados,
        "fiscais_atualizados": fiscais_atualizados,
        "ignorados": ignorados,
        "erros": erros,
    }
    if usuario:
        LogAuditoria.objects.create(
            usuario=usuario,
            modulo="produtos",
            acao="IMPORTA_PRODUTOS_CSV",
            descricao=(
                f"Importacao CSV concluida: {criados} criado(s), "
                f"{atualizados} atualizado(s) "
                f"({fiscais_atualizados} somente fiscal), {ignorados} ignorado(s) "
                f"e {len(erros)} linha(s) com erro."
            ),
            objeto_tipo="Produto",
            objeto_id="lote",
            ip=ip,
        )
    return resultado


def produtos_para_reajuste(*, categoria=None, marca=None):
    queryset = Produto.objects.select_related("categoria", "marca").order_by("nome")
    if categoria:
        queryset = queryset.filter(categoria=categoria)
    if marca:
        queryset = queryset.filter(marca=marca)
    return queryset


def calcular_preco_reajustado(valor, percentual):
    fator = Decimal("1") + (percentual / Decimal("100"))
    resultado = (valor * fator).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if resultado <= 0:
        raise ValidationError("O reajuste resultaria em preço menor ou igual a zero.")
    return resultado


def calcular_margem_preco(*, preco, custo):
    preco = Decimal(preco or 0)
    custo = Decimal(custo or 0)
    if preco <= 0:
        return None
    return ((preco - custo) / preco * Decimal("100")).quantize(Decimal("0.01"))


def _simular_item_reajuste(produto, percentual, aplicar_em_promocional):
    preco_venda_novo = calcular_preco_reajustado(produto.preco_venda, percentual)
    preco_promocional_novo = None
    if aplicar_em_promocional and produto.preco_promocional is not None:
        preco_promocional_novo = calcular_preco_reajustado(produto.preco_promocional, percentual)
    margem_nova = calcular_margem_preco(preco=preco_venda_novo, custo=produto.preco_custo)
    margem_promocional_nova = (
        calcular_margem_preco(preco=preco_promocional_novo, custo=produto.preco_custo)
        if preco_promocional_novo is not None
        else None
    )
    margem_desejada = produto.margem_desejada_percentual
    abaixo_margem = margem_desejada is not None and (
        (margem_nova is not None and margem_nova < margem_desejada)
        or (margem_promocional_nova is not None and margem_promocional_nova < margem_desejada)
    )
    return {
        "produto": produto,
        "preco_venda_atual": produto.preco_venda,
        "preco_venda_novo": preco_venda_novo,
        "preco_promocional_atual": produto.preco_promocional,
        "preco_promocional_novo": preco_promocional_novo,
        "margem_nova": margem_nova,
        "margem_promocional_nova": margem_promocional_nova,
        "abaixo_margem": abaixo_margem,
    }


def simular_reajuste_precos(*, categoria=None, marca=None, percentual, aplicar_em_promocional=False):
    produtos = produtos_para_reajuste(categoria=categoria, marca=marca)
    preview = [
        _simular_item_reajuste(produto, percentual, aplicar_em_promocional)
        for produto in produtos[:100]
    ]
    return preview, produtos.count()


@transaction.atomic
def aplicar_reajuste_precos(
    *, usuario, categoria=None, marca=None, percentual, motivo, aplicar_em_promocional=False,
    permitir_abaixo_margem=False, supervisor=None, ip=None
):
    produtos = list(produtos_para_reajuste(categoria=categoria, marca=marca).select_for_update())
    simulacoes = [_simular_item_reajuste(produto, percentual, aplicar_em_promocional) for produto in produtos]
    violacoes = [item for item in simulacoes if item["abaixo_margem"]]
    if violacoes and not permitir_abaixo_margem:
        raise ValidationError(
            f"O reajuste deixaria {len(violacoes)} produto(s) abaixo da margem desejada. "
            "Revise a simulação ou marque a autorização excepcional."
        )
    if violacoes and permitir_abaixo_margem and not supervisor:
        raise ValidationError("A exceção de margem exige autorização de supervisor ou administrador.")

    for item in simulacoes:
        produto = item["produto"]
        produto.preco_venda = item["preco_venda_novo"]
        update_fields = ["preco_venda", "updated_at"]
        if item["preco_promocional_novo"] is not None:
            produto.preco_promocional = item["preco_promocional_novo"]
            update_fields.append("preco_promocional")
        produto.save(update_fields=update_fields)

    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="produtos",
        acao="REAJUSTE_PRECO_MASSA",
        descricao=(
            f"Reajuste de {percentual}% aplicado em {len(produtos)} produto(s). "
            f"Categoria={categoria or '-'}; Marca={marca or '-'}; Motivo={motivo}; "
            f"Abaixo da margem={len(violacoes)}; Exceção autorizada={'Sim' if violacoes else 'Não'}; "
            f"Autorizado por={supervisor or '-'}"
        ),
        objeto_tipo="Produto",
        objeto_id="lote",
        ip=ip,
    )
    return len(produtos)


def preco_base_atual_produto(produto, momento=None):
    momento = momento or timezone.now()
    versao = (
        VersaoPrecoProduto.objects.filter(
            produto=produto,
            status=StatusVersaoPreco.AGENDADA,
            vigencia_inicio__lte=momento,
        )
        .order_by("-vigencia_inicio", "-versao")
        .first()
    )
    return versao.preco_novo if versao else produto.preco_venda


@transaction.atomic
def criar_versao_preco(
    *, produto, preco_novo, vigencia_inicio, motivo, usuario,
    permitir_abaixo_margem=False, supervisor=None, ip=None,
):
    produto = Produto.all_objects.select_for_update().get(pk=produto.pk)
    preco_novo = Decimal(preco_novo).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if preco_novo <= 0:
        raise ValidationError("O novo preço deve ser maior que zero.")
    margem_nova = calcular_margem_preco(preco=preco_novo, custo=produto.preco_custo)
    abaixo_margem = (
        produto.margem_desejada_percentual is not None
        and margem_nova is not None
        and margem_nova < produto.margem_desejada_percentual
    )
    if abaixo_margem and not permitir_abaixo_margem:
        raise ValidationError("O novo preço fica abaixo da margem desejada do produto.")
    if abaixo_margem and not supervisor:
        raise ValidationError("A exceção de margem exige autorização de supervisor ou administrador.")

    ultima_versao = (
        VersaoPrecoProduto.objects.filter(produto=produto).aggregate(numero=Max("versao"))["numero"] or 0
    )
    preco_anterior = preco_base_atual_produto(produto, momento=vigencia_inicio)
    versao = VersaoPrecoProduto.objects.create(
        produto=produto,
        versao=ultima_versao + 1,
        preco_anterior=preco_anterior,
        preco_novo=preco_novo,
        vigencia_inicio=vigencia_inicio,
        motivo=motivo,
        criado_por=usuario,
    )
    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="produtos",
        acao="AGENDAR_PRECO",
        descricao=(
            f"Preço v{versao.versao} agendado para {produto}: R$ {preco_anterior} -> R$ {preco_novo}; "
            f"vigência={vigencia_inicio.isoformat()}; motivo={motivo}; abaixo da margem={'Sim' if abaixo_margem else 'Não'}; "
            f"autorizado por={supervisor or '-'}"
        ),
        objeto_tipo="VersaoPrecoProduto",
        objeto_id=str(versao.pk),
        ip=ip,
    )
    return versao


@transaction.atomic
def cancelar_versao_preco(*, versao, usuario, motivo, ip=None):
    versao = VersaoPrecoProduto.objects.select_for_update().select_related("produto").get(pk=versao.pk)
    if versao.status == StatusVersaoPreco.CANCELADA:
        return versao
    versao.status = StatusVersaoPreco.CANCELADA
    versao.cancelado_por = usuario
    versao.cancelado_em = timezone.now()
    versao.motivo_cancelamento = motivo
    versao.save(update_fields=["status", "cancelado_por", "cancelado_em", "motivo_cancelamento"])
    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="produtos",
        acao="CANCELAR_PRECO_AGENDADO",
        descricao=f"Preço v{versao.versao} de {versao.produto} cancelado. Motivo={motivo}",
        objeto_tipo="VersaoPrecoProduto",
        objeto_id=str(versao.pk),
        ip=ip,
    )
    return versao