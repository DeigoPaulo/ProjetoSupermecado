import json

from django.core.management.base import BaseCommand, CommandError

from apps.configuracoes.homologation import diagnostico_homologacao_servidor_local


class Command(BaseCommand):
    help = "Verifica se a versao do servidor local possui homologacao valida."

    def add_arguments(self, parser):
        parser.add_argument("--versao", help="Versao do artefato a validar.")
        parser.add_argument(
            "--json",
            action="store_true",
            dest="como_json",
            help="Emite o diagnostico em JSON.",
        )
        parser.add_argument(
            "--estrito",
            action="store_true",
            help="Retorna erro quando a versao nao estiver homologada.",
        )

    def handle(self, *args, **options):
        diagnostico = diagnostico_homologacao_servidor_local(
            versao_vigente=options.get("versao") or None
        )

        if options["como_json"]:
            self.stdout.write(
                json.dumps(
                    diagnostico,
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                )
            )
        else:
            estado = "APROVADA" if diagnostico["pronta"] else "BLOQUEADA"
            self.stdout.write(
                "Homologacao do servidor local "
                f"{diagnostico['versao_vigente']}: {estado}"
            )
            self.stdout.write(f"- Estado: {diagnostico['status']}")
            self.stdout.write(f"- {diagnostico['descricao']}")
            if diagnostico["registro"]:
                registro = diagnostico["registro"]
                self.stdout.write(
                    f"- Registro: #{registro['id']} em {registro['maquina']}"
                )

        if options["estrito"] and not diagnostico["pronta"]:
            raise CommandError(
                "A versao do servidor local nao possui homologacao valida: "
                + diagnostico["status"].lower()
            )
