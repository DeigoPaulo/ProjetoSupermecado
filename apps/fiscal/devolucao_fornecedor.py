"""Pré-diagnóstico e rascunho documental da devolução ao fornecedor.

O fluxo é deliberadamente não emissivo: persiste somente a preparação operacional,
não escolhe tributação, não cria DocumentoFiscal e não movimenta estoque. Ele
separa evidências da entrada das decisões dependentes do contador e do caso real.
"""

import hashlib
import json
from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import transaction
from django.db.models import Max, Sum
from django.utils import timezone

from apps.clientes.escopo import empresa_id_do_usuario
from apps.accounts.permissions import REVISAO_FISCAL, has_role
from apps.compras.models import EntradaCompra, ItemEntradaCompra, StatusEntradaCompra

from apps.auditoria.models import LogAuditoria

from .pacote_contabil import analisar_xml_nfe
from .cfop import catalogo_cfop_vigente, validar_cfop
from .models import (
    DecisaoRevisaoDevolucaoFornecedor,
    ItemMemoriaCalculoDevolucaoFornecedor,
    ItemParametrizacaoFiscalDevolucaoFornecedor,
    ItemRascunhoDevolucaoFornecedor,
    MemoriaCalculoDevolucaoFornecedor,
    ParecerTributarioDevolucaoFornecedor,
    ParametrizacaoFiscalDevolucaoFornecedor,
    RascunhoDevolucaoFornecedor,
    RevisaoDevolucaoFornecedor,
    StatusRascunhoDevolucaoFornecedor,
    TipoCodigoICMSDevolucaoFornecedor,
)


CONTRATO_PREPARACAO_DEVOLUCAO_FORNECEDOR = "supplier_return_fiscal_preparation_v1"
CONTRATO_RASCUNHO_DEVOLUCAO_FORNECEDOR = "supplier_return_draft_v1"
CONTRATO_PARECER_TRIBUTARIO_DEVOLUCAO_FORNECEDOR = "supplier_return_tax_opinion_v1"
CONTRATO_PARAMETROS_ITEM_DEVOLUCAO_FORNECEDOR = "supplier_return_item_tax_parameters_v1"
CONTRATO_MEMORIA_CALCULO_DEVOLUCAO_FORNECEDOR = "supplier_return_item_tax_calculation_memory_v1"
STATUS_RASCUNHO_ATIVO = (
    StatusRascunhoDevolucaoFornecedor.RASCUNHO,
    StatusRascunhoDevolucaoFornecedor.AGUARDANDO_REVISAO,
    StatusRascunhoDevolucaoFornecedor.APROVADO,
)
STATUS_RASCUNHO_CANCELAVEL = (
    StatusRascunhoDevolucaoFornecedor.RASCUNHO,
    StatusRascunhoDevolucaoFornecedor.AGUARDANDO_REVISAO,
)
MILESIMOS = Decimal("0.001")
CENTAVOS = Decimal("0.01")
QUATRO_DECIMAIS = Decimal("0.0001")
TRIBUTOS_MEMORIA_CALCULO = (
    ("icms", "ICMS"),
    ("icms_st", "ICMS-ST"),
    ("fcp", "FCP"),
    ("ipi", "IPI"),
    ("pis", "PIS"),
    ("cofins", "COFINS"),
    ("ibs", "IBS"),
    ("cbs", "CBS"),
)


def _digitos(valor):
    return "".join(caractere for caractere in str(valor or "") if caractere.isdigit())


def _documento_dfe_da_entrada(entrada):
    try:
        return entrada.documento_dfe_recebido
    except ObjectDoesNotExist:
        return None


def _identificador(valor):
    return str(valor or "").strip().upper()


def _identificadores_produto(produto):
    return {
        valor
        for valor in (
            _identificador(produto.codigo_interno),
            _identificador(produto.codigo_barras),
        )
        if valor
    }


def _identificadores_item_xml(item_xml):
    return {
        valor
        for valor in (
            _identificador(item_xml.get("codigo_produto")),
            _identificador(item_xml.get("ean")),
            _identificador(item_xml.get("ean_tributavel")),
        )
        if valor and valor not in {"SEM GTIN", "SEM-GTIN"}
    }


def _resolver_item_xml(item_entrada, numero_solicitado, itens_xml):
    por_numero = {item["numero_item"]: item for item in itens_xml if item["numero_item"]}
    numero = str(numero_solicitado or item_entrada.numero_item_xml or "").strip()
    if numero:
        item_xml = por_numero.get(numero)
        if not item_xml:
            raise ValidationError(
                f"O nItem {numero} de {item_entrada.produto} não existe no XML original."
            )
        # O nItem gravado na importação é a evidência primária. Mapeamentos
        # posteriores só são aceitos se os identificadores ainda coincidirem.
        if item_entrada.numero_item_xml == numero:
            return item_xml
        if _identificadores_produto(item_entrada.produto) & _identificadores_item_xml(item_xml):
            return item_xml
        raise ValidationError(
            f"O nItem {numero} não corresponde com segurança ao produto {item_entrada.produto}."
        )

    identificadores = _identificadores_produto(item_entrada.produto)
    candidatos = [
        item_xml
        for item_xml in itens_xml
        if identificadores & _identificadores_item_xml(item_xml)
    ]
    if len(candidatos) != 1:
        raise ValidationError(
            f"Não foi possível mapear {item_entrada.produto} a um único nItem do XML original."
        )
    return candidatos[0]


def _validar_totais_por_item_xml(itens_rascunho, itens_xml):
    por_numero = {item["numero_item"]: item for item in itens_xml}
    totais = {}
    for item in itens_rascunho:
        totais[item.numero_item_xml] = totais.get(
            item.numero_item_xml, Decimal("0.000")
        ) + item.quantidade
    for numero, selecionada in totais.items():
        try:
            original = Decimal(por_numero[numero]["quantidade"])
        except (KeyError, InvalidOperation, TypeError) as exc:
            raise ValidationError(f"Quantidade original inválida no nItem {numero}.") from exc
        if not original.is_finite() or original <= 0 or selecionada > original:
            raise ValidationError(
                f"A soma selecionada para o nItem {numero} excede ou invalida a quantidade original."
            )


