from django.core.management.base import BaseCommand, CommandError

from apps.configuracoes.backup_operacional import (
    CODIGOS_FALHA,
    ETAPAS,
    registrar_resultado_backup,
)


class Command(BaseCommand):
    help = "Registra um resultado sanitizado e idempotente do backup operacional."

    def add_arguments(self, parser):
        parser.add_argument("--execucao-id", required=True)
        parser.add_argument("--status", choices=["sucesso", "falha"], required=True)
        parser.add_argument("--etapa", choices=sorted(ETAPAS), required=True)
        parser.add_argument("--criptografado", action="store_true")
        parser.add_argument("--copia-secundaria", action="store_true")
        parser.add_argument("--hash-validado", action="store_true")
        parser.add_argument(
            "--codigo-falha",
            choices=sorted(CODIGOS_FALHA),
            default="erro_operacional",
        )

    def handle(self, *args, **options):
        try:
            registro, criado = registrar_resultado_backup(
                execucao_id=options["execucao_id"],
                status=options["status"],
                etapa=options["etapa"],
                criptografado=options["criptografado"],
                copia_secundaria=options["copia_secundaria"],
                hash_validado=options["hash_validado"],
                codigo_falha=options["codigo_falha"],
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            f"backup_operacional_v1 status={options['status']} registrado={str(criado).lower()} id={registro.objeto_id}"
        )
