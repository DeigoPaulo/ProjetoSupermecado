from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("compras", "0006_entradacompra_xml"),
        ("estoque", "0019_lote_estoque"),
    ]

    operations = [
        migrations.AddField(
            model_name="itementradacompra",
            name="codigo_lote",
            field=models.CharField(blank=True, max_length=60),
        ),
        migrations.AddField(
            model_name="itementradacompra",
            name="fabricacao",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="itementradacompra",
            name="validade",
            field=models.DateField(blank=True, null=True),
        ),
    ]