def preparar_devolucao_fornecedor(entrada):
    """Expõe fatos e bloqueios sem gerar ou transmitir uma NF-e de devolução."""
    chave_entrada = _digitos(entrada.chave_acesso_xml)
    cnpj_fornecedor = _digitos(entrada.fornecedor.cnpj)
    cnpj_filial = _digitos(entrada.filial.cnpj or entrada.filial.empresa.cnpj)
    documento_dfe = _documento_dfe_da_entrada(entrada)
    xml_origem = documento_dfe.xml_conteudo if documento_dfe else ""
    analise = analisar_xml_nfe(xml_origem)

    verificacoes = [
        {
            "codigo": "entrada_finalizada",
            "rotulo": "Entrada de compra finalizada",
            "ok": entrada.status == StatusEntradaCompra.FINALIZADA,
            "detalhe": "A preparação fiscal só parte de mercadoria efetivamente recebida.",
        },
        {
            "codigo": "chave_original",
            "rotulo": "Chave da NF-e original válida",
            "ok": len(chave_entrada) == 44,
            "detalhe": chave_entrada or "A entrada não possui chave de 44 dígitos.",
        },
        {
            "codigo": "xml_original",
            "rotulo": "XML autorizado original preservado",
            "ok": bool(xml_origem) and not analise["erro"],
            "detalhe": (
                "XML integral disponível no DF-e vinculado."
                if xml_origem and not analise["erro"]
                else "Importe ou vincule o DF-e com o XML integral antes de apurar a devolução."
            ),
        },
        {
            "codigo": "modelo_original",
            "rotulo": "Documento original é NF-e modelo 55",
            "ok": analise["modelo"] == "55",
            "detalhe": f"Modelo encontrado: {analise['modelo'] or 'não identificado'}.",
        },
        {
            "codigo": "vinculo_xml",
            "rotulo": "XML e entrada representam a mesma NF-e",
            "ok": bool(chave_entrada) and analise["chave_acesso"] == chave_entrada,
            "detalhe": "A chave do XML integral deve ser idêntica à chave registrada na compra.",
        },
        {
            "codigo": "fornecedor_identificado",
            "rotulo": "Fornecedor corresponde ao emitente original",
            "ok": len(cnpj_fornecedor) == 14 and analise["emitente_cnpj"] == cnpj_fornecedor,
            "detalhe": "O CNPJ cadastrado deve coincidir com o emitente do XML original.",
        },
        {
            "codigo": "filial_identificada",
            "rotulo": "Filial corresponde ao destinatário original",
            "ok": len(cnpj_filial) == 14 and analise["destinatario_cnpj"] == cnpj_filial,
            "detalhe": "O CNPJ da filial deve coincidir com o destinatário do XML original.",
        },
        {
            "codigo": "itens_fiscais",
            "rotulo": "Itens fiscais originais disponíveis",
            "ok": bool(analise["itens"]),
            "detalhe": f"{len(analise['itens'])} item(ns) localizado(s) no XML integral.",
        },
    ]
    bloqueios_documentais = [item["rotulo"] for item in verificacoes if not item["ok"]]
    decisoes_pendentes = [
        "Selecionar os itens e as quantidades efetivamente devolvidos, sem exceder a entrada.",
        "Definir a natureza da operação e o CFOP com o contador para o caso concreto.",
        "Revisar por item ICMS, ICMS-ST, FCP, IPI, PIS, COFINS, cBenef e demais valores do XML original.",
        "Definir frete, transportador, volumes e motivo operacional da devolução, quando aplicáveis.",
        "Obter revisão fiscal antes de gerar XML, reservar numeração ou escolher Focus/SEFAZ direta.",
    ]

    return {
        "contrato": CONTRATO_PREPARACAO_DEVOLUCAO_FORNECEDOR,
        "estado": "BASE_DOCUMENTAL_DISPONIVEL" if not bloqueios_documentais else "INCOMPLETA",
        "permite_emissao": False,
        "permite_transmissao": False,
        "documento_planejado": {
            "modelo": "55",
            "finalidade": "4",
            "chave_referenciada": chave_entrada,
            "cfop": None,
            "tributacao": None,
        },
        "verificacoes": verificacoes,
        "bloqueios_documentais": bloqueios_documentais,
        "decisoes_pendentes": decisoes_pendentes,
        "itens_xml_original": analise["itens"],
    }


def _quantidade(valor, item_id):
    if valor in (None, ""):
        return Decimal("0.000")
    try:
        quantidade = Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError(f"Quantidade inválida para o item {item_id}.") from exc
    if not quantidade.is_finite():
        raise ValidationError(f"Quantidade inválida para o item {item_id}.")
    if quantidade < 0:
        raise ValidationError(f"A quantidade do item {item_id} não pode ser negativa.")
    if quantidade >= Decimal("1000000000"):
        raise ValidationError(f"A quantidade do item {item_id} excede o limite suportado.")
    try:
        quantidade_normalizada = quantidade.quantize(MILESIMOS)
    except InvalidOperation as exc:
        raise ValidationError(f"Quantidade inválida para o item {item_id}.") from exc
    if quantidade_normalizada != quantidade:
        raise ValidationError(f"A quantidade do item {item_id} deve ter no máximo três casas decimais.")
    return quantidade_normalizada


def rascunho_ativo_da_entrada(entrada):
    return (
        RascunhoDevolucaoFornecedor.objects.filter(
            entrada_compra=entrada,
            status__in=STATUS_RASCUNHO_ATIVO,
        )
        .prefetch_related("itens__item_entrada__produto")
        .first()
    )


