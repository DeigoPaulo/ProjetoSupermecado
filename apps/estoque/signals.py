from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.empresas.services_snapshots import enfileirar_snapshot_estoque, enfileirar_snapshot_produto
from apps.produtos.models import Produto

from .models import Estoque, MovimentacaoEstoque


@receiver(post_save, sender=Produto, dispatch_uid="produto_enfileirar_snapshot_atualizado")
def enfileirar_snapshot_apos_atualizacao(sender, instance, created, **kwargs):
    if getattr(instance, "_sincronizacao_entrada", False):
        return

    empresas_publicadas = set()
    for estoque in instance.estoques.select_related("filial__empresa").order_by("filial_id"):
        empresa = estoque.filial.empresa
        if empresa.pk in empresas_publicadas:
            continue
        enfileirar_snapshot_produto(produto=instance, empresa=empresa, filial=estoque.filial)
        empresas_publicadas.add(empresa.pk)


@receiver(post_save, sender=MovimentacaoEstoque, dispatch_uid="estoque_enfileirar_saldo_atualizado")
def enfileirar_saldo_apos_movimentacao(sender, instance, created, **kwargs):
    if not created or (instance.referencia or "").startswith("sync:"):
        return

    estoque = Estoque.objects.filter(produto=instance.produto, filial=instance.filial).first()
    if not estoque:
        return

    enfileirar_snapshot_produto(
        produto=instance.produto,
        empresa=instance.filial.empresa,
        filial=instance.filial,
    )
    enfileirar_snapshot_estoque(estoque=estoque, movimentacao=instance)