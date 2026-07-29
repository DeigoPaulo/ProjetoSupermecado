from django.db import migrations


def inicializar_formas_pagamento_filiais(apps, schema_editor):
    Filial = apps.get_model("empresas", "Filial")
    FormaPagamento = apps.get_model("vendas", "FormaPagamento")
    FormaPagamentoFilial = apps.get_model("vendas", "FormaPagamentoFilial")

    forma_ids = list(FormaPagamento.objects.values_list("id", flat=True))
    configuracoes = [
        FormaPagamentoFilial(filial_id=filial_id, forma_pagamento_id=forma_id, ativo=True)
        for filial_id in Filial.objects.values_list("id", flat=True)
        for forma_id in forma_ids
    ]
    FormaPagamentoFilial.objects.bulk_create(configuracoes, ignore_conflicts=True)


class Migration(migrations.Migration):
    dependencies = [
        ("vendas", "0010_formapagamentofilial"),
    ]

    operations = [
        migrations.RunPython(inicializar_formas_pagamento_filiais, migrations.RunPython.noop),
    ]