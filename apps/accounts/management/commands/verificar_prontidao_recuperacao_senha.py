import json

from django.core.management.base import BaseCommand, CommandError

from apps.accounts.services import diagnostico_prontidao_recuperacao_senha


class Command(BaseCommand):
    help = "Verifica a configuracao SMTP usada na recuperacao de senha."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", dest="como_json")
        parser.add_argument("--estrito", action="store_true")

    def handle(self, *args, **options):
        diagnostico = diagnostico_prontidao_recuperacao_senha()
        pronto = diagnostico["prontidao"]["configuracao_smtp_completa"]

        if options["como_json"]:
            self.stdout.write(json.dumps(diagnostico, ensure_ascii=False, sort_keys=True))
        else:
            self.stdout.write(f"Recuperacao de senha SMTP: {'PRONTO PARA HOMOLOGACAO' if pronto else 'BLOQUEADO'}")
            for alerta in diagnostico["alertas"]:
                self.stdout.write(f"- {alerta}")
            if pronto:
                self.stdout.write("- Configuracao valida; envio real e DNS de e-mail ainda precisam de homologacao.")

        if options["estrito"] and not pronto:
            detalhes = "; ".join(diagnostico["prontidao"]["bloqueios"]) or "Configuracao SMTP incompleta."
            raise CommandError(f"Recuperacao de senha nao esta pronta para homologacao: {detalhes}")
