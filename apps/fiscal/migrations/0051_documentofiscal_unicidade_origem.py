from django.db import migrations, models
from django.db.models import Count


def validar_documentos_ativos_unicos(apps, schema_editor):
    DocumentoFiscal = apps.get_model("fiscal", "DocumentoFiscal")
    documentos_ativos = DocumentoFiscal.objects.exclude(status="CANCELADO")

    vendas_duplicadas = list(
        documentos_ativos.exclude(venda_id=None)
        .values("venda_id")
        .annotate(total=Count("id"))
        .filter(total__gt=1)
        .values_list("venda_id", flat=True)[:20]
    )
    pedidos_duplicados = list(
        documentos_ativos.exclude(pedido_online_id=None)
        .values("pedido_online_id")
        .annotate(total=Count("id"))
        .filter(total__gt=1)
        .values_list("pedido_online_id", flat=True)[:20]
    )
    if vendas_duplicadas or pedidos_duplicados:
        raise RuntimeError(
            "Existem documentos fiscais nao cancelados duplicados. "
            f"Vendas: {vendas_duplicadas or 'nenhuma'}; "
            f"pedidos online: {pedidos_duplicados or 'nenhum'}. "
            "Regularize os registros antes de aplicar a migration 0051."
        )


class Migration(migrations.Migration):

    dependencies = [
        ("fiscal", "0050_memoriacalculodevolucaofornecedor_correcao_de_and_more"),
    ]

    operations = [
        migrations.RunPython(validar_documentos_ativos_unicos, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="documentofiscal",
            constraint=models.UniqueConstraint(
                condition=models.Q(("venda__isnull", False), ~models.Q(("status", "CANCELADO"))),
                fields=("venda",),
                name="fisc_doc_venda_ativo_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="documentofiscal",
            constraint=models.UniqueConstraint(
                condition=models.Q(
                    ("pedido_online__isnull", False),
                    ~models.Q(("status", "CANCELADO")),
                ),
                fields=("pedido_online",),
                name="fisc_doc_pedido_ativo_uniq",
            ),
        ),
    ]
