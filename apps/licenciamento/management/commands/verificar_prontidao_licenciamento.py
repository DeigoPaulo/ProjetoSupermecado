import json

from django.core.management.base import BaseCommand, CommandError

from apps.licenciamento.services import diagnostico_prontidao_licenciamento


class Command(BaseCommand):
    help = "Verifica se a central de licenciamento está pronta para homologação ou produção."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", dest="como_json")
        parser.add_argument("--estrito", action="store_true")
        parser.add_argument("--producao", action="store_true")

    def handle(self, *args, **options):
        diagnostico = diagnostico_prontidao_licenciamento()
        alvo = "produção" if options["producao"] else "homologação"
        chave_prontidao = "pronto_producao" if options["producao"] else "pronto_homologacao"

        if options["como_json"]:
            self.stdout.write(json.dumps(diagnostico, ensure_ascii=False, sort_keys=True))
        else:
            estado = "PRONTO" if diagnostico[chave_prontidao] else "BLOQUEADO"
            self.stdout.write(f"Licenciamento para {alvo}: {estado}")
            for alerta in diagnostico["alertas"]:
                self.stdout.write(f"- {alerta}")
            self.stdout.write(f"Agendamento: {diagnostico['comando_agendamento']}")

        if (options["estrito"] or options["producao"]) and not diagnostico[chave_prontidao]:
            detalhes = "; ".join(diagnostico["alertas"]) or f"Ambiente ainda não aprovado para {alvo}."
            raise CommandError(f"Licenciamento não está pronto para {alvo}: {detalhes}")
