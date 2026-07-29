import json

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.fiscal.fila import processar_fila_fiscal


class Command(BaseCommand):
    help = "Processa a fila de transmissao fiscal com lease, limite e retentativa exponencial."

    def add_arguments(self, parser):
        parser.add_argument("--limite", type=int, default=50)
        parser.add_argument("--simular-homologacao", action="store_true")
        parser.add_argument("--forcar", action="store_true")

    def handle(self, *args, **options):
        try:
            resumo = processar_fila_fiscal(
                limite=options["limite"],
                simular_homologacao=options["simular_homologacao"],
                forcar=options["forcar"],
            )
        except ValidationError as exc:
            raise CommandError(" ".join(exc.messages)) from exc
        self.stdout.write(json.dumps(resumo, ensure_ascii=False, sort_keys=True))