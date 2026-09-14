import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.fiscal.auditoria_importacoes_catalogo_teste import (
    auditar_importacoes_catalogo_teste,
)


class Command(BaseCommand):
    help = "Recusa importacoes do catalogo fiscal de teste por codigo operacional."

    def add_arguments(self, parser):
        parser.add_argument("--base-dir", default=str(settings.BASE_DIR))
        parser.add_argument("--detalhes", action="store_true")

    def handle(self, *args, **options):
        resultado = auditar_importacoes_catalogo_teste(
            options["base_dir"], incluir_detalhes=options["detalhes"]
        )
        self.stdout.write(json.dumps(resultado, ensure_ascii=False, sort_keys=True))
        if not resultado["conforme"]:
            raise CommandError("IMPORTACAO_CATALOGO_TESTE_FORA_DE_ARQUIVO_DE_TESTE")
