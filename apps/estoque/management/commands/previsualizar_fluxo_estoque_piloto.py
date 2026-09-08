import json

from django.core.management.base import BaseCommand, CommandError

from apps.estoque.previsualizacao_piloto import previsualizar_candidatos_piloto


class Command(BaseCommand):
    help = "Lista candidatos e impedimentos do piloto real sem alterar dados."

    def add_arguments(self, parser):
        parser.add_argument("--filial-id", type=int, required=True)
        parser.add_argument("--limite", type=int, default=20)
        parser.add_argument("--estrito", action="store_true")

    def handle(self, *args, **options):
        try:
            previa = previsualizar_candidatos_piloto(
                filial_id=options["filial_id"],
                limite_por_tipo=options["limite"],
            )
        except Exception as exc:
            raise CommandError(
                f"Não foi possível gerar a prévia ({exc.__class__.__name__})."
            ) from None
        self.stdout.write(json.dumps(previa, ensure_ascii=False, sort_keys=True))
        if options["estrito"] and previa["impedimentos"]:
            raise CommandError("A filial ainda possui impedimentos para o piloto real.")
