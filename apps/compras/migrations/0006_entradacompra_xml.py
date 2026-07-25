from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("compras", "0005_cotacao_compra"),
    ]

    operations = [
        migrations.AddField(
            model_name="entradacompra",
            name="chave_acesso_xml",
            field=models.CharField(blank=True, max_length=44, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="entradacompra",
            name="importada_xml_em",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="entradacompra",
            name="total_documento",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True),
        ),
    ]
