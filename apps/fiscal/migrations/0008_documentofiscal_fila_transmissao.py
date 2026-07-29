from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("fiscal", "0007_configuracaofiscal_urls_nfce")]

    operations = [
        migrations.AddField(
            model_name="documentofiscal",
            name="proxima_tentativa_em",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="documentofiscal",
            name="transmissao_reservada_em",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]