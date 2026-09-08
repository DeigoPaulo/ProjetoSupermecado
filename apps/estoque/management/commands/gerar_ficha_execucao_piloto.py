import json

from django.core.management.base import BaseCommand, CommandError

from apps.estoque.ficha_execucao_piloto import gerar_ficha_execucao_piloto


class Command(BaseCommand):
    help = "Gera a ficha somente leitura dos IDs escolhidos para o piloto real."

    def add_arguments(self, parser):
        for nome in ("entrada", "venda", "perda", "inventario", "fechamento"):
            parser.add_argument(f"--{nome}-id", type=int, required=True)
        parser.add_argument("--responsavel-execucao", required=True)
        parser.add_argument("--responsavel-conferencia", required=True)
        parser.add_argument("--observacoes", default="")
        parser.add_argument("--estrito", action="store_true")

    def handle(self, *args, **options):
        try:
            ficha = gerar_ficha_execucao_piloto(
                entrada_id=options["entrada_id"],
                venda_id=options["venda_id"],
                perda_id=options["perda_id"],
                inventario_id=options["inventario_id"],
                fechamento_id=options["fechamento_id"],
                responsavel_execucao=options["responsavel_execucao"],
                responsavel_conferencia=options["responsavel_conferencia"],
                observacoes_operacionais=options["observacoes"],
            )
        except Exception as exc:
            raise CommandError(
                f"Não foi possível gerar a ficha ({exc.__class__.__name__})."
            ) from None
        self.stdout.write(json.dumps(ficha, ensure_ascii=False, sort_keys=True))
        if options["estrito"] and not ficha["apta_para_verificacao_final"]:
            raise CommandError("A seleção ainda possui impedimentos para o piloto real.")
