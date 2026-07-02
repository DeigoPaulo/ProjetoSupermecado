from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("vendas", "0003_devolucaovenda_itemdevolucaovenda"),
    ]

    operations = [
        migrations.AlterField(
            model_name="pagamentovenda",
            name="status",
            field=models.CharField(
                choices=[
                    ("PENDENTE", "Pendente"),
                    ("CONFIRMADO", "Confirmado"),
                    ("RECUSADO", "Recusado"),
                    ("ESTORNADO", "Estornado"),
                ],
                default="CONFIRMADO",
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name="pagamentovenda",
            name="transacao_externa_id",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="pagamentovenda",
            name="nsu",
            field=models.CharField(blank=True, max_length=60),
        ),
        migrations.AddField(
            model_name="pagamentovenda",
            name="codigo_autorizacao",
            field=models.CharField(blank=True, max_length=60),
        ),
        migrations.AddField(
            model_name="pagamentovenda",
            name="mensagem_processadora",
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
