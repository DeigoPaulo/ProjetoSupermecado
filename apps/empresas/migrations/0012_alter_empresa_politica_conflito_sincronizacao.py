from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("empresas", "0011_empresa_politica_conflito_sincronizacao"),
    ]

    operations = [
        migrations.AlterField(
            model_name="empresa",
            name="politica_conflito_sincronizacao",
            field=models.CharField(
                choices=[
                    ("MANUAL", "Resolver manualmente"),
                    ("REMOTO_PRODUTOS_ESTOQUE", "Nuvem prevalece para produtos e estoque"),
                    ("LOCAL_PRODUTOS_ESTOQUE", "Loja prevalece para produtos e estoque"),
                ],
                default="MANUAL",
                max_length=40,
                verbose_name="Politica de conflito",
            ),
        ),
    ]
