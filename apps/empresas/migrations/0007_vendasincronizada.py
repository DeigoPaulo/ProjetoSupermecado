import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("empresas", "0006_alter_eventoentradasincronizacao_status")]

    operations = [
        migrations.CreateModel(
            name="VendaSincronizada",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("venda_externa_id", models.CharField(max_length=120)),
                ("caixa_externo", models.CharField(blank=True, max_length=80)),
                ("operador", models.CharField(blank=True, max_length=120)),
                ("cliente", models.CharField(blank=True, max_length=180)),
                ("total_bruto", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("desconto", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("total_liquido", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("itens", models.JSONField(default=list)),
                ("pagamentos", models.JSONField(default=list)),
                ("realizada_em", models.DateTimeField(blank=True, null=True)),
                ("recebida_em", models.DateTimeField(auto_now_add=True)),
                ("atualizada_em", models.DateTimeField(auto_now=True)),
                ("empresa", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="vendas_sincronizadas", to="empresas.empresa")),
                ("evento", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="venda_sincronizada", to="empresas.eventoentradasincronizacao")),
                ("filial", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="vendas_sincronizadas", to="empresas.filial")),
            ],
            options={"ordering": ["-realizada_em", "-recebida_em"]},
        ),
        migrations.AddConstraint(
            model_name="vendasincronizada",
            constraint=models.UniqueConstraint(fields=("empresa", "venda_externa_id"), name="empresas_venda_sync_unica"),
        ),
    ]
