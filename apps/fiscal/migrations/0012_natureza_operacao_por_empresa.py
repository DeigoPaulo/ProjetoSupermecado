from django.db import migrations, models
import django.db.models.deletion


def separar_naturezas_por_empresa(apps, schema_editor):
    Empresa = apps.get_model("empresas", "Empresa")
    Natureza = apps.get_model("fiscal", "NaturezaOperacao")
    Documento = apps.get_model("fiscal", "DocumentoFiscal")
    empresas = list(Empresa.objects.order_by("pk").values_list("pk", flat=True))

    for natureza in list(Natureza.objects.order_by("pk")):
        if not empresas:
            raise RuntimeError(
                "Existe natureza de operacao sem empresa cadastrada. "
                "Cadastre a empresa antes de aplicar esta migracao."
            )

        empresas_em_uso = list(
            Documento.objects.filter(natureza_operacao_id=natureza.pk)
            .order_by("filial__empresa_id")
            .values_list("filial__empresa_id", flat=True)
            .distinct()
        )
        empresa_principal = empresas_em_uso[0] if empresas_em_uso else empresas[0]
        Natureza.objects.filter(pk=natureza.pk).update(empresa_id=empresa_principal)

        campos = {
            field.name: getattr(natureza, field.name)
            for field in Natureza._meta.concrete_fields
            if field.name not in {"id", "empresa"}
        }
        por_empresa = {empresa_principal: natureza.pk}
        for empresa_id in empresas:
            if empresa_id == empresa_principal:
                continue
            copia = Natureza.objects.create(empresa_id=empresa_id, **campos)
            por_empresa[empresa_id] = copia.pk

        for empresa_id, natureza_id in por_empresa.items():
            Documento.objects.filter(
                natureza_operacao_id=natureza.pk,
                filial__empresa_id=empresa_id,
            ).update(natureza_operacao_id=natureza_id)


def reunir_naturezas_globais(apps, schema_editor):
    Natureza = apps.get_model("fiscal", "NaturezaOperacao")
    Documento = apps.get_model("fiscal", "DocumentoFiscal")
    descricoes = Natureza.objects.order_by("pk").values_list("descricao", flat=True).distinct()
    for descricao in descricoes:
        naturezas = list(Natureza.objects.filter(descricao=descricao).order_by("pk"))
        if not naturezas:
            continue
        principal = naturezas[0]
        ids_duplicados = [natureza.pk for natureza in naturezas[1:]]
        if ids_duplicados:
            Documento.objects.filter(natureza_operacao_id__in=ids_duplicados).update(
                natureza_operacao_id=principal.pk
            )
            Natureza.objects.filter(pk__in=ids_duplicados).delete()
        Natureza.objects.filter(pk=principal.pk).update(empresa_id=None)


class Migration(migrations.Migration):
    dependencies = [
        ("empresas", "0015_alter_empresa_modo_implantacao"),
        ("fiscal", "0011_naturezaoperacao_ipi_compoe_base_icms_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="naturezaoperacao",
            name="descricao",
            field=models.CharField(max_length=120),
        ),
        migrations.AddField(
            model_name="naturezaoperacao",
            name="empresa",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="naturezas_operacao",
                to="empresas.empresa",
            ),
        ),
        migrations.RunPython(separar_naturezas_por_empresa, reunir_naturezas_globais),
        migrations.AlterField(
            model_name="naturezaoperacao",
            name="empresa",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="naturezas_operacao",
                to="empresas.empresa",
            ),
        ),
        migrations.AddConstraint(
            model_name="naturezaoperacao",
            constraint=models.UniqueConstraint(
                fields=("empresa", "tipo_documento", "descricao"),
                name="fiscal_nat_empresa_tipo_descricao_uniq",
            ),
        ),
        migrations.AlterModelOptions(
            name="naturezaoperacao",
            options={"ordering": ["empresa__nome_fantasia", "descricao"]},
        ),
    ]
