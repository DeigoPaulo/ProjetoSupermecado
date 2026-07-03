from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("pdv", "0004_terminalpdv")]

    operations = [
        migrations.AddField(
            model_name="terminalpdv",
            name="chave_api_hash",
            field=models.CharField(blank=True, editable=False, max_length=128),
        ),
        migrations.AddField(
            model_name="terminalpdv",
            name="chave_api_prefixo",
            field=models.CharField(blank=True, editable=False, max_length=12),
        ),
    ]
