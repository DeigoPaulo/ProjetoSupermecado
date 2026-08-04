import json

from django.core.management.base import BaseCommand, CommandError

from apps.empresas.services_lookup import diagnostico_prontidao_consulta_cadastro


class Command(BaseCommand):
    help = "Verifica a prontidao dos provedores de consulta de CNPJ e CEP."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", dest="como_json")
        parser.add_argument("--estrito", action="store_true")

    def handle(self, *args, **options):
        diagnostico = diagnostico_prontidao_consulta_cadastro()
        pronto = diagnostico["prontidao"]["pronto_homologacao"]

        if options["como_json"]:
            self.stdout.write(json.dumps(diagnostico, ensure_ascii=False, sort_keys=True))
        else:
            estado = "PRONTO PARA HOMOLOGACAO" if pronto else "FALLBACK LOCAL"
            self.stdout.write(f"Consulta CNPJ/CEP: {estado}")
            for alerta in diagnostico["alertas"]:
                self.stdout.write(f"- {alerta}")

        if options["estrito"] and not pronto:
            detalhes = "; ".join(diagnostico["prontidao"]["bloqueios"]) or "Provedores externos incompletos."
            raise CommandError(f"Consulta CNPJ/CEP nao esta pronta para homologacao: {detalhes}")
