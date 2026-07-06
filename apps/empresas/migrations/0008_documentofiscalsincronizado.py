import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("empresas", "0007_vendasincronizada")]

    operations = [
        migrations.CreateModel(
            name="DocumentoFiscalSincronizado",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("documento_externo_id", models.CharField(max_length=120)),
                ("venda_externa_id", models.CharField(blank=True, max_length=120)),
                ("tipo_documento", models.CharField(default="NFCE", max_length=20)),
                ("ambiente", models.CharField(blank=True, max_length=20)),
                ("serie", models.CharField(blank=True, max_length=20)),
                ("numero", models.CharField(blank=True, max_length=30)),
                ("chave_acesso", models.CharField(blank=True, max_length=80)),
                ("protocolo", models.CharField(blank=True, max_length=80)),
                ("status", models.CharField(blank=True, max_length=30)),
                ("valor_total", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("emitido_em", models.DateTimeField(blank=True, null=True)),
                ("payload", models.JSONField(default=dict)),
                ("recebido_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("empresa", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="documentos_fiscais_sincronizados", to="empresas.empresa")),
                ("evento", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="documento_fiscal_sincronizado", to="empresas.eventoentradasincronizacao")),
                ("filial", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="documentos_fiscais_sincronizados", to="empresas.filial")),
            ],
            options={"ordering": ["-emitido_em", "-recebido_em"]},
        ),
        migrations.AddConstraint(
            model_name="documentofiscalsincronizado",
            constraint=models.UniqueConstraint(fields=("empresa", "documento_externo_id"), name="empresas_doc_fiscal_sync_unico"),
        ),
    ]
