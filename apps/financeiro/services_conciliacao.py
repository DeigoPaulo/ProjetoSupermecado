import csv
import hashlib
import io
import unicodedata
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import transaction
from django.db.models import Q

from apps.auditoria.models import LogAuditoria

from .extrato_adapters import carregar_adaptador_extrato, validar_arquivo_adaptador

from .models import (
    ImportacaoExtratoFinanceiro,
    ItemExtratoFinanceiro,
    LancamentoFinanceiro,
    StatusItemExtratoFinanceiro,
    TipoLancamentoFinanceiro,
)
from .services import conciliar_lancamento
from .services_recebiveis import candidatos_recebivel_item, conciliar_recebivel_com_item


CABECALHOS = {
    "data": {"data", "date", "data_movimento", "data_lancamento"},
    "tipo": {"tipo", "natureza", "movimento", "credito_debito"},
    "valor": {"valor", "amount", "valor_movimento"},
    "descricao": {"descricao", "historico", "description", "memo"},
    "referencia": {"referencia", "id", "documento", "nsu", "identificador", "reference"},
}


def _normalizar(texto):
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    return "_".join("".join(ch for ch in texto if not unicodedata.combining(ch)).strip().lower().split())


def _mapear_cabecalhos(fieldnames):
    normalizados = {_normalizar(nome): nome for nome in (fieldnames or [])}
    mapa = {}
    for destino, aliases in CABECALHOS.items():
        original = next((normalizados[alias] for alias in aliases if alias in normalizados), None)
        if not original:
            raise ValidationError(f"Coluna obrigatória ausente: {destino}.")
        mapa[destino] = original
    return mapa


def _parse_data(valor, linha):
    valor = str(valor or "").strip()
    for formato in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(valor, formato).date()
        except ValueError:
            continue
    raise ValidationError(f"Linha {linha}: data inválida ({valor or 'vazia'}).")


def _parse_valor(valor, linha):
    texto = str(valor or "").strip().replace("R$", "").replace(" ", "")
    if "," in texto and "." in texto:
        texto = texto.replace(".", "").replace(",", ".")
    elif "," in texto:
        texto = texto.replace(",", ".")
    try:
        numero = Decimal(texto).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        raise ValidationError(f"Linha {linha}: valor inválido ({valor or 'vazio'}).")
    if numero <= 0:
        raise ValidationError(f"Linha {linha}: o valor deve ser maior que zero.")
    return numero


def _parse_tipo(valor, linha):
    texto = _normalizar(valor)
    if texto in {"entrada", "credito", "credit", "c", "+"}:
        return TipoLancamentoFinanceiro.ENTRADA
    if texto in {"saida", "debito", "debit", "d", "-"}:
        return TipoLancamentoFinanceiro.SAIDA
    raise ValidationError(f"Linha {linha}: tipo deve ser entrada/crédito ou saída/débito.")


def _decodificar(conteudo):
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return conteudo.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValidationError("Não foi possível identificar a codificação do CSV.")


def ler_extrato_csv(conteudo):
    texto = _decodificar(conteudo)
    amostra = texto[:4096]
    try:
        dialect = csv.Sniffer().sniff(amostra, delimiters=";,\t")
        delimitador = dialect.delimiter
    except csv.Error:
        delimitador = ";"
    reader = csv.DictReader(io.StringIO(texto), delimiter=delimitador)
    mapa = _mapear_cabecalhos(reader.fieldnames)
    itens = []
    referencias = set()
    for numero_linha, row in enumerate(reader, start=2):
        if not any(str(valor or "").strip() for valor in row.values()):
            continue
        referencia = str(row.get(mapa["referencia"], "") or "").strip()
        if not referencia:
            raise ValidationError(f"Linha {numero_linha}: informe uma referência externa única.")
        if referencia in referencias:
            raise ValidationError(f"Linha {numero_linha}: referência duplicada no arquivo ({referencia}).")
        referencias.add(referencia)
        descricao = str(row.get(mapa["descricao"], "") or "").strip()
        if not descricao:
            raise ValidationError(f"Linha {numero_linha}: informe a descrição.")
        itens.append({
            "numero_linha": numero_linha,
            "data": _parse_data(row.get(mapa["data"]), numero_linha),
            "tipo": _parse_tipo(row.get(mapa["tipo"]), numero_linha),
            "valor": _parse_valor(row.get(mapa["valor"]), numero_linha),
            "descricao": descricao[:255],
            "referencia_externa": referencia[:120],
        })
    if not itens:
        raise ValidationError("O arquivo não possui movimentações para importar.")
    return itens