def salvar_rascunho_devolucao_fornecedor(
    entrada,
    *,
    selecoes,
    motivo_operacional,
    usuario,
    mapeamentos=None,
    ip=None,
):
    """Persiste somente itens e quantidades; nenhum efeito fiscal ou de estoque."""
    motivo = str(motivo_operacional or "").strip()
    if not motivo:
        raise ValidationError("Informe o motivo operacional da devolução.")
    if len(motivo) > 255:
        raise ValidationError("O motivo operacional deve ter no máximo 255 caracteres.")

    with transaction.atomic():
        entrada = (
            EntradaCompra.objects.select_for_update()
            .select_related("fornecedor", "filial__empresa")
            .get(pk=entrada.pk)
        )
        empresa_id = empresa_id_do_usuario(usuario)
        if empresa_id is not None and entrada.filial.empresa_id != empresa_id:
            raise ValidationError("Esta entrada não pertence à empresa do usuário.")

        diagnostico = preparar_devolucao_fornecedor(entrada)
        if diagnostico["bloqueios_documentais"]:
            raise ValidationError(
                "A preparação documental está incompleta: "
                + "; ".join(diagnostico["bloqueios_documentais"])
                + "."
            )

        itens_entrada = {
            item.pk: item
            for item in ItemEntradaCompra.objects.select_for_update()
            .select_related("produto")
            .filter(entrada=entrada)
        }
        quantidades = {}
        for item_id_bruto, valor in (selecoes or {}).items():
            try:
                item_id = int(item_id_bruto)
            except (TypeError, ValueError) as exc:
                raise ValidationError("A seleção contém um item inválido.") from exc
            if item_id not in itens_entrada:
                raise ValidationError(f"O item {item_id} não pertence a esta entrada.")
            quantidade = _quantidade(valor, item_id)
            if quantidade > 0:
                quantidades[item_id] = quantidade
        if not quantidades:
            raise ValidationError("Selecione ao menos um item com quantidade maior que zero.")

        itens_xml = diagnostico["itens_xml_original"]
        mapeamentos = mapeamentos or {}
        itens_xml_mapeados = {
            item_id: _resolver_item_xml(
                itens_entrada[item_id],
                mapeamentos.get(item_id, mapeamentos.get(str(item_id), "")),
                itens_xml,
            )
            for item_id in quantidades
        }

        rascunho = (
            RascunhoDevolucaoFornecedor.objects.select_for_update()
            .filter(entrada_compra=entrada, status__in=STATUS_RASCUNHO_ATIVO)
            .first()
        )
        if rascunho and rascunho.status == StatusRascunhoDevolucaoFornecedor.AGUARDANDO_REVISAO:
            raise ValidationError("O rascunho está aguardando revisão fiscal e não pode ser alterado.")

        reservadas_outros = {
            linha["item_entrada_id"]: linha["total"]
            for linha in ItemRascunhoDevolucaoFornecedor.objects.filter(
                item_entrada_id__in=itens_entrada,
                rascunho__status__in=STATUS_RASCUNHO_ATIVO,
            )
            .exclude(rascunho=rascunho)
            .values("item_entrada_id")
            .annotate(total=Sum("quantidade"))
        }
        for item_id, quantidade in quantidades.items():
            item = itens_entrada[item_id]
            disponivel = item.quantidade - reservadas_outros.get(item_id, Decimal("0.000"))
            if quantidade > disponivel:
                raise ValidationError(
                    f"Quantidade do item {item.produto} excede o saldo devolvível de {disponivel}."
                )

        criado = rascunho is None
        if criado:
            rascunho = RascunhoDevolucaoFornecedor.objects.create(
                entrada_compra=entrada,
                chave_referenciada=diagnostico["documento_planejado"]["chave_referenciada"],
                motivo_operacional=motivo,
                criado_por=usuario,
                atualizado_por=usuario,
            )
        else:
            rascunho.motivo_operacional = motivo
            rascunho.atualizado_por = usuario
            rascunho.save(update_fields=["motivo_operacional", "atualizado_por", "atualizado_em"])
            rascunho.itens.all().delete()

        ItemRascunhoDevolucaoFornecedor.objects.bulk_create(
            [
                ItemRascunhoDevolucaoFornecedor(
                    rascunho=rascunho,
                    item_entrada=itens_entrada[item_id],
                    quantidade=quantidade,
                    quantidade_recebida_snapshot=itens_entrada[item_id].quantidade,
                    numero_item_xml=itens_xml_mapeados[item_id]["numero_item"],
                    item_xml_snapshot=itens_xml_mapeados[item_id],
                )
                for item_id, quantidade in sorted(quantidades.items())
            ]
        )
        LogAuditoria.objects.create(
            usuario=usuario,
            modulo="fiscal",
            acao="RASCUNHO_DEVOLUCAO_FORNECEDOR_SALVO",
            descricao=(
                f"Rascunho {rascunho.pk} da entrada {entrada.pk} salvo com "
                f"{len(quantidades)} item(ns). Nenhum documento fiscal, numeração, "
                "estoque ou transmissão foi criado."
            ),
            objeto_tipo="RascunhoDevolucaoFornecedor",
            objeto_id=str(rascunho.pk),
            ip=ip,
        )
    return rascunho, criado


def submeter_rascunho_devolucao_para_revisao(entrada, *, usuario, ip=None):
    """Congela origem e seleção para revisão, ainda sem emitir ou calcular tributos."""
    with transaction.atomic():
        entrada = (
            EntradaCompra.objects.select_for_update()
            .select_related("fornecedor", "filial__empresa")
            .get(pk=entrada.pk)
        )
        empresa_id = empresa_id_do_usuario(usuario)
        if empresa_id is not None and entrada.filial.empresa_id != empresa_id:
            raise ValidationError("Esta entrada não pertence à empresa do usuário.")
        rascunho = (
            RascunhoDevolucaoFornecedor.objects.select_for_update()
            .filter(
                entrada_compra=entrada,
                status=StatusRascunhoDevolucaoFornecedor.RASCUNHO,
            )
            .first()
        )
        if not rascunho:
            raise ValidationError("Não existe rascunho editável para submeter à revisão fiscal.")

        diagnostico = preparar_devolucao_fornecedor(entrada)
        if diagnostico["bloqueios_documentais"]:
            raise ValidationError("A preparação documental deixou de estar válida.")
        itens_rascunho = list(
            rascunho.itens.select_for_update().select_related("item_entrada__produto")
        )
        if not itens_rascunho:
            raise ValidationError("O rascunho não possui itens para revisão.")
        itens_xml = diagnostico["itens_xml_original"]
        atuais_por_numero = {item["numero_item"]: item for item in itens_xml}
        for item in itens_rascunho:
            atual = atuais_por_numero.get(item.numero_item_xml)
            if not item.numero_item_xml or not item.item_xml_snapshot or atual != item.item_xml_snapshot:
                raise ValidationError(
                    f"O vínculo com o XML original do item {item.item_entrada.produto} não está íntegro."
                )
        _validar_totais_por_item_xml(itens_rascunho, itens_xml)

        documento_dfe = _documento_dfe_da_entrada(entrada)
        xml_origem = documento_dfe.xml_conteudo if documento_dfe else ""
        rascunho.xml_origem_sha256 = hashlib.sha256(xml_origem.encode("utf-8")).hexdigest()
        rascunho.status = StatusRascunhoDevolucaoFornecedor.AGUARDANDO_REVISAO
        rascunho.submetido_em = timezone.now()
        rascunho.submetido_por = usuario
        rascunho.atualizado_por = usuario
        rascunho.save(
            update_fields=[
                "xml_origem_sha256",
                "status",
                "submetido_em",
                "submetido_por",
                "atualizado_por",
                "atualizado_em",
            ]
        )
        LogAuditoria.objects.create(
            usuario=usuario,
            modulo="fiscal",
            acao="RASCUNHO_DEVOLUCAO_FORNECEDOR_SUBMETIDO",
            descricao=(
                f"Rascunho {rascunho.pk} submetido à revisão com {len(itens_rascunho)} "
                "seleção(ões) mapeadas ao XML original. Nenhum tributo, documento fiscal, "
                "numeração, estoque ou transmissão foi criado."
            ),
            objeto_tipo="RascunhoDevolucaoFornecedor",
            objeto_id=str(rascunho.pk),
            ip=ip,
        )
    return rascunho


