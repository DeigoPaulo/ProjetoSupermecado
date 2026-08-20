import json

from django.core.management.base import BaseCommand, CommandError

from apps.fiscal.monitor_atualizacoes import monitorar_atualizacoes_fiscais


class Command(BaseCommand):
    help = "Consulta fontes fiscais oficiais e registra novidades para revisão humana."

    def add_arguments(self, parser):
        parser.add_argument(
            "--forcar",
            action="store_true",
            help="Executa uma consulta manual mesmo com o monitor desabilitado.",
        )
        parser.add_argument(
            "--estrito",
            action="store_true",
            help="Retorna erro quando qualquer fonte oficial falhar.",
        )

    def handle(self, *args, **options):
        resultado = monitorar_atualizacoes_fiscais(forcar=options["forcar"])
        self.stdout.write(json.dumps(resultado, ensure_ascii=False, default=str, indent=2))
        if options["estrito"] and resultado["falhas"]:
            raise CommandError("Uma ou mais fontes fiscais oficiais falharam.")
        if not resultado["habilitado"] and not options["forcar"]:
            self.stdout.write(self.style.WARNING("Monitor fiscal desabilitado no ambiente."))
        else:
            self.stdout.write(self.style.SUCCESS("Consulta fiscal concluída."))
