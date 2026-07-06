from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils.dateparse import parse_datetime
from django.utils import timezone

from .models import EventoEntradaSincronizacao, StatusEventoEntrada


class ManipuladorEventoNaoEncontrado(Exception):
    pass


class ConflitoSincronizacao(Exception):
    pass


def _ping(_evento):
    return None


def _valor_texto(dados, chave, padrao=""):
    valor = dados.get(chave, padrao)
    return str(valor).strip() if valor is not None else padrao


def _valor_decimal(dados, chave, padrao="0"):
    try:
        return Decimal(str(dados.get(chave, padrao)).replace(",", "."))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"Valor invalido para {chave}.") from exc


def _valor_booleano(dados, chave, padrao=False):
    valor = dados.get(chave, padrao)
    if isinstance(valor, bool):
        return valor
    return str(valor).strip().lower() in {"1", "true", "sim", "s", "on"}


def _nome_relacionado(valor):
    if isinstance(valor, dict):
        return str(valor.get("nome", "")).strip()
    return str(valor or "").strip()


def _dados_evento(evento):
    payload = evento.payload.get("payload", evento.payload)
    if not isinstance(payload, dict):
        raise ValueError("Payload de evento deve ser um objeto JSON.")
    return payload


def _evento_remoto_em(evento):
    bruto = evento.payload.get("criado_em") or evento.payload.get("atualizado_em")
    if not bruto:
        return None
    data = parse_datetime(str(bruto))
    if data and timezone.is_naive(data):
        data = timezone.make_aware(data)
    return data


def _produto_salvar(evento):
    from apps.produtos.models import Categoria, Marca, Produto, UnidadeMedida

    dados = _dados_evento(evento)
    codigo_barras = _valor_texto(dados, "codigo_barras")
    nome = _valor_texto(dados, "nome")
    categoria_nome = _nome_relacionado(dados.get("categoria"))
    if not codigo_barras or not nome or not categoria_nome:
        raise ValueError("codigo_barras, nome e categoria sao obrigatorios para sincronizar produto.")

    categoria, _ = Categoria.all_objects.get_or_create(nome=categoria_nome, defaults={"is_active": True})
    marca = None
    marca_nome = _nome_relacionado(dados.get("marca"))
    if marca_nome:
        marca, _ = Marca.all_objects.get_or_create(nome=marca_nome, defaults={"is_active": True})

    produto = Produto.all_objects.filter(codigo_barras=codigo_barras).first()
    remoto_em = _evento_remoto_em(evento)
    if produto and remoto_em and produto.updated_at and produto.updated_at > remoto_em:
        raise ConflitoSincronizacao("Produto local foi alterado depois do evento remoto.")

    valores = {
        "codigo_interno": _valor_texto(dados, "codigo_interno"),
        "nome": nome,
        "descricao": _valor_texto(dados, "descricao"),
        "categoria": categoria,
        "marca": marca,
        "unidade": _valor_texto(dados, "unidade", UnidadeMedida.UNIDADE)[:3] or UnidadeMedida.UNIDADE,
        "produto_pesavel": _valor_booleano(dados, "produto_pesavel"),
        "preco_custo": _valor_decimal(dados, "preco_custo"),
        "preco_venda": _valor_decimal(dados, "preco_venda"),
        "estoque_minimo": _valor_decimal(dados, "estoque_minimo"),
        "vendido_no_pdv": _valor_booleano(dados, "vendido_no_pdv", True),
        "vendido_no_marketplace": _valor_booleano(dados, "vendido_no_marketplace"),
        "ncm": _valor_texto(dados, "ncm"),
        "cest": _valor_texto(dados, "cest"),
        "origem_mercadoria": _valor_texto(dados, "origem_mercadoria"),
        "cst_icms": _valor_texto(dados, "cst_icms"),
        "csosn": _valor_texto(dados, "csosn"),
        "aliquota_icms": _valor_decimal(dados, "aliquota_icms", "0"),
        "is_active": _valor_booleano(dados, "is_active", True),
    }
    if produto:
        for campo, valor in valores.items():
            setattr(produto, campo, valor)
        produto.save()
    else:
        Produto.all_objects.create(codigo_barras=codigo_barras, **valores)


