from django.db import migrations


def criar_formas_voucher(apps, schema_editor):
    FormaPagamento = apps.get_model("vendas", "FormaPagamento")
    formas = (
        ("VALE_ALIMENTACAO", "Vale alimentacao"),
        ("VALE_REFEICAO", "Vale refeicao"),
    )
    for tipo, nome in formas:
        if not FormaPagamento.objects.filter(tipo=tipo).exists():
            FormaPagamento.objects.create(
                nome=nome,
                tipo=tipo,
                ativo=True,
                permite_troco=False,
                exige_autorizacao=False,
            )


class Migration(migrations.Migration):
    dependencies = [("vendas", "0008_estornoparcialpagamento")]

    operations = [migrations.RunPython(criar_formas_voucher, migrations.RunPython.noop)]