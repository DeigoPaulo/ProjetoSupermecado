import json

from django.core.management.base import BaseCommand, CommandError

from apps.fiscal.auditoria_pacote_xsd import AuditoriaPacoteXSDErro, auditar_pacote_xsd


class Command(BaseCommand):
    help = "Audita offline um ZIP XSD sem instalar, aprovar, ativar ou alterar configurações."

    def add_arguments(self, parser):
        parser.add_argument("--arquivo", required=True, help="Caminho local do ZIP arquivado.")
        parser.add_argument("--sha256", required=True, help="SHA-256 esperado do ZIP.")
        parser.add_argument("--versao", required=True, help="Identificador versionado candidato.")
        parser.add_argument("--arquivo-raiz", default="nfe_v4.00.xsd")

    def handle(self, *args, **options):
        try:
            resultado = auditar_pacote_xsd(
                arquivo=options["arquivo"],
                sha256_esperado=options["sha256"],
                versao=options["versao"],
                arquivo_raiz=options["arquivo_raiz"],
            )
        except AuditoriaPacoteXSDErro as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(resultado, ensure_ascii=False, indent=2, sort_keys=True))