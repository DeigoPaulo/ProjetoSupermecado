from django.db import migrations, models
from django.db.models import F, Q


def validar_contas_existentes(apps, schema_editor):
    ContaFinanceira = apps.get_model("financeiro", "ContaFinanceira")
    inconsistentes = ContaFinanceira.objects.filter(
        Q(status="PAGA")
        & (Q(data_pagamento__isnull=True) | Q(valor_pago__isnull=True) | ~Q(valor_pago=F("valor")))
        | Q(status__in=["ABERTA", "CANCELADA"])
        & (Q(data_pagamento__isnull=False) | Q(valor_pago__isnull=False))
    )
    if inconsistentes.exists():
        ids = list(inconsistentes.order_by("pk").values_list("pk", flat=True)[:20])
        raise RuntimeError(
            "Existem contas financeiras incompatíveis com a baixa integral segura. "
            f"Corrija os registros antes de aplicar a migração. IDs iniciais: {ids}"
        )


class Migration(migrations.Migration):
    dependencies = [("financeiro", "0022_aceiteamostracontabil")]

    operations = [
        migrations.RunPython(validar_contas_existentes, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="contafinanceira",
            constraint=models.CheckConstraint(
                condition=(
                    Q(status="PAGA", data_pagamento__isnull=False, valor_pago=F("valor"))
                    | Q(
                        status__in=["ABERTA", "CANCELADA"],
                        data_pagamento__isnull=True,
                        valor_pago__isnull=True,
                    )
                ),
                name="financeiro_conta_baixa_integral_coerente",
            ),
        ),
    ]
