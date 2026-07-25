from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("empresas", "0011_empresa_politica_conflito_sincronizacao"),
        ("estoque", "0018_alertaslaordemproducao"),
        ("produtos", "0004_alter_produto_imagem_alter_produtoimagem_imagem"),
    ]

    operations = [
        migrations.CreateModel(
            name="LoteEstoque",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("codigo", models.CharField(max_length=60)),
                ("fabricacao", models.DateField(blank=True, null=True)),
                ("validade", models.DateField(blank=True, null=True)),
                ("quantidade_inicial", models.DecimalField(decimal_places=3, max_digits=12)),
                ("quantidade_atual", models.DecimalField(decimal_places=3, max_digits=12)),
                ("custo_unitario", models.DecimalField(decimal_places=2, max_digits=10)),
                ("origem_referencia", models.CharField(blank=True, max_length=120)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("filial", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="lotes_estoque", to="empresas.filial")),
                ("produto", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="lotes_estoque", to="produtos.produto")),
            ],
            options={
                "ordering": [models.OrderBy(models.F("validade"), nulls_last=True), "criado_em", "id"],
            },
        ),
        migrations.CreateModel(
            name="MovimentacaoLoteEstoque",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("quantidade", models.DecimalField(decimal_places=3, max_digits=12)),
                ("custo_unitario", models.DecimalField(decimal_places=2, max_digits=10)),
                ("lote", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="movimentacoes_lote", to="estoque.loteestoque")),
                ("movimentacao", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="alocacoes_lote", to="estoque.movimentacaoestoque")),
            ],
            options={"ordering": ["id"]},
        ),
        migrations.AddIndex(
            model_name="loteestoque",
            index=models.Index(fields=["produto", "filial", "codigo"], name="est_lote_prod_fil_cod_idx"),
        ),
        migrations.AddIndex(
            model_name="loteestoque",
            index=models.Index(fields=["validade", "quantidade_atual"], name="est_lote_val_saldo_idx"),
        ),
    ]
