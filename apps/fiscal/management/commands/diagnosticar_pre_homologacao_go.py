import json

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.fiscal.pre_homologacao_go import (
    diagnostico_pre_homologacao_go,
    diagnostico_prontidao_interna_piloto_go,
)


class Command(BaseCommand):
    help = "Publica diagnostico offline do XSD e da matriz de capacidades do piloto GO."

    def handle(self, *args, **options):
        resultado = diagnostico_pre_homologacao_go(settings.BASE_DIR)
        resultado["prontidao_interna_piloto"] = diagnostico_prontidao_interna_piloto_go(
            settings.BASE_DIR
        )
        self.stdout.write(json.dumps(resultado, ensure_ascii=False, sort_keys=True, indent=2))
