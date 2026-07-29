from django.db import migrations


def atribuir_empresa_clientes(apps, schema_editor):
    Cliente = apps.get_model("clientes", "Cliente")
    Empresa = apps.get_model("empresas", "Empresa")
    Venda = apps.get_model("vendas", "Venda")
    PreVenda = apps.get_model("vendas", "PreVenda")
    ContaFinanceira = apps.get_model("financeiro", "ContaFinanceira")
    PedidoOnline = apps.get_model("marketplace", "PedidoOnline")

    empresas = list(Empresa.objects.values_list("pk", flat=True)[:2])
    empresa_unica_id = empresas[0] if len(empresas) == 1 else None

    for cliente in Cliente.objects.filter(empresa__isnull=True).iterator():
        empresa_ids = set(
            Venda.objects.filter(cliente_id=cliente.pk).values_list("filial__empresa_id", flat=True)
        )
        empresa_ids.update(
            PreVenda.objects.filter(cliente_id=cliente.pk).values_list("filial__empresa_id", flat=True)
        )
        empresa_ids.update(
            ContaFinanceira.objects.filter(cliente_id=cliente.pk).values_list("filial__empresa_id", flat=True)
        )
        empresa_ids.update(
            PedidoOnline.objects.filter(cliente_id=cliente.pk).values_list("filial__empresa_id", flat=True)
        )
        empresa_ids.discard(None)
        empresa_id = next(iter(empresa_ids)) if len(empresa_ids) == 1 else empresa_unica_id if not empresa_ids else None
        if empresa_id:
            Cliente.objects.filter(pk=cliente.pk).update(empresa_id=empresa_id)


def desfazer_atribuicao(apps, schema_editor):
    Cliente = apps.get_model("clientes", "Cliente")
    Cliente.objects.update(empresa_id=None)


class Migration(migrations.Migration):
    dependencies = [
        ("clientes", "0002_cliente_por_empresa"),
        ("vendas", "0009_formas_pagamento_voucher"),
        ("financeiro", "0007_conciliacaolancamentofinanceiro"),
        ("marketplace", "0005_pedidoonline_documento_cliente_and_more"),
    ]

    operations = [
        migrations.RunPython(atribuir_empresa_clientes, desfazer_atribuicao),
    ]