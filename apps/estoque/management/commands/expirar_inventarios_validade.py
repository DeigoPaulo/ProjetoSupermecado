from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.estoque.services import executar_manutencao_inventarios_validade


class Command(BaseCommand):
    help = "Encerra rascunhos de inventário de validade cujo prazo operacional de 24 horas venceu."

    def add_arguments(self, parser):
        parser.add_argument("--confirmar-expiracao", action="store_true")

    def handle(self, *args, **options):
        if not options["confirmar_expiracao"]:
            raise CommandError(
                "Use --confirmar-expiracao para materializar os prazos vencidos sem ajustar estoque."
            )
        try:
            expirados, registro = executar_manutencao_inventarios_validade(momento=timezone.now())
        except Exception as exc:
            raise CommandError(
                f"Falha na manutenção de validade ({exc.__class__.__name__}). Consulte o histórico operacional."
            ) from None
        ids = ", ".join(str(inventario.pk) for inventario in expirados) or "nenhum"
        self.stdout.write(
            self.style.SUCCESS(
                f"Execução {registro.execucao_id}. Inventários expirados: {len(expirados)} ({ids}). "
                "Nenhum saldo foi alterado."
            )
        )