def _candidatos(item, conta):
    inicio = item["data"] - timedelta(days=3)
    fim = item["data"] + timedelta(days=3)
    candidatos = LancamentoFinanceiro.objects.select_for_update().filter(
        conta=conta,
        tipo=item["tipo"],
        valor=item["valor"],
        data__range=(inicio, fim),
        conciliacao_bancaria__isnull=True,
        item_extrato__isnull=True,
    )
    referencia = item["referencia_externa"]
    por_referencia = candidatos.filter(
        Q(pagamento_venda__nsu=referencia)
        | Q(pagamento_venda__transacao_externa_id=referencia)
        | Q(pagamento_venda__codigo_autorizacao=referencia)
    )
    if por_referencia.exists():
        return por_referencia
    return candidatos


def _normalizar_linhas_adaptador(linhas):
    if not isinstance(linhas, (list, tuple)):
        raise ValidationError("O adaptador de extrato deve retornar uma lista de movimentações.")
    normalizadas = []
    referencias = set()
    for posicao, linha in enumerate(linhas, start=1):
        if not isinstance(linha, dict):
            raise ValidationError(f"Movimentação {posicao}: o adaptador retornou um registro inválido.")
        numero_linha = linha.get("numero_linha") or posicao
        try:
            numero_linha = int(numero_linha)
        except (TypeError, ValueError):
            raise ValidationError(f"Movimentação {posicao}: número da linha inválido.")
        referencia = str(
            linha.get("referencia_externa") or linha.get("referencia") or ""
        ).strip()
        if not referencia:
            raise ValidationError(f"Movimentação {posicao}: informe a referência externa.")
        if referencia in referencias:
            raise ValidationError(f"Movimentação {posicao}: referência duplicada no arquivo ({referencia}).")
        referencias.add(referencia)
        descricao = str(linha.get("descricao") or "").strip()
        if not descricao:
            raise ValidationError(f"Movimentação {posicao}: informe a descrição.")
        normalizadas.append(
            {
                "numero_linha": numero_linha,
                "data": _parse_data(linha.get("data"), numero_linha),
                "tipo": _parse_tipo(linha.get("tipo"), numero_linha),
                "valor": _parse_valor(linha.get("valor"), numero_linha),
                "descricao": descricao[:255],
                "referencia_externa": referencia[:120],
            }
        )
    if not normalizadas:
        raise ValidationError("O arquivo não possui movimentações para importar.")
    return normalizadas


