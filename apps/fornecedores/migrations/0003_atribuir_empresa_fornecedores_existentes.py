from django.db import migrations


def atribuir_empresa_fornecedores(apps, schema_editor):
    Fornecedor = apps.get_model("fornecedores", "Fornecedor")
    Empresa = apps.get_model("empresas", "Empresa")
    RespostaCotacaoFornecedor = apps.get_model("compras", "RespostaCotacaoFornecedor")
    PedidoCompra = apps.get_model("compras", "PedidoCompra")
    EntradaCompra = apps.get_model("compras", "EntradaCompra")
    ContaFinanceira = apps.get_model("financeiro", "ContaFinanceira")

    empresas = list(Empresa.objects.values_list("pk", flat=True)[:2])
    empresa_unica_id = empresas[0] if len(empresas) == 1 else None

    for fornecedor in Fornecedor.objects.filter(empresa__isnull=True).iterator():
        empresa_ids = set(
            RespostaCotacaoFornecedor.objects.filter(fornecedor_id=fornecedor.pk).values_list(
                "cotacao__filial__empresa_id", flat=True
            )
        )
        empresa_ids.update(
            PedidoCompra.objects.filter(fornecedor_id=fornecedor.pk).values_list("filial__empresa_id", flat=True)
        )
        empresa_ids.update(
            EntradaCompra.objects.filter(fornecedor_id=fornecedor.pk).values_list("filial__empresa_id", flat=True)
        )
        empresa_ids.update(
            ContaFinanceira.objects.filter(fornecedor_id=fornecedor.pk).values_list("filial__empresa_id", flat=True)
        )
        empresa_ids.discard(None)
        empresa_id = next(iter(empresa_ids)) if len(empresa_ids) == 1 else empresa_unica_id if not empresa_ids else None
        if empresa_id:
            Fornecedor.objects.filter(pk=fornecedor.pk).update(empresa_id=empresa_id)


def desfazer_atribuicao(apps, schema_editor):
    Fornecedor = apps.get_model("fornecedores", "Fornecedor")
    Fornecedor.objects.update(empresa_id=None)


class Migration(migrations.Migration):
    dependencies = [
        ("fornecedores", "0002_alter_fornecedor_options_fornecedor_empresa_and_more"),
        ("compras", "0007_itementradacompra_lote"),
        ("financeiro", "0007_conciliacaolancamentofinanceiro"),
    ]

    operations = [
        migrations.RunPython(atribuir_empresa_fornecedores, desfazer_atribuicao),
    ]