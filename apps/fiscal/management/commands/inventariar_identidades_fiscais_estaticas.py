import json

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.fiscal.inventario_estatico_identidades_fiscais import (
    inventariar_identidades_fiscais_estaticas,
)


class Command(BaseCommand):
    help = "Classifica candidatos fiscais no codigo e na documentacao sem exibir valores."

    def add_arguments(self, parser):
        parser.add_argument(
            "--detalhes",
            action="store_true",
            help="Inclui caminho, linha, categoria e hash; nunca inclui o valor completo.",
        )

    def handle(self, *args, **options):
        resultado = inventariar_identidades_fiscais_estaticas(
            settings.BASE_DIR,
            incluir_ocorrencias=options["detalhes"],
        )
        self.stdout.write(json.dumps(resultado, ensure_ascii=False, sort_keys=True))