def cancelar_rascunho_devolucao_fornecedor(entrada, *, usuario, ip=None):
    """Libera a seleção sem desfazer estoque ou criar efeito fiscal."""
    with transaction.atomic():
        entrada = EntradaCompra.objects.select_for_update().get(pk=entrada.pk)
        empresa_id = empresa_id_do_usuario(usuario)
        if empresa_id is not None and entrada.filial.empresa_id != empresa_id:
            raise ValidationError("Esta entrada não pertence à empresa do usuário.")
        rascunho = (
            RascunhoDevolucaoFornecedor.objects.select_for_update()
            .filter(entrada_compra=entrada, status__in=STATUS_RASCUNHO_ATIVO)
            .first()
        )
        if not rascunho:
            raise ValidationError("Não existe preparação fiscal ativa para cancelar.")
        if rascunho.status not in STATUS_RASCUNHO_CANCELAVEL:
            raise ValidationError(
                "A preparação fiscal aprovada não pode ser cancelada por Compras."
            )
        rascunho.status = StatusRascunhoDevolucaoFornecedor.CANCELADO
        rascunho.atualizado_por = usuario
        rascunho.save(update_fields=["status", "atualizado_por", "atualizado_em"])
        LogAuditoria.objects.create(
            usuario=usuario,
            modulo="fiscal",
            acao="RASCUNHO_DEVOLUCAO_FORNECEDOR_CANCELADO",
            descricao=(
                f"Rascunho {rascunho.pk} da entrada {entrada.pk} cancelado. "
                "Nenhum documento fiscal, estoque ou transmissão foi alterado."
            ),
            objeto_tipo="RascunhoDevolucaoFornecedor",
            objeto_id=str(rascunho.pk),
            ip=ip,
        )
    return rascunho


def _conteudo_revisao(rascunho, itens, decisao, justificativa):
    return {
        "contrato": "supplier_return_fiscal_review_v1",
        "rascunho_id": rascunho.pk,
        "chave_referenciada": rascunho.chave_referenciada,
        "xml_origem_sha256": rascunho.xml_origem_sha256,
        "decisao": decisao,
        "justificativa": justificativa,
        "itens": [
            {
                "item_entrada_id": item.item_entrada_id,
                "numero_item_xml": item.numero_item_xml,
                "quantidade": format(item.quantidade, "f"),
                "item_xml_snapshot": item.item_xml_snapshot,
            }
            for item in itens
        ],
    }


def _hash_conteudo_revisao(conteudo):
    serializado = json.dumps(
        conteudo,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serializado.encode("utf-8")).hexdigest()


def revisar_rascunho_devolucao_fornecedor(
    rascunho,
    *,
    decisao,
    justificativa,
    revisor,
    ip=None,
):
    """Registra decisão imutável sem gerar autorização para emissão."""
    if not has_role(revisor, REVISAO_FISCAL):
        raise ValidationError("O usuário não possui permissão de revisão fiscal.")
    decisao = str(decisao or "").strip()
    if decisao not in DecisaoRevisaoDevolucaoFornecedor.values:
        raise ValidationError("Decisão fiscal inválida.")
    justificativa = str(justificativa or "").strip()
    if len(justificativa) < 10:
        raise ValidationError("Informe uma justificativa fiscal com pelo menos 10 caracteres.")
    if len(justificativa) > 500:
        raise ValidationError("A justificativa fiscal deve ter no máximo 500 caracteres.")

    with transaction.atomic():
        rascunho = (
            RascunhoDevolucaoFornecedor.objects.select_for_update()
            .select_related("entrada_compra__filial")
            .get(pk=rascunho.pk)
        )
        empresa_id = empresa_id_do_usuario(revisor)
        if empresa_id is not None and rascunho.entrada_compra.filial.empresa_id != empresa_id:
            raise ValidationError("Este rascunho não pertence à empresa do revisor.")
        if rascunho.status != StatusRascunhoDevolucaoFornecedor.AGUARDANDO_REVISAO:
            raise ValidationError("Somente rascunhos aguardando revisão podem receber decisão.")

        itens = list(
            rascunho.itens.select_for_update().select_related("item_entrada__produto")
        )
        documento_dfe = _documento_dfe_da_entrada(rascunho.entrada_compra)
        xml_origem = documento_dfe.xml_conteudo if documento_dfe else ""
        hash_atual = hashlib.sha256(xml_origem.encode("utf-8")).hexdigest()
        if not xml_origem or hash_atual != rascunho.xml_origem_sha256:
            raise ValidationError("O XML original divergiu após a submissão; a revisão foi bloqueada.")

        sequencia = (rascunho.revisoes.aggregate(maior=Max("sequencia"))["maior"] or 0) + 1
        conteudo_revisao = _conteudo_revisao(
            rascunho, itens, decisao, justificativa
        )
        revisao = RevisaoDevolucaoFornecedor.objects.create(
            rascunho=rascunho,
            sequencia=sequencia,
            decisao=decisao,
            justificativa=justificativa,
            conteudo_snapshot=conteudo_revisao,
            conteudo_sha256=_hash_conteudo_revisao(conteudo_revisao),
            revisor=revisor,
        )
        if decisao == DecisaoRevisaoDevolucaoFornecedor.APROVAR:
            rascunho.status = StatusRascunhoDevolucaoFornecedor.APROVADO
        else:
            rascunho.status = StatusRascunhoDevolucaoFornecedor.RASCUNHO
            rascunho.xml_origem_sha256 = ""
            rascunho.submetido_em = None
            rascunho.submetido_por = None
        rascunho.atualizado_por = revisor
        rascunho.save(
            update_fields=[
                "status",
                "xml_origem_sha256",
                "submetido_em",
                "submetido_por",
                "atualizado_por",
                "atualizado_em",
            ]
        )
        LogAuditoria.objects.create(
            usuario=revisor,
            modulo="fiscal",
            acao="REVISAO_DEVOLUCAO_FORNECEDOR",
            descricao=(
                f"Revisão {revisao.pk} registrada para o rascunho {rascunho.pk}: {decisao}. "
                "A decisão não gerou documento fiscal, numeração, estoque ou transmissão."
            ),
            objeto_tipo="RevisaoDevolucaoFornecedor",
            objeto_id=str(revisao.pk),
            ip=ip,
        )
    return revisao, rascunho


def _texto_parecer(valor, rotulo, *, maximo=2000):
    texto = str(valor or "").strip()
    if len(texto) < 5:
        raise ValidationError(
            f"Informe {rotulo}; quando não se aplicar, registre isso expressamente."
        )
    if len(texto) > maximo:
        raise ValidationError(f"{rotulo.capitalize()} deve ter no máximo {maximo} caracteres.")
    return texto


def _data_parecer(valor):
    if isinstance(valor, date):
        return valor
    try:
        return date.fromisoformat(str(valor or "").strip())
    except ValueError as exc:
        raise ValidationError("Informe uma data de referência válida para o parecer.") from exc