def _estoque_saldo_atualizar(evento):
    from apps.estoque.models import Estoque, MovimentacaoEstoque, TipoMovimentacaoEstoque
    from apps.produtos.models import Produto

    dados = _dados_evento(evento)
    codigo_barras = _valor_texto(dados, "codigo_barras")
    filial_cnpj = _valor_texto(dados, "filial_cnpj")
    filial_nome = _valor_texto(dados, "filial_nome")
    if not codigo_barras or not (filial_cnpj or filial_nome):
        raise ValueError("codigo_barras e filial_cnpj ou filial_nome sao obrigatorios para sincronizar estoque.")

    produto = Produto.all_objects.filter(codigo_barras=codigo_barras).first()
    if not produto:
        raise ConflitoSincronizacao("Produto do saldo de estoque nao encontrado na loja.")

    filiais = evento.empresa.filiais.all()
    filial = filiais.filter(cnpj=filial_cnpj).first() if filial_cnpj else None
    if not filial and filial_nome:
        filial = filiais.filter(nome=filial_nome).first()
    if not filial:
        raise ConflitoSincronizacao("Filial do saldo de estoque nao encontrada para a empresa.")

    estoque, _ = Estoque.objects.get_or_create(produto=produto, filial=filial)
    remoto_em = _evento_remoto_em(evento)
    if remoto_em and estoque.atualizado_em and estoque.atualizado_em > remoto_em:
        raise ConflitoSincronizacao("Estoque local foi alterado depois do evento remoto.")

    quantidade_atual = _valor_decimal(dados, "quantidade_atual")
    quantidade_reservada = _valor_decimal(dados, "quantidade_reservada", "0")
    anterior = estoque.quantidade_atual
    diferenca = quantidade_atual - anterior
    estoque.quantidade_atual = quantidade_atual
    estoque.quantidade_reservada = quantidade_reservada
    estoque.full_clean()
    estoque.save()

    if diferenca:
        MovimentacaoEstoque.objects.create(
            produto=produto,
            filial=filial,
            tipo=TipoMovimentacaoEstoque.AJUSTE,
            quantidade=diferenca,
            motivo="Sincronizacao de saldo de estoque",
            referencia=f"sync:{evento.identificador}",
        )


def _filial_do_evento(evento, dados):
    filial_cnpj = _valor_texto(dados, "filial_cnpj") or _valor_texto(evento.payload, "filial_cnpj")
    filial_nome = _valor_texto(dados, "filial_nome")
    filiais = evento.empresa.filiais.all()
    filial = filiais.filter(cnpj=filial_cnpj).first() if filial_cnpj else None
    if not filial and filial_nome:
        filial = filiais.filter(nome=filial_nome).first()
    return filial


def _venda_finalizada(evento):
    from .models import VendaSincronizada

    dados = _dados_evento(evento)
    venda_externa_id = _valor_texto(dados, "venda_id") or _valor_texto(dados, "id")
    if not venda_externa_id:
        raise ValueError("venda_id e obrigatorio para sincronizar venda finalizada.")
    total_liquido = _valor_decimal(dados, "total_liquido")
    existente = VendaSincronizada.objects.filter(empresa=evento.empresa, venda_externa_id=venda_externa_id).first()
    if existente and existente.total_liquido != total_liquido:
        raise ConflitoSincronizacao("Venda externa ja existe com total diferente.")

    filial = _filial_do_evento(evento, dados)
    if not filial:
        raise ConflitoSincronizacao("Filial da venda sincronizada nao encontrada para a empresa.")
    realizada_em = parse_datetime(_valor_texto(dados, "realizada_em")) if _valor_texto(dados, "realizada_em") else None
    if realizada_em and timezone.is_naive(realizada_em):
        realizada_em = timezone.make_aware(realizada_em)
    itens = dados.get("itens", [])
    pagamentos = dados.get("pagamentos", [])
    if not isinstance(itens, list) or not isinstance(pagamentos, list):
        raise ValueError("Itens e pagamentos da venda devem ser listas.")

    valores = {
        "filial": filial,
        "evento": evento,
        "caixa_externo": _valor_texto(dados, "caixa"),
        "operador": _valor_texto(dados, "operador"),
        "cliente": _valor_texto(dados, "cliente", "Cliente avulso"),
        "total_bruto": _valor_decimal(dados, "total_bruto"),
        "desconto": _valor_decimal(dados, "desconto"),
        "total_liquido": total_liquido,
        "itens": itens,
        "pagamentos": pagamentos,
        "realizada_em": realizada_em,
    }
    if existente:
        for campo, valor in valores.items():
            setattr(existente, campo, valor)
        existente.save()
    else:
        VendaSincronizada.objects.create(empresa=evento.empresa, venda_externa_id=venda_externa_id, **valores)


