import json

from django.core.management.base import BaseCommand, CommandError

from apps.estoque.verificador_dossie_piloto import verificar_dossie_piloto


class Command(BaseCommand):
    help = "Confere offline um dossiê ZIP do piloto sem extrair seus arquivos."

    def add_arguments(self, parser):
        parser.add_argument("--dossie", required=True)
        parser.add_argument("--estrito", action="store_true")

    def handle(self, *args, **options):
        try:
            resultado = verificar_dossie_piloto(options["dossie"])
        except Exception as exc:
            raise CommandError(
                f"Não foi possível conferir o dossiê ({exc.__class__.__name__})."
            ) from None
        self.stdout.write(json.dumps(resultado, ensure_ascii=False, sort_keys=True))
        if options["estrito"] and not resultado["integridade_confirmada"]:
            raise CommandError("A integridade do dossiê foi reprovada.")
