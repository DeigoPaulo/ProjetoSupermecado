from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("empresas", "0002_filial_codigo_municipio_ibge_filial_municipio_and_more")]

    operations = [
        migrations.AddField(
            model_name="empresa",
            name="modo_implantacao",
            field=models.CharField(
                choices=[
                    ("LOCAL", "Somente servidor local"),
                    ("HIBRIDO", "Servidor local com sincronizacao em nuvem"),
                    ("NUVEM_AGENTE", "Nuvem com agente local"),
                ],
                default="LOCAL",
                max_length=20,
                verbose_name="Modo de implantacao",
            ),
        ),
        migrations.AddField(
            model_name="empresa",
            name="sincronizacao_automatica",
            field=models.BooleanField(default=False, verbose_name="Sincronizacao automatica"),
        ),
        migrations.AddField(
            model_name="empresa",
            name="url_sincronizacao",
            field=models.URLField(blank=True, verbose_name="URL segura da nuvem"),
        ),
    ]
