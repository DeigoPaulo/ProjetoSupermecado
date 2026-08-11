from django.db import migrations


def _somente_digitos(valor):
    return "".join(caractere for caractere in (valor or "") if caractere.isdigit())


def criar_filiais_matriz_ausentes(apps, schema_editor):
    Empresa = apps.get_model("empresas", "Empresa")
    Filial = apps.get_model("empresas", "Filial")

    for empresa in Empresa.objects.all().iterator():
        filiais = list(Filial.objects.filter(empresa_id=empresa.pk, deleted_at__isnull=True))
        cnpj_empresa = _somente_digitos(empresa.cnpj)
        matriz = next(
            (filial for filial in filiais if cnpj_empresa and _somente_digitos(filial.cnpj) == cnpj_empresa),
            None,
        )
        if matriz is None:
            matriz = next((filial for filial in filiais if "matriz" in filial.nome.casefold()), None)
        if matriz is not None:
            if not matriz.cnpj and empresa.cnpj:
                matriz.cnpj = empresa.cnpj
                matriz.save(update_fields=["cnpj"])
            continue

        nome = "Matriz"
        sequencia = 2
        nomes_existentes = {filial.nome.casefold() for filial in filiais}
        while nome.casefold() in nomes_existentes:
            nome = f"Matriz {sequencia}"
            sequencia += 1

        Filial.objects.create(
            empresa_id=empresa.pk,
            nome=nome,
            cnpj=empresa.cnpj,
            telefone=empresa.telefone,
            cep=empresa.cep,
            logradouro=empresa.logradouro,
            numero=empresa.numero,
            complemento=empresa.complemento,
            bairro=empresa.bairro,
            endereco=empresa.endereco,
            municipio=empresa.municipio,
            uf=empresa.uf,
            is_active=empresa.is_active,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("empresas", "0019_alter_empresa_sincronizacao_automatica"),
    ]

    operations = [
        migrations.RunPython(criar_filiais_matriz_ausentes, migrations.RunPython.noop),
    ]