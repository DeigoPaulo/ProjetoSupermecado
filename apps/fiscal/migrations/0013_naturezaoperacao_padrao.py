from django.db import migrations, models
from django.db.models import Q


def definir_naturezas_padrao(apps, schema_editor):
    Natureza = apps.get_model("fiscal", "NaturezaOperacao")
    grupos = (
        Natureza.objects.filter(ativo=True)
        .order_by("empresa_id", "tipo_documento")
        .values_list("empresa_id", "tipo_documento")
        .distinct()
    )
    for empresa_id, tipo_documento in grupos:
        primeira = (
            Natureza.objects.filter(
                empresa_id=empresa_id,
                tipo_documento=tipo_documento,
                ativo=True,
            )
            .order_by("pk")
            .first()
        )
        if primeira:
            Natureza.objects.filter(pk=primeira.pk).update(padrao=True)


class Migration(migrations.Migration):
    dependencies = [
        ("fiscal", "0012_natureza_operacao_por_empresa"),
    ]

    operations = [
        migrations.AddField(
            model_name="naturezaoperacao",
            name="padrao",
            field=models.BooleanField(
                default=False,
                help_text="Usada automaticamente nas emissões deste tipo de documento.",
                verbose_name="Natureza padrão",
            ),
        ),
        migrations.RunPython(definir_naturezas_padrao, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="naturezaoperacao",
            constraint=models.UniqueConstraint(
                condition=Q(("padrao", True)),
                fields=("empresa", "tipo_documento"),
                name="fiscal_nat_empresa_tipo_padrao_uniq",
            ),
        ),
    ]
