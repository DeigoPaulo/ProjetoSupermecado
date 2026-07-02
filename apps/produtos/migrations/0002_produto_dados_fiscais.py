from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("produtos", "0001_initial"),
    ]

    operations = [
        migrations.AddField(model_name="produto", name="ncm", field=models.CharField(blank=True, max_length=8, verbose_name="NCM")),
        migrations.AddField(model_name="produto", name="cest", field=models.CharField(blank=True, max_length=7, verbose_name="CEST")),
        migrations.AddField(
            model_name="produto",
            name="origem_mercadoria",
            field=models.CharField(
                blank=True,
                choices=[
                    ("0", "0 - Nacional"),
                    ("1", "1 - Estrangeira, importacao direta"),
                    ("2", "2 - Estrangeira, adquirida no mercado interno"),
                    ("3", "3 - Nacional, conteudo importado superior a 40%"),
                    ("4", "4 - Nacional, processos produtivos basicos"),
                    ("5", "5 - Nacional, conteudo importado ate 40%"),
                    ("6", "6 - Estrangeira, sem similar nacional"),
                    ("7", "7 - Estrangeira interna, sem similar nacional"),
                    ("8", "8 - Nacional, conteudo importado superior a 70%"),
                ],
                max_length=1,
            ),
        ),
        migrations.AddField(model_name="produto", name="cst_icms", field=models.CharField(blank=True, max_length=2, verbose_name="CST ICMS")),
        migrations.AddField(model_name="produto", name="csosn", field=models.CharField(blank=True, max_length=3, verbose_name="CSOSN")),
        migrations.AddField(
            model_name="produto",
            name="aliquota_icms",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True, verbose_name="Aliquota ICMS (%)"),
        ),
    ]
