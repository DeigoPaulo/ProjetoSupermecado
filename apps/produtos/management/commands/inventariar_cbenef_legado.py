import json

from django.core.management.base import BaseCommand

from apps.produtos.diagnosticos import diagnostico_cbenef_legado


class Command(BaseCommand):
    help = "Inventaria, sem alterar dados, produtos que ainda possuem cBenef legado."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", dest="como_json")

    def handle(self, *args, **options):
        diagnostico = diagnostico_cbenef_legado()
        if options["como_json"]:
            self.stdout.write(json.dumps(diagnostico, ensure_ascii=False, sort_keys=True))
            return

        self.stdout.write(
            f"Produtos com cBenef legado: {diagnostico['quantidade_produtos']}"
        )
        for produto in diagnostico["produtos"]:
            referencia = produto["codigo_barras"] or produto["codigo_interno"] or "-"
            self.stdout.write(
                f"- id={produto['id']} referencia={referencia} "
                f"cBenef={produto['codigo_beneficio_fiscal']}"
            )
        self.stdout.write(
            f"Fallback emissivo: {diagnostico['estado_fallback_emissivo']}"
        )
        self.stdout.write(
            f"Decisao: {diagnostico['decisao_remocao_coluna']}"
        )
