import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.fiscal.compatibilidade_matriz_xsd import construir_compatibilidade_matriz_xsd
from apps.fiscal.inventario_dados_devolucao import construir_inventario_dados_devolucao
from apps.fiscal.matriz_atomica_devolucao import construir_matriz_atomica_devolucao


class Command(BaseCommand):
    help = "Confronta a matriz atômica da devolução com um pacote XSD auditado, sem gerar XML."

    def add_arguments(self, parser):
        parser.add_argument("--arquivo", required=True)
        parser.add_argument("--sha256", required=True)
        parser.add_argument("--versao", required=True)

    def handle(self, *args, **options):
        try:
            inventario = construir_inventario_dados_devolucao({})
            matriz = construir_matriz_atomica_devolucao(inventario)
            resultado = construir_compatibilidade_matriz_xsd(
                matriz=matriz,
                arquivo=Path(options["arquivo"]),
                sha256_esperado=options["sha256"],
                versao=options["versao"],
            )
        except (OSError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(resultado, ensure_ascii=False, indent=2, sort_keys=True))