def _documento_fiscal_salvar(evento):
    from .models import DocumentoFiscalSincronizado

    dados = _dados_evento(evento)
    documento_externo_id = _valor_texto(dados, "documento_id") or _valor_texto(dados, "id")
    if not documento_externo_id:
        raise ValueError("documento_id e obrigatorio para sincronizar documento fiscal.")

    valor_total = _valor_decimal(dados, "valor_total")
    chave_acesso = _valor_texto(dados, "chave_acesso")
    existente = DocumentoFiscalSincronizado.objects.filter(
        empresa=evento.empresa,
        documento_externo_id=documento_externo_id,
    ).first()
    if existente:
        if existente.valor_total != valor_total:
            raise ConflitoSincronizacao("Documento fiscal externo ja existe com valor diferente.")
        if existente.chave_acesso and chave_acesso and existente.chave_acesso != chave_acesso:
            raise ConflitoSincronizacao("Documento fiscal externo ja existe com chave de acesso diferente.")

    filial = _filial_do_evento(evento, dados)
    if not filial:
        raise ConflitoSincronizacao("Filial do documento fiscal sincronizado nao encontrada para a empresa.")
    emitido_em = parse_datetime(_valor_texto(dados, "emitido_em")) if _valor_texto(dados, "emitido_em") else None
    if emitido_em and timezone.is_naive(emitido_em):
        emitido_em = timezone.make_aware(emitido_em)

    valores = {
        "filial": filial,
        "evento": evento,
        "venda_externa_id": _valor_texto(dados, "venda_id"),
        "tipo_documento": _valor_texto(dados, "tipo_documento", "NFCE"),
        "ambiente": _valor_texto(dados, "ambiente"),
        "serie": _valor_texto(dados, "serie"),
        "numero": _valor_texto(dados, "numero"),
        "chave_acesso": chave_acesso,
        "protocolo": _valor_texto(dados, "protocolo"),
        "status": _valor_texto(dados, "status", "EMITIDO"),
        "valor_total": valor_total,
        "emitido_em": emitido_em,
        "payload": dados,
    }
    if existente:
        for campo, valor in valores.items():
            setattr(existente, campo, valor)
        existente.save()
    else:
        DocumentoFiscalSincronizado.objects.create(
            empresa=evento.empresa,
            documento_externo_id=documento_externo_id,
            **valores,
        )


MANIPULADORES = {
    "sistema.ping": _ping,
    "produto.criado": _produto_salvar,
    "produto.atualizado": _produto_salvar,
    "estoque.saldo_atualizado": _estoque_saldo_atualizar,
    "venda.finalizada": _venda_finalizada,
    "fiscal.documento_emitido": _documento_fiscal_salvar,
    "fiscal.documento_cancelado": _documento_fiscal_salvar,
}


def processar_evento_entrada(evento):
    manipulador = MANIPULADORES.get(evento.tipo)
    if not manipulador:
        raise ManipuladorEventoNaoEncontrado(f"Evento sem manipulador de dominio: {evento.tipo}")
    manipulador(evento)


def processar_entrada_sincronizacao(*, limite=50):
    candidatos = list(
        EventoEntradaSincronizacao.objects.filter(status=StatusEventoEntrada.RECEBIDO)
        .order_by("recebido_em")
        .values_list("pk", flat=True)[:limite]
    )
    resultado = {"processados": 0, "erros": 0}
    for pk in candidatos:
        with transaction.atomic():
            evento = EventoEntradaSincronizacao.objects.select_for_update().get(pk=pk)
            if evento.status != StatusEventoEntrada.RECEBIDO:
                continue
            try:
                processar_evento_entrada(evento)
            except ConflitoSincronizacao as exc:
                evento.status = StatusEventoEntrada.CONFLITO
                evento.ultimo_erro = str(exc)[:2000]
                evento.save(update_fields=["status", "ultimo_erro", "atualizado_em"])
                resultado["erros"] += 1
            except Exception as exc:
                evento.status = StatusEventoEntrada.ERRO
                evento.ultimo_erro = str(exc)[:2000]
                evento.save(update_fields=["status", "ultimo_erro", "atualizado_em"])
                resultado["erros"] += 1
            else:
                evento.status = StatusEventoEntrada.PROCESSADO
                evento.ultimo_erro = ""
                evento.processado_em = timezone.now()
                evento.save(update_fields=["status", "ultimo_erro", "processado_em", "atualizado_em"])
                resultado["processados"] += 1
    return resultado
