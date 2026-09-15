from django.db import migrations, models


def classificar_series_existentes(apps, schema_editor):
    SerieFiscal = apps.get_model("fiscal", "SerieFiscal")
    ConfiguracaoFiscal = apps.get_model("fiscal", "ConfiguracaoFiscal")

    ambientes_por_filial = dict(
        ConfiguracaoFiscal.objects.values_list("filial_id", "ambiente")
    )
    for serie in SerieFiscal.objects.all().iterator():
        ambiente = ambientes_por_filial.get(serie.filial_id, "HOMOLOGACAO")
        if serie.ambiente != ambiente:
            SerieFiscal.objects.filter(pk=serie.pk).update(ambiente=ambiente)


class Migration(migrations.Migration):

    dependencies = [
        ("fiscal", "0051_documentofiscal_unicidade_origem"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="seriefiscal",
            options={
                "ordering": [
                    "filial__nome",
                    "tipo_documento",
                    "ambiente",
                    "serie",
                ]
            },
        ),
        migrations.AddField(
            model_name="seriefiscal",
            name="ambiente",
            field=models.CharField(
                choices=[
                    ("HOMOLOGACAO", "Homologacao"),
                    ("PRODUCAO", "Producao"),
                ],
                default="HOMOLOGACAO",
                max_length=20,
            ),
        ),
        migrations.RunPython(classificar_series_existentes, migrations.RunPython.noop),
        migrations.AlterUniqueTogether(
            name="seriefiscal",
            unique_together={("filial", "tipo_documento", "ambiente", "serie")},
        ),
        migrations.AlterUniqueTogether(
            name="documentofiscal",
            unique_together={
                ("filial", "tipo_documento", "ambiente", "serie", "numero")
            },
        ),
    ]
