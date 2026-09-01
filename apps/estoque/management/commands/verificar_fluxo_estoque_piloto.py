import json

from django.core.management.base import BaseCommand, CommandError

from apps.estoque.evidencia_piloto import gerar_evidencia_fluxo_estoque_piloto


class Command(BaseCommand):
    help = "Gera evidência somente leitura do fluxo ponta a ponta de estoque e validade."

    def add_arguments(self, parser):
        for nome in ("entrada", "venda", "perda", "inventario", "fechamento"):
            parser.add_argument(f"--{nome}-id", type=int, required=True)
        parser.add_argument("--estrito", action="store_true")
        parser.add_argument("--dados-sinteticos", action="store_true")

    def handle(self, *args, **options):
        try:
            evidencia = gerar_evidencia_fluxo_estoque_piloto(
                entrada_id=options["entrada_id"],
                venda_id=options["venda_id"],
                perda_id=options["perda_id"],
                inventario_id=options["inventario_id"],
                fechamento_id=options["fechamento_id"],
                dados_sinteticos=options["dados_sinteticos"],
            )
        except Exception as exc:
            raise CommandError(
                f"Não foi possível verificar o ensaio ({exc.__class__.__name__})."
            ) from None
        self.stdout.write(json.dumps(evidencia, ensure_ascii=False, sort_keys=True))
        if options["estrito"] and not evidencia["valida"]:
            raise CommandError("A evidência do fluxo de estoque foi reprovada.")