def registrar_parecer_tributario_devolucao_fornecedor(
    rascunho,
    *,
    dados,
    responsavel,
    ip=None,
):
    """Preserva orientação humana versionada sem calcular ou liberar emissão."""
    if not has_role(responsavel, REVISAO_FISCAL):
        raise ValidationError("O usuário não possui permissão para registrar parecer fiscal.")

    vigencia = _data_parecer(dados.get("vigencia_referencia"))
    cfop = "".join(caractere for caractere in str(dados.get("cfop") or "") if caractere.isdigit())
    catalogo = catalogo_cfop_vigente(vigencia)
    if not catalogo:
        raise ValidationError("Não existe catálogo CFOP oficial vigente para a data informada.")
    erro_cfop = validar_cfop(
        cfop,
        direcao="SAIDA",
        modelo="55",
        data_referencia=vigencia,
    )
    if erro_cfop:
        raise ValidationError(erro_cfop)

    campos = {
        "regime_tributario_referencia": _texto_parecer(
            dados.get("regime_tributario_referencia"), "o regime tributário de referência", maximo=120
        ),
        "natureza_operacao": _texto_parecer(
            dados.get("natureza_operacao"), "a natureza da operação", maximo=120
        ),
        "tratamento_icms": _texto_parecer(dados.get("tratamento_icms"), "o tratamento do ICMS"),
        "tratamento_icms_st_fcp": _texto_parecer(
            dados.get("tratamento_icms_st_fcp"), "o tratamento de ICMS-ST/FCP"
        ),
        "tratamento_ipi": _texto_parecer(dados.get("tratamento_ipi"), "o tratamento do IPI"),
        "tratamento_pis": _texto_parecer(dados.get("tratamento_pis"), "o tratamento do PIS"),
        "tratamento_cofins": _texto_parecer(
            dados.get("tratamento_cofins"), "o tratamento da COFINS"
        ),
        "tratamento_cbenef": _texto_parecer(
            dados.get("tratamento_cbenef"), "o tratamento do cBenef"
        ),
        "tratamento_ibs_cbs": _texto_parecer(
            dados.get("tratamento_ibs_cbs"), "o tratamento de IBS/CBS"
        ),
        "fundamentacao": _texto_parecer(
            dados.get("fundamentacao"), "a fundamentação e fonte da orientação", maximo=4000
        ),
    }

    with transaction.atomic():
        rascunho = (
            RascunhoDevolucaoFornecedor.objects.select_for_update()
            .select_related("entrada_compra__filial")
            .get(pk=rascunho.pk)
        )
        empresa_id = empresa_id_do_usuario(responsavel)
        if empresa_id is not None and rascunho.entrada_compra.filial.empresa_id != empresa_id:
            raise ValidationError("Este rascunho não pertence à empresa do responsável fiscal.")
        if rascunho.status != StatusRascunhoDevolucaoFornecedor.APROVADO:
            raise ValidationError("O parecer exige uma preparação previamente aprovada.")

        revisao_base = rascunho.revisoes.filter(
            decisao=DecisaoRevisaoDevolucaoFornecedor.APROVAR
        ).order_by("-sequencia").first()
        if not revisao_base:
            raise ValidationError("A revisão de aprovação que fundamenta o parecer não foi encontrada.")
        if (
            _hash_conteudo_revisao(revisao_base.conteudo_snapshot)
            != revisao_base.conteudo_sha256
        ):
            raise ValidationError("A revisão de aprovação perdeu a integridade; o parecer foi bloqueado.")

        documento_dfe = _documento_dfe_da_entrada(rascunho.entrada_compra)
        xml_origem = documento_dfe.xml_conteudo if documento_dfe else ""
        hash_atual = hashlib.sha256(xml_origem.encode("utf-8")).hexdigest()
        if not xml_origem or hash_atual != rascunho.xml_origem_sha256:
            raise ValidationError("O XML original divergiu da preparação aprovada; o parecer foi bloqueado.")

        conteudo = {
            "contrato": CONTRATO_PARECER_TRIBUTARIO_DEVOLUCAO_FORNECEDOR,
            "rascunho_id": rascunho.pk,
            "revisao_base_id": revisao_base.pk,
            "revisao_base_sha256": revisao_base.conteudo_sha256,
            "xml_origem_sha256": rascunho.xml_origem_sha256,
            "vigencia_referencia": vigencia.isoformat(),
            "cfop": cfop,
            "catalogo_cfop_id": catalogo.pk,
            "catalogo_cfop_referencia_em": catalogo.referencia_em.isoformat(),
            "catalogo_cfop_sha256": catalogo.fonte_sha256,
            **campos,
        }
        hash_conteudo = _hash_conteudo_revisao(conteudo)
        existente = rascunho.pareceres_tributarios.filter(
            conteudo_sha256=hash_conteudo
        ).first()
        if existente:
            return existente, False

        versao = (
            rascunho.pareceres_tributarios.aggregate(maior=Max("versao"))["maior"] or 0
        ) + 1
        parecer = ParecerTributarioDevolucaoFornecedor.objects.create(
            rascunho=rascunho,
            revisao_base=revisao_base,
            versao=versao,
            vigencia_referencia=vigencia,
            cfop=cfop,
            conteudo_snapshot=conteudo,
            conteudo_sha256=hash_conteudo,
            responsavel=responsavel,
            **campos,
        )
        LogAuditoria.objects.create(
            usuario=responsavel,
            modulo="fiscal",
            acao="PARECER_TRIBUTARIO_DEVOLUCAO_FORNECEDOR",
            descricao=(
                f"Parecer tributário {parecer.pk}, versão {versao}, registrado para o "
                f"rascunho {rascunho.pk}. Nenhum cálculo, documento, numeração, estoque "
                "ou transmissão foi criado."
            ),
            objeto_tipo="ParecerTributarioDevolucaoFornecedor",
            objeto_id=str(parecer.pk),
            ip=ip,
        )
    return parecer, True


def _codigo_cst_ou_na(valor, rotulo):
    codigo = str(valor or "").strip().upper()
    if codigo == "NA":
        return codigo
    if len(codigo) != 2 or not codigo.isdigit():
        raise ValidationError(f"{rotulo} deve conter dois dígitos ou NA.")
    return codigo


