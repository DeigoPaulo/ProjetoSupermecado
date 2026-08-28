import json

from django.core.management.base import BaseCommand, CommandError

from apps.configuracoes.post_deployment import diagnostico_pos_implantacao_local


class Command(BaseCommand):
    help = "Valida o servidor local após a instalação."

    def add_arguments(self, parser):
        parser.add_argument("--url")
        parser.add_argument("--timeout", type=int, default=5)
        parser.add_argument(
            "--backup-max-horas",
            type=int,
            help="Substitui explicitamente LOCAL_BACKUP_MAX_AGE_HOURS nesta execução.",
        )
        parser.add_argument("--json", action="store_true", dest="como_json")
        parser.add_argument("--estrito", action="store_true")

    def handle(self, *args, **options):
        diagnostico = diagnostico_pos_implantacao_local(
            url=options["url"],
            timeout=max(1, min(options["timeout"], 30)),
            idade_maxima_backup_horas=(
                max(1, options["backup_max_horas"])
                if options["backup_max_horas"] is not None
                else None
            ),
        )
        if options["como_json"]:
            self.stdout.write(json.dumps(diagnostico, ensure_ascii=False, sort_keys=True))
        else:
            estado = "PRONTO" if diagnostico["pronto"] else "BLOQUEADO"
            self.stdout.write(f"Pós-implantação do servidor local: {estado}")
            for item in diagnostico["verificacoes"]:
                self.stdout.write(f"- {item['id']}: {'OK' if item['pronta'] else 'PENDENTE'}")
            for bloqueio in diagnostico["bloqueios"]:
                self.stdout.write(f"  BLOQUEIO: {bloqueio}")
        if options["estrito"] and not diagnostico["pronto"]:
            raise CommandError("A instalação local não passou no aceite técnico.")
