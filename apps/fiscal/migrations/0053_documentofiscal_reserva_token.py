from django.db import migrations, models
from django.db.models import Q


def validar_reservas_existentes(apps, schema_editor):
    DocumentoFiscal = apps.get_model("fiscal", "DocumentoFiscal")
    inconsistentes = DocumentoFiscal.objects.filter(
        Q(transmissao_reservada_em__isnull=True, transmissao_reserva_token__isnull=False)
        | Q(transmissao_reservada_em__isnull=False, transmissao_reserva_token__isnull=True)
    )
    if inconsistentes.exists():
        ids = list(inconsistentes.order_by("pk").values_list("pk", flat=True)[:20])
        raise RuntimeError(
            "Existem reservas fiscais legadas sem identidade verificável. "
            f"Interrompa os processadores e libere conscientemente essas reservas. IDs iniciais: {ids}"
        )


class Migration(migrations.Migration):
    dependencies = [("fiscal", "0052_seriefiscal_ambiente")]

    operations = [
        migrations.AddField(
            model_name="documentofiscal",
            name="transmissao_reserva_token",
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.RunPython(validar_reservas_existentes, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="documentofiscal",
            constraint=models.CheckConstraint(
                condition=(
                    Q(transmissao_reservada_em__isnull=True, transmissao_reserva_token__isnull=True)
                    | Q(transmissao_reservada_em__isnull=False, transmissao_reserva_token__isnull=False)
                ),
                name="fisc_doc_reserva_transmissao_coerente",
            ),
        ),
    ]
