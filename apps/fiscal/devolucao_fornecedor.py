"""Pré-diagnóstico e rascunho documental da devolução ao fornecedor.

O fluxo é deliberadamente não emissivo: persiste somente a preparação operacional,
não escolhe tributação, não cria DocumentoFiscal e não movimenta estoque. Ele
separa evidências da entrada das decisões dependentes do contador e do caso real.
"""

from decimal import Decimal, InvalidOperation

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import transaction
from django.db.models import Sum

from apps.clientes.escopo import empresa_id_do_usuario
from apps.compras.models import EntradaCompra, ItemEntradaCompra, StatusEntradaCompra

from apps.auditoria.models import LogAuditoria

from .pacote_contabil import analisar_xml_nfe
from .models import (
    ItemRascunhoDevolucaoFornecedor,
    RascunhoDevolucaoFornecedor,
    StatusRascunhoDevolucaoFornecedor,
)


CONTRATO_PREPARACAO_DEVOLUCAO_FORNECEDOR = "supplier_return_fiscal_preparation_v1"
CONTRATO_RASCUNHO_DEVOLUCAO_FORNECEDOR = "supplier_return_draft_v1"
STATUS_RASCUNHO_ATIVO = (
    StatusRascunhoDevolucaoFornecedor.RASCUNHO,
    StatusRascunhoDevolucaoFornecedor.AGUARDANDO_REVISAO,
)
MILESIMOS = Decimal("0.001")


def _digitos(valor):
    return "".join(caractere for caractere in str(valor or "") if caractere.isdigit())


def _documento_dfe_da_entrada(entrada):
    try:
        return entrada.documento_dfe_recebido
    except ObjectDoesNotExist:
        return None


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
