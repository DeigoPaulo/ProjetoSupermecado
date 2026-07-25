from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("produtos", "0004_alter_produto_imagem_alter_produtoimagem_imagem"),
    ]

    operations = [
        migrations.AddField(
            model_name="produto",
            name="exige_lote",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Quando ativo, novas entradas deste produto devem informar um lote. "
                    "O saldo legado continua utilizavel."
                ),
                verbose_name="Exigir lote nas novas entradas",
            ),
        ),
    ]