def _parametros_item(dados, item):
    sufixo = str(item.pk)
    tipo_icms = str(dados.get(f"tipo_codigo_icms_{sufixo}") or "").strip().upper()
    if tipo_icms not in TipoCodigoICMSDevolucaoFornecedor.values:
        raise ValidationError(f"Informe CST, CSOSN ou não aplicável para o nItem {item.numero_item_xml}.")
    codigo_icms = "".join(
        caractere
        for caractere in str(dados.get(f"codigo_icms_{sufixo}") or "")
        if caractere.isdigit()
    )
    if tipo_icms == TipoCodigoICMSDevolucaoFornecedor.CST and len(codigo_icms) != 2:
        raise ValidationError(f"O CST do ICMS do nItem {item.numero_item_xml} deve ter dois dígitos.")
    if tipo_icms == TipoCodigoICMSDevolucaoFornecedor.CSOSN and len(codigo_icms) != 3:
        raise ValidationError(f"O CSOSN do nItem {item.numero_item_xml} deve ter três dígitos.")
    if tipo_icms == TipoCodigoICMSDevolucaoFornecedor.NAO_APLICAVEL:
        if codigo_icms:
            raise ValidationError(f"Não informe código de ICMS quando o nItem {item.numero_item_xml} não se aplica.")

    origem_icms = str(dados.get(f"origem_icms_{sufixo}") or "").strip()
    if len(origem_icms) != 1 or origem_icms not in "012345678":
        raise ValidationError(f"A origem do ICMS do nItem {item.numero_item_xml} deve ser um código de 0 a 8.")
    codigo_cbenef = str(dados.get(f"codigo_cbenef_{sufixo}") or "").strip().upper()
    if codigo_cbenef != "NA" and not (
        len(codigo_cbenef) == 8
        and codigo_cbenef.startswith("GO")
        and codigo_cbenef[2:].isdigit()
    ):
        raise ValidationError(
            f"O cBenef do nItem {item.numero_item_xml} deve seguir GO + 6 dígitos ou ser NA."
        )

    observacao = str(dados.get(f"observacao_{sufixo}") or "").strip()
    if len(observacao) > 2000:
        raise ValidationError(f"A observação do nItem {item.numero_item_xml} excede 2.000 caracteres.")
    return {
        "item_rascunho_id": item.pk,
        "numero_item_xml": item.numero_item_xml,
        "tipo_codigo_icms": tipo_icms,
        "origem_icms": origem_icms,
        "codigo_icms": codigo_icms,
        "codigo_ipi": _codigo_cst_ou_na(
            dados.get(f"codigo_ipi_{sufixo}"), f"O CST do IPI do nItem {item.numero_item_xml}"
        ),
        "codigo_pis": _codigo_cst_ou_na(
            dados.get(f"codigo_pis_{sufixo}"), f"O CST do PIS do nItem {item.numero_item_xml}"
        ),
        "codigo_cofins": _codigo_cst_ou_na(
            dados.get(f"codigo_cofins_{sufixo}"), f"O CST da COFINS do nItem {item.numero_item_xml}"
        ),
        "codigo_cbenef": codigo_cbenef,
        "tratamento_icms_st_fcp": _texto_parecer(
            dados.get(f"tratamento_icms_st_fcp_{sufixo}"),
            f"o tratamento de ICMS-ST/FCP do nItem {item.numero_item_xml}",
        ),
        "tratamento_cbenef": _texto_parecer(
            dados.get(f"tratamento_cbenef_{sufixo}"),
            f"o tratamento do cBenef do nItem {item.numero_item_xml}",
        ),
        "tratamento_ibs_cbs": _texto_parecer(
            dados.get(f"tratamento_ibs_cbs_{sufixo}"),
            f"o tratamento de IBS/CBS do nItem {item.numero_item_xml}",
        ),
        "observacao": observacao,
    }


def registrar_parametrizacao_itens_devolucao_fornecedor(
    rascunho,
    *,
    parecer_id,
    dados,
    responsavel,
    ip=None,
):
    """Versiona códigos orientados por item sem calcular ou gerar documento."""
    if not has_role(responsavel, REVISAO_FISCAL):
        raise ValidationError("O usuário não possui permissão para parametrização fiscal.")
    try:
        parecer_id = int(parecer_id)
    except (TypeError, ValueError) as exc:
        raise ValidationError("Selecione a versão do parecer que fundamenta os parâmetros.") from exc

    with transaction.atomic():
        rascunho = (
            RascunhoDevolucaoFornecedor.objects.select_for_update()
            .select_related("entrada_compra__filial")
            .get(pk=rascunho.pk)
        )
        empresa_id = empresa_id_do_usuario(responsavel)
        if empresa_id is not None and rascunho.entrada_compra.filial.empresa_id != empresa_id:
            raise ValidationError("Este rascunho não pertence à empresa do responsável fiscal.")
        if rascunho.status != StatusRascunhoDevolucaoFornecedor.APROVADO:
            raise ValidationError("A parametrização exige uma preparação previamente aprovada.")

        parecer = rascunho.pareceres_tributarios.filter(pk=parecer_id).first()
        if not parecer:
            raise ValidationError("O parecer selecionado não pertence a esta preparação.")
        if _hash_conteudo_revisao(parecer.conteudo_snapshot) != parecer.conteudo_sha256:
            raise ValidationError("O parecer selecionado perdeu a integridade.")

        documento_dfe = _documento_dfe_da_entrada(rascunho.entrada_compra)
        xml_origem = documento_dfe.xml_conteudo if documento_dfe else ""
        if (
            not xml_origem
            or hashlib.sha256(xml_origem.encode("utf-8")).hexdigest()
            != rascunho.xml_origem_sha256
        ):
            raise ValidationError("O XML original divergiu da preparação aprovada.")

        itens = list(rascunho.itens.select_for_update().order_by("pk"))
        if not itens:
            raise ValidationError("A preparação aprovada não possui itens para parametrizar.")
        parametros = [_parametros_item(dados, item) for item in itens]
        conteudo = {
            "contrato": CONTRATO_PARAMETROS_ITEM_DEVOLUCAO_FORNECEDOR,
            "rascunho_id": rascunho.pk,
            "parecer_id": parecer.pk,
            "parecer_versao": parecer.versao,
            "parecer_sha256": parecer.conteudo_sha256,
            "xml_origem_sha256": rascunho.xml_origem_sha256,
            "itens": parametros,
        }
        hash_conteudo = _hash_conteudo_revisao(conteudo)
        existente = rascunho.parametrizacoes_fiscais.filter(
            conteudo_sha256=hash_conteudo
        ).first()
        if existente:
            return existente, False

        versao = (
            rascunho.parametrizacoes_fiscais.aggregate(maior=Max("versao"))["maior"] or 0
        ) + 1
        parametrizacao = ParametrizacaoFiscalDevolucaoFornecedor.objects.create(
            rascunho=rascunho,
            parecer=parecer,
            versao=versao,
            conteudo_snapshot=conteudo,
            conteudo_sha256=hash_conteudo,
            responsavel=responsavel,
        )
        ItemParametrizacaoFiscalDevolucaoFornecedor.objects.bulk_create(
            [
                ItemParametrizacaoFiscalDevolucaoFornecedor(
                    parametrizacao=parametrizacao,
                    item_rascunho_id=item["item_rascunho_id"],
                    numero_item_xml=item["numero_item_xml"],
                    tipo_codigo_icms=item["tipo_codigo_icms"],
                    origem_icms=item["origem_icms"],
                    codigo_icms=item["codigo_icms"],
                    codigo_ipi=item["codigo_ipi"],
                    codigo_pis=item["codigo_pis"],
                    codigo_cofins=item["codigo_cofins"],
                    codigo_cbenef=item["codigo_cbenef"],
                    tratamento_icms_st_fcp=item["tratamento_icms_st_fcp"],
                    tratamento_cbenef=item["tratamento_cbenef"],
                    tratamento_ibs_cbs=item["tratamento_ibs_cbs"],
                    observacao=item["observacao"],
                )
                for item in parametros
            ]
        )
        LogAuditoria.objects.create(
            usuario=responsavel,
            modulo="fiscal",
            acao="PARAMETRIZACAO_ITEM_DEVOLUCAO_FORNECEDOR",
            descricao=(
                f"Parametrização {parametrizacao.pk}, versão {versao}, registrada com "
                f"{len(parametros)} nItem(ns) para o rascunho {rascunho.pk}. Nenhum cálculo, "
                "documento, numeração, estoque ou transmissão foi criado."
            ),
            objeto_tipo="ParametrizacaoFiscalDevolucaoFornecedor",
            objeto_id=str(parametrizacao.pk),
            ip=ip,
        )
    return parametrizacao, True


