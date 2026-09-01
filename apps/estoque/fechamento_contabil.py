import hashlib
import json
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import PerfilUsuario, TipoPerfil
from apps.auditoria.models import LogAuditoria

from .models import Estoque, FechamentoEstoqueContabil, ItemFechamentoEstoqueContabil


CRITERIO_CUSTO = "CUSTO_MEDIO_PONDERADO_MOVEL"


def _dados_posicao(filial):
    linhas = []
    for saldo in Estoque.objects.select_related("produto").filter(filial=filial).order_by("produto_id"):
        valor_custo = (saldo.quantidade_atual * saldo.custo_medio).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        linhas.append(
            {
                "produto_id": saldo.produto_id,
                "codigo_interno": saldo.produto.codigo_interno,
                "codigo_barras": saldo.produto.codigo_barras,
                "nome_produto": saldo.produto.nome,
                "ncm": saldo.produto.ncm,
                "cest": saldo.produto.cest,
                "unidade": saldo.produto.get_unidade_display(),
                "quantidade_fisica": str(saldo.quantidade_atual),
                "quantidade_reservada": str(saldo.quantidade_reservada),
                "quantidade_disponivel": str(saldo.quantidade_disponivel),
                "custo_medio": str(saldo.custo_medio),
                "valor_custo": str(valor_custo),
            }
        )
    return linhas


def _hash_posicao(filial_id, data_referencia, linhas):
    conteudo = json.dumps(
        {
            "filial_id": filial_id,
            "data_referencia": data_referencia.isoformat(),
            "criterio_custo": CRITERIO_CUSTO,
            "itens": linhas,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(conteudo).hexdigest()


@transaction.atomic
def capturar_fechamento_estoque_contabil(*, filial, usuario, data_referencia=None):
    if not usuario or not usuario.is_active:
        raise ValidationError("Informe um usuário ativo responsável pelo fechamento.")
    autorizado = usuario.is_superuser or PerfilUsuario.objects.filter(
        usuario=usuario,
        is_active=True,
        filial__empresa_id=filial.empresa_id,
        tipo__in=[TipoPerfil.ADMINISTRADOR, TipoPerfil.CONTABILIDADE],
    ).exists()
    if not autorizado:
        raise ValidationError("O fechamento exige Master, Administração ou Contabilidade da mesma empresa.")
    data_referencia = data_referencia or timezone.localdate()
    if data_referencia != timezone.localdate():
        raise ValidationError(
            "O fechamento só pode capturar a posição do dia atual; não é permitido fabricar snapshot retroativo."
        )
    linhas = _dados_posicao(filial)
    conteudo_sha256 = _hash_posicao(filial.pk, data_referencia, linhas)
    existente = FechamentoEstoqueContabil.objects.filter(
        filial=filial, data_referencia=data_referencia
    ).first()
    if existente:
        if existente.conteudo_sha256 != conteudo_sha256:
            raise ValidationError(
                "Já existe fechamento imutável para esta filial/data e o estoque atual diverge dele."
            )
        return existente, False

    valor_total = sum((Decimal(linha["valor_custo"]) for linha in linhas), Decimal("0.00"))
    fechamento = FechamentoEstoqueContabil.objects.create(
        filial=filial,
        data_referencia=data_referencia,
        criterio_custo=CRITERIO_CUSTO,
        total_itens=len(linhas),
        valor_total_custo=valor_total,
        conteudo_sha256=conteudo_sha256,
        capturado_por=usuario,
    )
    ItemFechamentoEstoqueContabil.objects.bulk_create(
        [
            ItemFechamentoEstoqueContabil(
                fechamento=fechamento,
                produto_id=linha["produto_id"],
                codigo_interno=linha["codigo_interno"],
                codigo_barras=linha["codigo_barras"],
                nome_produto=linha["nome_produto"],
                ncm=linha["ncm"],
                cest=linha["cest"],
                unidade=linha["unidade"],
                quantidade_fisica=Decimal(linha["quantidade_fisica"]),
                quantidade_reservada=Decimal(linha["quantidade_reservada"]),
                quantidade_disponivel=Decimal(linha["quantidade_disponivel"]),
                custo_medio=Decimal(linha["custo_medio"]),
                valor_custo=Decimal(linha["valor_custo"]),
            )
            for linha in linhas
        ]
    )
    LogAuditoria.objects.create(
        usuario=usuario,
        modulo="estoque",
        acao="FECHAMENTO_ESTOQUE_CONTABIL",
        descricao=(
            f"Fechamento contábil de estoque da filial {filial.pk} em {data_referencia}: "
            f"{fechamento.total_itens} item(ns), SHA-256 {fechamento.conteudo_sha256}."
        ),
        objeto_tipo="FechamentoEstoqueContabil",
        objeto_id=str(fechamento.pk),
    )
    return fechamento, True
