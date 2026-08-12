from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("configuracoes", "0008_alter_configuracaoimpressao_tipo_documento_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("empresas", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="HomologacaoOperacional",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nome", models.CharField(default="Roteiro de homologação operacional", max_length=120)),
                ("etapas_concluidas", models.JSONField(blank=True, default=list)),
                ("observacoes", models.TextField(blank=True)),
                ("criada_em", models.DateTimeField(auto_now_add=True)),
                ("atualizada_em", models.DateTimeField(auto_now=True)),
                ("empresa", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="homologacoes_operacionais", to="empresas.empresa")),
                ("filial", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="homologacoes_operacionais", to="empresas.filial")),
                ("responsavel", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="homologacoes_operacionais", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-atualizada_em", "-pk"]},
        ),
        migrations.AddConstraint(
            model_name="homologacaooperacional",
            constraint=models.UniqueConstraint(fields=("filial", "nome"), name="config_homologacao_operacional_filial_nome"),
        ),
    ]