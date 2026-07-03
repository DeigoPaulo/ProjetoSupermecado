from django.core.management.base import BaseCommand

from apps.empresas.services_eventos_entrada import processar_entrada_sincronizacao


class Command(BaseCommand):
    help = "Processa eventos recebidos da sincronizacao antes de aplicar nos dominios."

    def add_arguments(self, parser):
        parser.add_argument("--limite", type=int, default=50)

    def handle(self, *args, **options):
        resultado = processar_entrada_sincronizacao(limite=max(1, options["limite"]))
        self.stdout.write(
            self.style.SUCCESS(
                "Entrada de sincronizacao processada: "
                f"{resultado['processados']} processado(s), {resultado['erros']} erro(s)."
            )
        )
