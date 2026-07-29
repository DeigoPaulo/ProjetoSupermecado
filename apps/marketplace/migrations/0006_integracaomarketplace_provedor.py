from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("marketplace", "0005_pedidoonline_documento_cliente_and_more")]

    operations = [
        migrations.AddField(
            model_name="integracaomarketplace",
            name="provedor",
            field=models.CharField(
                choices=[
                    ("PADRAO", "Contrato padrao"),
                    ("IFOOD", "iFood"),
                    ("RAPPI", "Rappi"),
                    ("MERCADO_LIVRE", "Mercado Livre"),
                    ("SITE_PROPRIO", "Site proprio"),
                    ("OUTRO", "Outro parceiro"),
                ],
                default="PADRAO",
                max_length=30,
            ),
        ),
    ]
