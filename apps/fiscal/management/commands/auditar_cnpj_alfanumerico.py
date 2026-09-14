import json

from django.core.management.base import BaseCommand, CommandError

from apps.fiscal.auditoria_cnpj_alfanumerico import auditar_base_identificadores


class Command(BaseCommand):
    help = "Audita CNPJ e chaves em modo somente leitura, com valores protegidos."

    def add_arguments(self, parser):
        parser.add_argument(
            "--estrito",
            action="store_true",
            help="Retorna erro quando o ensaio encontra bloqueios, sem modificar registros.",
        )

    def handle(self, *args, **options):
        resultado = auditar_base_identificadores()
        self.stdout.write(json.dumps(resultado, ensure_ascii=False, sort_keys=True))
        if options["estrito"] and resultado["resumo"]["quantidade_bloqueios"]:
            raise CommandError("A auditoria encontrou bloqueios; nenhum registro foi alterado.")
