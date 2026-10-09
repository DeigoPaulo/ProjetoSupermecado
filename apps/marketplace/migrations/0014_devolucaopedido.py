import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("marketplace", "0013_alter_pedidoonline_canal"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="DevolucaoPedido",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("motivo", models.CharField(max_length=255)),
                ("valor_devolvido", models.DecimalField(decimal_places=2, max_digits=12)),
                ("produto_apto_venda", models.BooleanField(default=False)),
                ("devolvido_em", models.DateTimeField(default=django.utils.timezone.now)),
                ("pedido", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="devolucao", to="marketplace.pedidoonline")),
                ("usuario", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
