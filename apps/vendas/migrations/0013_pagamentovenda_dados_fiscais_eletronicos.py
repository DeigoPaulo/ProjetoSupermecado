from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("vendas", "0012_alter_venda_documento_consumidor_tipo"),
    ]

    operations = [
        migrations.AlterField(
            model_name="pagamentovenda",
            name="codigo_autorizacao",
            field=models.CharField(blank=True, max_length=128),
        ),
        migrations.AddField(
            model_name="pagamentovenda",
            name="tipo_integracao",
            field=models.CharField(
                blank=True,
                choices=[
                    ("1", "Integrado ao sistema de automação"),
                    ("2", "Não integrado ao sistema de automação"),
                ],
                max_length=1,
            ),
        ),
        migrations.AddField(
            model_name="pagamentovenda",
            name="cnpj_instituicao_pagamento",
            field=models.CharField(blank=True, max_length=14),
        ),
        migrations.AddField(
            model_name="pagamentovenda",
            name="bandeira_cartao",
            field=models.CharField(blank=True, max_length=2),
        ),
        migrations.AddField(
            model_name="pagamentovenda",
            name="cnpj_beneficiario_pagamento",
            field=models.CharField(blank=True, max_length=14),
        ),
        migrations.AddField(
            model_name="pagamentovenda",
            name="identificador_terminal_pagamento",
            field=models.CharField(blank=True, max_length=40),
        ),
    ]
