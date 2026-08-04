from django.db import migrations, models
import django.db.models.deletion


def vincular_categorias(apps, schema_editor):
    Categoria = apps.get_model("financeiro", "CategoriaFinanceira")
    Conta = apps.get_model("financeiro", "ContaFinanceira")
    Empresa = apps.get_model("empresas", "Empresa")
    fallback = Empresa.objects.order_by("id").first()
    for categoria in Categoria.objects.all():
        empresas = list(Conta.objects.filter(categoria_id=categoria.id).values_list("filial__empresa_id", flat=True).distinct())
        if not empresas and fallback:
            categoria.empresa_id = fallback.id
            categoria.save(update_fields=["empresa"])
            continue
        for index, empresa_id in enumerate(empresas):
            alvo = categoria if index == 0 else Categoria.objects.create(nome=categoria.nome, tipo=categoria.tipo, is_active=categoria.is_active)
            alvo.empresa_id = empresa_id
            alvo.save(update_fields=["empresa"])
            Conta.objects.filter(categoria_id=categoria.id, filial__empresa_id=empresa_id).update(categoria_id=alvo.id)


class Migration(migrations.Migration):
    dependencies = [("financeiro", "0008_exportacaocontabil")]
    operations = [
        migrations.AddField(model_name="categoriafinanceira", name="empresa", field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name="categorias_financeiras", to="empresas.empresa")),
        migrations.RunPython(vincular_categorias, migrations.RunPython.noop),
        migrations.AlterField(model_name="categoriafinanceira", name="empresa", field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="categorias_financeiras", to="empresas.empresa")),
        migrations.AlterField(model_name="categoriafinanceira", name="nome", field=models.CharField(max_length=120)),
        migrations.AddConstraint(model_name="categoriafinanceira", constraint=models.UniqueConstraint(fields=("empresa", "nome"), name="financeiro_categoria_unica_por_empresa")),
    ]