def _decimal_memoria(valor, rotulo, *, casas):
    texto = str(valor or "").strip().replace(" ", "")
    if not texto:
        raise ValidationError(f"Informe {rotulo}, inclusive quando o valor for zero.")
    if "," in texto:
        if "." in texto:
            texto = texto.replace(".", "")
        texto = texto.replace(",", ".")
    try:
        numero = Decimal(texto)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError(f"{rotulo} possui formato decimal inválido.") from exc
    if not numero.is_finite() or numero < 0:
        raise ValidationError(f"{rotulo} deve ser um número não negativo.")
    quantizador = CENTAVOS if casas == 2 else QUATRO_DECIMAIS
    try:
        normalizado = numero.quantize(quantizador)
    except InvalidOperation as exc:
        raise ValidationError(f"{rotulo} excede o limite permitido.") from exc
    if numero != normalizado:
        raise ValidationError(f"{rotulo} deve possuir no máximo {casas} casas decimais.")
    limite = Decimal("9999999999999.99") if casas == 2 else Decimal("999.9999")
    if normalizado > limite:
        raise ValidationError(f"{rotulo} excede o limite permitido.")
    return normalizado


def _decimal_snapshot(valor, casas):
    return f"{valor:.{casas}f}"


def _snapshot_item_parametrizacao(item):
    return {
        "item_rascunho_id": item.item_rascunho_id,
        "numero_item_xml": item.numero_item_xml,
        "tipo_codigo_icms": item.tipo_codigo_icms,
        "origem_icms": item.origem_icms,
        "codigo_icms": item.codigo_icms,
        "codigo_ipi": item.codigo_ipi,
        "codigo_pis": item.codigo_pis,
        "codigo_cofins": item.codigo_cofins,
        "codigo_cbenef": item.codigo_cbenef,
        "tratamento_icms_st_fcp": item.tratamento_icms_st_fcp,
        "tratamento_cbenef": item.tratamento_cbenef,
        "tratamento_ibs_cbs": item.tratamento_ibs_cbs,
        "observacao": item.observacao,
    }


def _dados_item_memoria(dados, item_parametrizacao):
    sufixo = str(item_parametrizacao.pk)
    item = {
        "item_parametrizacao_id": item_parametrizacao.pk,
        "item_rascunho_id": item_parametrizacao.item_rascunho_id,
        "numero_item_xml": item_parametrizacao.numero_item_xml,
        "valor_operacao": _decimal_memoria(
            dados.get(f"valor_operacao_{sufixo}"),
            f"o valor da operação do nItem {item_parametrizacao.numero_item_xml}",
            casas=2,
        ),
    }
    for chave, rotulo in TRIBUTOS_MEMORIA_CALCULO:
        item[f"base_{chave}"] = _decimal_memoria(
            dados.get(f"base_{chave}_{sufixo}"),
            f"a base de {rotulo} do nItem {item_parametrizacao.numero_item_xml}",
            casas=2,
        )
        item[f"aliquota_{chave}"] = _decimal_memoria(
            dados.get(f"aliquota_{chave}_{sufixo}"),
            f"a alíquota de {rotulo} do nItem {item_parametrizacao.numero_item_xml}",
            casas=4,
        )
        item[f"valor_{chave}"] = _decimal_memoria(
            dados.get(f"valor_{chave}_{sufixo}"),
            f"o valor de {rotulo} do nItem {item_parametrizacao.numero_item_xml}",
            casas=2,
        )

    codigos_nao_aplicaveis = []
    if item_parametrizacao.tipo_codigo_icms == TipoCodigoICMSDevolucaoFornecedor.NAO_APLICAVEL:
        codigos_nao_aplicaveis.append(("icms", "ICMS"))
    for chave, rotulo, codigo in (
        ("ipi", "IPI", item_parametrizacao.codigo_ipi),
        ("pis", "PIS", item_parametrizacao.codigo_pis),
        ("cofins", "COFINS", item_parametrizacao.codigo_cofins),
    ):
        if codigo == "NA":
            codigos_nao_aplicaveis.append((chave, rotulo))
    for chave, rotulo in codigos_nao_aplicaveis:
        if any(item[f"{campo}_{chave}"] != 0 for campo in ("base", "aliquota", "valor")):
            raise ValidationError(
                f"{rotulo} está marcado como não aplicável no nItem "
                f"{item_parametrizacao.numero_item_xml}; informe zero em base, alíquota e valor."
            )

    observacao = str(dados.get(f"observacao_memoria_{sufixo}") or "").strip()
    if len(observacao) > 2000:
        raise ValidationError(
            f"A observação da memória do nItem {item_parametrizacao.numero_item_xml} excede 2.000 caracteres."
        )
    item["observacao"] = observacao
    return item


def _snapshot_item_memoria(item):
    snapshot = {
        "item_parametrizacao_id": item["item_parametrizacao_id"],
        "item_rascunho_id": item["item_rascunho_id"],
        "numero_item_xml": item["numero_item_xml"],
        "valor_operacao": _decimal_snapshot(item["valor_operacao"], 2),
    }
    for chave, _rotulo in TRIBUTOS_MEMORIA_CALCULO:
        snapshot[f"base_{chave}"] = _decimal_snapshot(item[f"base_{chave}"], 2)
        snapshot[f"aliquota_{chave}"] = _decimal_snapshot(item[f"aliquota_{chave}"], 4)
        snapshot[f"valor_{chave}"] = _decimal_snapshot(item[f"valor_{chave}"], 2)
    snapshot["observacao"] = item["observacao"]
    return snapshot


