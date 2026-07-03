from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("empresas", "0004_eventosincronizacao")]

    operations = [
        migrations.CreateModel(
            name="EventoEntradaSincronizacao",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("identificador", models.UUIDField(editable=False, unique=True)),
                ("chave_idempotencia", models.CharField(max_length=180, unique=True)),
                ("tipo", models.CharField(max_length=100)),
                ("payload", models.JSONField(default=dict)),
                ("status", models.CharField(choices=[("RECEBIDO", "Recebido"), ("PROCESSADO", "Processado"), ("ERRO", "Erro")], default="RECEBIDO", max_length=20)),
                ("ultimo_erro", models.TextField(blank=True)),
                ("recebido_em", models.DateTimeField(auto_now_add=True)),
                ("processado_em", models.DateTimeField(blank=True, null=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("empresa", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="eventos_entrada_sincronizacao", to="empresas.empresa")),
            ],
            options={"ordering": ["recebido_em"]},
        ),
        migrations.AddIndex(model_name="eventoentradasincronizacao", index=models.Index(fields=["status", "recebido_em"], name="empresas_in_status_entrada_idx")),
    ]
