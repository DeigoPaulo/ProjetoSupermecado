from django.db import migrations


def corrigir_nome_maca(apps, schema_editor):
    Produto = apps.get_model("produtos", "Produto")
    Produto.objects.filter(nome="MAÇĂ").update(nome="MAÇÃ")


class Migration(migrations.Migration):
    dependencies = [
        ("produtos", "0005_produto_exige_lote"),
    ]

    operations = [
        migrations.RunPython(corrigir_nome_maca, migrations.RunPython.noop),
    ]
