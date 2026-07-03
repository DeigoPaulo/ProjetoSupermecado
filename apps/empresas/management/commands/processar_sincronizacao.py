from django.core.management.base import BaseCommand

from apps.empresas.services_sincronizacao import processar_fila


class Command(BaseCommand):
    help = "Processa um lote da fila local de sincronizacao com a nuvem."

    def add_arguments(self, parser):
        parser.add_argument("--limite", type=int, default=50)

    def handle(self, *args, **options):
        resultado = processar_fila(limite=max(1, options["limite"]))
        self.stdout.write(
            self.style.SUCCESS(
                f"Sincronizacao processada: {resultado['enviados']} enviado(s), {resultado['erros']} erro(s)."
            )
        )
