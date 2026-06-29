from django.core.management.base import BaseCommand

from apps.empresas.models import Empresa, Filial
from apps.produtos.models import Categoria, Marca
from apps.vendas.models import FormaPagamento


class Command(BaseCommand):
    help = "Cria dados iniciais para desenvolvimento do MVP."

    def handle(self, *args, **options):
        empresa, _ = Empresa.objects.get_or_create(
            cnpj="00.000.000/0001-00",
            defaults={
                "razao_social": "Supermercado Modelo Ltda",
                "nome_fantasia": "Supermercado Modelo",
                "telefone": "(00) 0000-0000",
                "email": "contato@supermercado.local",
                "endereco": "Endereco de exemplo",
                "regime_tributario": "Simples Nacional",
            },
        )
        Filial.objects.get_or_create(
            empresa=empresa,
            nome="Loja Matriz",
            defaults={
                "cnpj": empresa.cnpj,
                "telefone": empresa.telefone,
                "endereco": empresa.endereco,
            },
        )

        for nome in [
            "Hortifruti",
            "Acougue",
            "Padaria",
            "Bebidas",
            "Mercearia",
            "Limpeza",
            "Higiene pessoal",
            "Frios e laticinios",
        ]:
            Categoria.all_objects.get_or_create(nome=nome, defaults={"descricao": ""})

        for nome in ["Marca propria", "Sem marca", "Fornecedor local"]:
            Marca.all_objects.get_or_create(nome=nome)

        formas = [
            ("Dinheiro", "DINHEIRO", True, False),
            ("Pix", "PIX", False, False),
            ("Cartao de debito", "DEBITO", False, True),
            ("Cartao de credito", "CREDITO", False, True),
        ]
        for nome, tipo, permite_troco, exige_autorizacao in formas:
            FormaPagamento.objects.get_or_create(
                nome=nome,
                defaults={
                    "tipo": tipo,
                    "permite_troco": permite_troco,
                    "exige_autorizacao": exige_autorizacao,
                },
            )

        self.stdout.write(self.style.SUCCESS("Dados iniciais criados/atualizados."))
