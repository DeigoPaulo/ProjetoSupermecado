import json

from django.core.management.base import BaseCommand, CommandError

from apps.estoque.verificador_artefatos_piloto import (
    carregar_artefato_json,
    verificar_integridade_artefatos_piloto,
)


class Command(BaseCommand):
    help = "Confere offline a integridade e o vínculo da ficha e do relatório do piloto."

    def add_arguments(self, parser):
        parser.add_argument("--ficha", required=True)
        parser.add_argument("--relatorio", required=True)
        parser.add_argument("--estrito", action="store_true")

    def handle(self, *args, **options):
        try:
            resultado = verificar_integridade_artefatos_piloto(
                ficha=carregar_artefato_json(options["ficha"]),
                relatorio=carregar_artefato_json(options["relatorio"]),
            )
        except Exception as exc:
            raise CommandError(
                f"Não foi possível conferir os artefatos ({exc.__class__.__name__})."
            ) from None
        self.stdout.write(json.dumps(resultado, ensure_ascii=False, sort_keys=True))
        if options["estrito"] and not resultado["integridade_confirmada"]:
            raise CommandError("A integridade ou o vínculo dos artefatos foi reprovado.")
