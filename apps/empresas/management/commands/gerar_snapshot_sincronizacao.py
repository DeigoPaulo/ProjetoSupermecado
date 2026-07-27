from django.core.management.base import BaseCommand, CommandError

from apps.empresas.models import Empresa, Filial
from apps.empresas.services_snapshots import gerar_carga_inicial_sincronizacao


class Command(BaseCommand):
    help = "Enfileira carga inicial idempotente de produtos e saldos para a sincronizacao."

    def add_arguments(self, parser):
        parser.add_argument("--empresa", type=int, required=True)
        parser.add_argument("--filial", type=int)
        parser.add_argument("--limite", type=int, default=5000)

    def handle(self, *args, **options):
        empresa = Empresa.objects.filter(pk=options["empresa"]).first()
        if not empresa:
            raise CommandError("Empresa nao encontrada.")

        filial = None
        filial_id = options.get("filial")
        if filial_id:
            filial = Filial.objects.filter(pk=filial_id, empresa=empresa).first()
            if not filial:
                raise CommandError("Filial nao encontrada para a empresa informada.")

        try:
            resultado = gerar_carga_inicial_sincronizacao(
                empresa=empresa,
                filial=filial,
                limite=options["limite"],
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                "Carga inicial enfileirada: "
                f"{resultado['estoques_processados']} saldo(s) processado(s), "
                f"{resultado['produtos_criados']} produto(s) novo(s) na fila e "
                f"{resultado['saldos_criados']} saldo(s) novo(s) na fila."
            )
        )
