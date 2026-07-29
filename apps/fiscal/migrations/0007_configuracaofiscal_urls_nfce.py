from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("fiscal", "0006_documentofiscal_certificado_serial_assinatura_and_more")]

    operations = [
        migrations.AddField(
            model_name="configuracaofiscal",
            name="url_consulta_nfce",
            field=models.URLField(blank=True, help_text="Pagina oficial de consulta da chave de acesso na SEFAZ.", max_length=500, verbose_name="URL de consulta NFC-e"),
        ),
        migrations.AddField(
            model_name="configuracaofiscal",
            name="url_qrcode_nfce",
            field=models.URLField(blank=True, help_text="Endpoint oficial da SEFAZ para o QR Code, conforme a UF e o ambiente.", max_length=500, verbose_name="URL do QR Code NFC-e"),
        ),
    ]