@transaction.atomic
def importar_extrato(
    *,
    conta,
    arquivo_nome,
    conteudo,
    usuario,
    adaptador_codigo="CSV_GENERICO",
    ip=None,
):
    try:
        info = validar_arquivo_adaptador(codigo=adaptador_codigo, arquivo_nome=arquivo_nome)
        adaptador = carregar_adaptador_extrato(info.codigo)
    except ImproperlyConfigured as exc:
        raise ValidationError(str(exc)) from exc

    arquivo_sha256 = hashlib.sha256(conteudo).hexdigest()
    existente = ImportacaoExtratoFinanceiro.objects.filter(
        conta=conta,
        arquivo_sha256=arquivo_sha256,
    ).first()
    if existente:
        return existente, False

    linhas = _normalizar_linhas_adaptador(
        adaptador.ler(conteudo=conteudo, arquivo_nome=arquivo_nome)
    )
    importacao = ImportacaoExtratoFinanceiro.objects.create(
        conta=conta,
        arquivo_nome=arquivo_nome[:255],
        arquivo_sha256=arquivo_sha256,
        adaptador_codigo=info.codigo,
        adaptador_nome=info.nome,
        adaptador_contrato=info.contrato,
        total_linhas=len(linhas),
        usuario=usuario,
    )
    contadores = {"conciliadas_automaticamente": 0, "pendentes": 0, "ambiguas": 0, "duplicadas": 0}
    for linha in linhas:
        if ItemExtratoFinanceiro.objects.filter(
            conta=conta,
            referencia_externa=linha["referencia_externa"],
            tipo=linha["tipo"],
            data=linha["data"],
        ).exists():
            contadores["duplicadas"] += 1
            continue
        item = ItemExtratoFinanceiro.objects.create(
            importacao=importacao,
            conta=conta,
            status=StatusItemExtratoFinanceiro.PENDENTE,
            observacao="Nenhum lançamento ou recebível compatível encontrado.",
            **linha,
        )
        recebiveis = candidatos_recebivel_item(item, somente_referencia=True)
        if len(recebiveis) == 1:
            conciliar_recebivel_com_item(
                item=item,
                recebivel=recebiveis[0],
                usuario=usuario,
                automatico=True,
                ip=ip,
            )
            contadores["conciliadas_automaticamente"] += 1
            continue
        if len(recebiveis) > 1:
            item.status = StatusItemExtratoFinanceiro.AMBIGUO
            item.observacao = "Mais de um recebível possui a referência externa; revisão manual obrigatória."
            item.save(update_fields=["status", "observacao"])
            contadores["ambiguas"] += 1
            continue

        candidatos = list(_candidatos(linha, conta)[:2])
        if len(candidatos) == 1:
            lancamento = candidatos[0]
            observacao = "Conciliação automática por conta, natureza, valor e janela de data."
            item.lancamento = lancamento
            item.status = StatusItemExtratoFinanceiro.CONCILIADO
            item.observacao = observacao
            item.save(update_fields=["lancamento", "status", "observacao"])
            conciliar_lancamento(
                lancamento=lancamento,
                data_conciliacao=linha["data"],
                referencia_externa=linha["referencia_externa"],
                observacao=f"Importado de {arquivo_nome}. {observacao}",
                usuario=usuario,
                ip=ip,
            )
            contadores["conciliadas_automaticamente"] += 1
        elif len(candidatos) > 1:
            item.status = StatusItemExtratoFinanceiro.AMBIGUO
            item.observacao = "Mais de um lançamento compatível; revisão manual obrigatória."
            item.save(update_fields=["status", "observacao"])
            contadores["ambiguas"] += 1
        else:
            contadores["pendentes"] += 1

    ImportacaoExtratoFinanceiro.objects.filter(pk=importacao.pk).update(**contadores)
    importacao.refresh_from_db()
    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="financeiro",
        acao="IMPORTA_EXTRATO_FINANCEIRO",
        descricao=(
            f"Extrato {arquivo_nome} importado por {info.codigo} na conta #{conta.pk}: "
            f"{importacao.conciliadas_automaticamente} conciliadas, {importacao.pendentes} pendentes, "
            f"{importacao.ambiguas} ambíguas e {importacao.duplicadas} duplicadas."
        ),
        objeto_tipo="ImportacaoExtratoFinanceiro",
        objeto_id=str(importacao.pk),
        ip=ip,
    )
    return importacao, True


def importar_extrato_csv(*, conta, arquivo_nome, conteudo, usuario, ip=None):
    return importar_extrato(
        conta=conta,
        arquivo_nome=arquivo_nome,
        conteudo=conteudo,
        usuario=usuario,
        adaptador_codigo="CSV_GENERICO",
        ip=ip,
    )


@transaction.atomic
def conciliar_item_extrato(*, item, lancamento, usuario, ip=None):
    item = ItemExtratoFinanceiro.objects.select_for_update().select_related("conta").get(pk=item.pk)
    lancamento = LancamentoFinanceiro.objects.select_for_update().get(pk=lancamento.pk)
    if item.status == StatusItemExtratoFinanceiro.CONCILIADO or item.lancamento_id:
        raise ValidationError("Este item de extrato já foi conciliado.")
    if item.movimentos_recebiveis.exists():
        raise ValidationError("Este item está parcialmente alocado a recebíveis eletrônicos.")
    if lancamento.conta_id != item.conta_id:
        raise ValidationError("O lançamento pertence a outra conta de movimento.")
    if lancamento.tipo != item.tipo or lancamento.valor != item.valor:
        raise ValidationError("Natureza e valor do lançamento devem ser idênticos aos do extrato.")
    conciliar_lancamento(
        lancamento=lancamento,
        data_conciliacao=item.data,
        referencia_externa=item.referencia_externa,
        observacao=f"Conciliação manual do extrato {item.importacao.arquivo_nome}.",
        usuario=usuario,
        ip=ip,
    )
    ItemExtratoFinanceiro.objects.filter(pk=item.pk).update(
        lancamento=lancamento,
        status=StatusItemExtratoFinanceiro.CONCILIADO,
        observacao="Conciliação manual confirmada.",
    )
    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="financeiro",
        acao="CONCILIA_ITEM_EXTRATO",
        descricao=f"Item de extrato #{item.pk} vinculado ao lançamento #{lancamento.pk}.",
        objeto_tipo="ItemExtratoFinanceiro",
        objeto_id=str(item.pk),
        ip=ip,
    )
    item.refresh_from_db()
    return item