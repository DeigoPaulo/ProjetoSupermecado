import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("empresas", "0003_empresa_modo_implantacao_and_more")]

    operations = [
        migrations.CreateModel(
            name="EventoSincronizacao",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("identificador", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("tipo", models.CharField(max_length=100)),
                ("objeto_tipo", models.CharField(max_length=100)),
                ("objeto_id", models.CharField(max_length=80)),
                ("chave_idempotencia", models.CharField(max_length=180, unique=True)),
                ("payload", models.JSONField(default=dict)),
                ("status", models.CharField(choices=[("PENDENTE", "Pendente"), ("PROCESSANDO", "Processando"), ("ENVIADO", "Enviado"), ("ERRO", "Erro")], default="PENDENTE", max_length=20)),
                ("tentativas", models.PositiveIntegerField(default=0)),
                ("proxima_tentativa_em", models.DateTimeField(blank=True, null=True)),
                ("ultimo_erro", models.TextField(blank=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("processado_em", models.DateTimeField(blank=True, null=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("empresa", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="eventos_sincronizacao", to="empresas.empresa")),
                ("filial", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="eventos_sincronizacao", to="empresas.filial")),
            ],
            options={"ordering": ["criado_em"]},
        ),
        migrations.AddIndex(model_name="eventosincronizacao", index=models.Index(fields=["status", "proxima_tentativa_em"], name="empresas_ev_status_3e6760_idx")),
        migrations.AddIndex(model_name="eventosincronizacao", index=models.Index(fields=["empresa", "criado_em"], name="empresas_ev_empresa_a7567c_idx")),
    ]
