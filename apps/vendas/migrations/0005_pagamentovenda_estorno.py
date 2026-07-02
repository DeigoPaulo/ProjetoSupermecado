from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("vendas", "0004_pagamentovenda_dados_tef"),
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
                    ("ESTORNO_PENDENTE", "Estorno pendente"),
                    ("ESTORNADO", "Estornado"),
                ],
                default="CONFIRMADO",
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name="pagamentovenda",
            name="motivo_estorno",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="pagamentovenda",
            name="estorno_solicitado_em",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="pagamentovenda",
            name="estornado_em",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
