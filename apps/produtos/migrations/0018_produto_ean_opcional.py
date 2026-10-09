from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("produtos", "0017_alter_produto_reducao_base_icms"),
    ]

    operations = [
        migrations.AlterField(
            model_name="produto",
            name="codigo_barras",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddConstraint(
            model_name="produto",
            constraint=models.UniqueConstraint(
                fields=["codigo_barras"],
                condition=~models.Q(codigo_barras=""),
                name="produtos_ean_principal_unico_preenchido",
            ),
        ),
    ]
