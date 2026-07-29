from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fiscal", "0004_documentofiscal_pedido_online"),
    ]

    operations = [
        migrations.AddField(
            model_name="configuracaofiscal",
            name="permite_contingencia_offline",
            field=models.BooleanField(
                default=False,
                help_text="Habilite somente quando a UF e a situacao operacional permitirem a contingencia offline.",
                verbose_name="Permite contingencia offline NFC-e",
            ),
        ),
        migrations.AddField(
            model_name="documentofiscal",
            name="contingencia_iniciada_em",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="documentofiscal",
            name="contingencia_justificativa",
            field=models.CharField(blank=True, max_length=256),
        ),
        migrations.AddField(
            model_name="documentofiscal",
            name="tentativas_transmissao",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="documentofiscal",
            name="transmissao_limite_em",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="documentofiscal",
            name="ultima_tentativa_em",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="documentofiscal",
            name="status",
            field=models.CharField(
                choices=[
                    ("RASCUNHO", "Rascunho"),
                    ("PRONTO", "Pronto para transmissao"),
                    ("EMITIDO", "Emitido"),
                    ("REJEITADO", "Rejeitado"),
                    ("CONTINGENCIA", "Contingencia offline"),
                    ("CANCELADO", "Cancelado"),
                    ("INUTILIZADO", "Inutilizado"),
                ],
                default="RASCUNHO",
                max_length=20,
            ),
        ),
    ]
