from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("empresas", "0005_eventoentradasincronizacao")]

    operations = [
        migrations.AlterField(
            model_name="eventoentradasincronizacao",
            name="status",
            field=models.CharField(
                choices=[
                    ("RECEBIDO", "Recebido"),
                    ("PROCESSADO", "Processado"),
                    ("CONFLITO", "Conflito"),
                    ("ERRO", "Erro"),
                ],
                default="RECEBIDO",
                max_length=20,
            ),
        ),
    ]
