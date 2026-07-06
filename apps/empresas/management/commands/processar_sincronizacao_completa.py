from django.core.management.base import BaseCommand

from apps.empresas.services_eventos_entrada import processar_entrada_sincronizacao
from apps.empresas.services_sincronizacao import processar_fila


class Command(BaseCommand):
    help = "Processa saida e entrada da sincronizacao em uma unica execucao agendavel."

    def add_arguments(self, parser):
        parser.add_argument("--limite-saida", type=int, default=50)
        parser.add_argument("--limite-entrada", type=int, default=50)
        parser.add_argument(
            "--entrada-primeiro",
            action="store_true",
            help="Processa primeiro os eventos recebidos antes de enviar a fila local.",
        )

    def handle(self, *args, **options):
        limite_saida = max(1, options["limite_saida"])
        limite_entrada = max(1, options["limite_entrada"])
        if options["entrada_primeiro"]:
            entrada = processar_entrada_sincronizacao(limite=limite_entrada)
            saida = processar_fila(limite=limite_saida)
        else:
            saida = processar_fila(limite=limite_saida)
            entrada = processar_entrada_sincronizacao(limite=limite_entrada)

        self.stdout.write(
            self.style.SUCCESS(
                "Sincronizacao completa: "
                f"{saida['enviados']} enviado(s), {saida['erros']} erro(s) de saida; "
                f"{entrada['processados']} entrada(s) processada(s), {entrada['erros']} erro(s) de entrada."
            )
        )