def _totais_memoria(dados, itens):
    campos = [("valor_operacao", "valor total da operação")]
    for chave, rotulo in TRIBUTOS_MEMORIA_CALCULO:
        campos.extend(
            [
                (f"base_{chave}", f"total da base de {rotulo}"),
                (f"valor_{chave}", f"total do valor de {rotulo}"),
            ]
        )
    totais = {}
    for campo, rotulo in campos:
        informado = _decimal_memoria(
            dados.get(f"total_{campo}"),
            rotulo,
            casas=2,
        )
        calculado = sum((item[campo] for item in itens), Decimal("0.00"))
        if informado != calculado:
            raise ValidationError(
                f"O {rotulo} informado ({informado:.2f}) não confere com a soma "
                f"dos itens ({calculado:.2f})."
            )
        totais[campo] = _decimal_snapshot(informado, 2)
    return totais


def registrar_memoria_calculo_devolucao_fornecedor(
    rascunho,
    *,
    parametrizacao_id,
    dados,
    responsavel,
    ip=None,
):
    """Versiona valores informados e confere totais sem gerar tributação ou XML."""
    if not has_role(responsavel, REVISAO_FISCAL):
        raise ValidationError("O usuário não possui permissão para registrar memória de cálculo fiscal.")
    try:
        parametrizacao_id = int(parametrizacao_id)
    except (TypeError, ValueError) as exc:
        raise ValidationError("Selecione a versão dos parâmetros que fundamenta a memória.") from exc

    with transaction.atomic():
        rascunho = (
            RascunhoDevolucaoFornecedor.objects.select_for_update()
            .select_related("entrada_compra__filial")
            .get(pk=rascunho.pk)
        )
        empresa_id = empresa_id_do_usuario(responsavel)
        if empresa_id is not None and rascunho.entrada_compra.filial.empresa_id != empresa_id:
            raise ValidationError("Este rascunho não pertence à empresa do responsável fiscal.")
        if rascunho.status != StatusRascunhoDevolucaoFornecedor.APROVADO:
            raise ValidationError("A memória de cálculo exige uma preparação previamente aprovada.")

        parametrizacao = (
            rascunho.parametrizacoes_fiscais.select_for_update()
            .select_related("parecer")
            .filter(pk=parametrizacao_id)
            .first()
        )
        if not parametrizacao:
            raise ValidationError("A parametrização selecionada não pertence a esta preparação.")
        if _hash_conteudo_revisao(parametrizacao.conteudo_snapshot) != parametrizacao.conteudo_sha256:
            raise ValidationError("A parametrização selecionada perdeu a integridade.")
        if _hash_conteudo_revisao(parametrizacao.parecer.conteudo_snapshot) != parametrizacao.parecer.conteudo_sha256:
            raise ValidationError("O parecer vinculado à parametrização perdeu a integridade.")

        documento_dfe = _documento_dfe_da_entrada(rascunho.entrada_compra)
        xml_origem = documento_dfe.xml_conteudo if documento_dfe else ""
        if (
            not xml_origem
            or hashlib.sha256(xml_origem.encode("utf-8")).hexdigest()
            != rascunho.xml_origem_sha256
        ):
            raise ValidationError("O XML original divergiu da preparação aprovada.")

        itens_parametrizacao = list(
            parametrizacao.itens.select_for_update()
            .select_related("item_rascunho")
            .order_by("item_rascunho_id")
        )
        ids_itens_rascunho = list(
            rascunho.itens.select_for_update()
            .order_by("pk")
            .values_list("pk", flat=True)
        )
        snapshot_parametros = parametrizacao.conteudo_snapshot.get("itens")
        if (
            not itens_parametrizacao
            or ids_itens_rascunho
            != [item.item_rascunho_id for item in itens_parametrizacao]
            or snapshot_parametros
            != [_snapshot_item_parametrizacao(item) for item in itens_parametrizacao]
        ):
            raise ValidationError("Os itens da parametrização selecionada perderam a integridade.")

        itens = [_dados_item_memoria(dados, item) for item in itens_parametrizacao]
        totais = _totais_memoria(dados, itens)
        criterio = _texto_parecer(
            dados.get("criterio_arredondamento"),
            "o critério de cálculo e arredondamento",
        )
        if len(criterio) > 500:
            raise ValidationError("O critério de cálculo e arredondamento excede 500 caracteres.")

        conteudo = {
            "contrato": CONTRATO_MEMORIA_CALCULO_DEVOLUCAO_FORNECEDOR,
            "rascunho_id": rascunho.pk,
            "parametrizacao_id": parametrizacao.pk,
            "parametrizacao_versao": parametrizacao.versao,
            "parametrizacao_sha256": parametrizacao.conteudo_sha256,
            "parecer_id": parametrizacao.parecer_id,
            "parecer_sha256": parametrizacao.parecer.conteudo_sha256,
            "xml_origem_sha256": rascunho.xml_origem_sha256,
            "criterio_arredondamento": criterio,
            "totais": totais,
            "itens": [_snapshot_item_memoria(item) for item in itens],
        }
        hash_conteudo = _hash_conteudo_revisao(conteudo)
        existente = rascunho.memorias_calculo.filter(conteudo_sha256=hash_conteudo).first()
        if existente:
            return existente, False

        versao = (
            rascunho.memorias_calculo.aggregate(maior=Max("versao"))["maior"] or 0
        ) + 1
        memoria = MemoriaCalculoDevolucaoFornecedor.objects.create(
            rascunho=rascunho,
            parametrizacao=parametrizacao,
            versao=versao,
            criterio_arredondamento=criterio,
            totais_snapshot=totais,
            conteudo_snapshot=conteudo,
            conteudo_sha256=hash_conteudo,
            responsavel=responsavel,
        )
        ItemMemoriaCalculoDevolucaoFornecedor.objects.bulk_create(
            [
                ItemMemoriaCalculoDevolucaoFornecedor(
                    memoria=memoria,
                    item_parametrizacao_id=item["item_parametrizacao_id"],
                    item_rascunho_id=item["item_rascunho_id"],
                    numero_item_xml=item["numero_item_xml"],
                    valor_operacao=item["valor_operacao"],
                    observacao=item["observacao"],
                    **{
                        f"{campo}_{chave}": item[f"{campo}_{chave}"]
                        for chave, _rotulo in TRIBUTOS_MEMORIA_CALCULO
                        for campo in ("base", "aliquota", "valor")
                    },
                )
                for item in itens
            ]
        )
        LogAuditoria.objects.create(
            usuario=responsavel,
            modulo="fiscal",
            acao="MEMORIA_CALCULO_DEVOLUCAO_FORNECEDOR",
            descricao=(
                f"Memória de cálculo {memoria.pk}, versão {versao}, registrada com "
                f"{len(itens)} nItem(ns) para o rascunho {rascunho.pk}. Os totais foram "
                "conferidos; nenhum documento, numeração, estoque, XML ou transmissão foi criado."
            ),
            objeto_tipo="MemoriaCalculoDevolucaoFornecedor",
            objeto_id=str(memoria.pk),
            ip=ip,
        )
    return memoria, True
