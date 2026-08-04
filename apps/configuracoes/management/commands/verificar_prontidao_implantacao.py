import json

from django.core.management.base import BaseCommand, CommandError

from apps.configuracoes.readiness import diagnostico_prontidao_implantacao


class Command(BaseCommand):
    help = "Consolida a prontidão do servidor central ou local para homologação ou produção."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", dest="como_json")
        parser.add_argument("--estrito", action="store_true")
        parser.add_argument("--producao", action="store_true")
        parser.add_argument("--exigir-recomendados", action="store_true")
        parser.add_argument(
            "--perfil",
            choices=("central", "servidor-local"),
            default="central",
            help="Tipo de servidor que será implantado.",
        )

    def handle(self, *args, **options):
        diagnostico = diagnostico_prontidao_implantacao(
            producao=options["producao"],
            perfil=options["perfil"],
        )
        recomendados_prontos = (
            diagnostico["resumo"]["recomendadas_prontas"] == diagnostico["resumo"]["recomendadas"]
        )
        if options["como_json"]:
            self.stdout.write(json.dumps(diagnostico, ensure_ascii=False, sort_keys=True))
        else:
            estado = "PRONTO" if diagnostico["pronto"] else "BLOQUEADO"
            resumo = diagnostico["resumo"]
            self.stdout.write(
                f"Implantação {diagnostico['perfil']} para {diagnostico['alvo']}: {estado}"
            )
            self.stdout.write(
                f"Obrigatórias: {resumo['obrigatorias_prontas']}/{resumo['obrigatorias']} "
                f"({resumo['percentual_obrigatorio']}%)"
            )
            for item in diagnostico["verificacoes"]:
                tipo = "obrigatória" if item["obrigatoria"] else "recomendada"
                situacao = "OK" if item["pronta"] else "PENDENTE"
                self.stdout.write(f"- {item['id']}: {situacao} ({tipo})")
            for bloqueio in diagnostico["bloqueios"]:
                self.stdout.write(f"  BLOQUEIO: {bloqueio}")
            for recomendacao in diagnostico["recomendacoes"]:
                self.stdout.write(f"  RECOMENDAÇÃO: {recomendacao}")
        deve_falhar = (options["estrito"] or options["producao"]) and not diagnostico["pronto"]
        if options["exigir_recomendados"] and not recomendados_prontos:
            deve_falhar = True
        if deve_falhar:
            detalhes = list(diagnostico["bloqueios"])
            if options["exigir_recomendados"]:
                detalhes += diagnostico["recomendacoes"]
            raise CommandError("Prontidão de implantação incompleta: " + "; ".join(detalhes))
