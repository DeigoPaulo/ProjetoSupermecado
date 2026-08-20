from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.clientes.escopo import empresa_id_do_usuario
from apps.empresas.models import Filial
from apps.fiscal.services_dfe import consultar_distribuicao_dfe


class Command(BaseCommand):
    help = "Consulta a distribuição de DF-e por filial usando o adaptador fiscal configurado."

    def add_arguments(self, parser):
        parser.add_argument("--usuario", required=True, help="Usuário técnico ativo usado na auditoria.")
        parser.add_argument("--empresa-id", type=int)
        parser.add_argument("--filial-id", type=int)
        parser.add_argument("--limite", type=int, default=50)
        parser.add_argument(
            "--estrito",
            action="store_true",
            help="Retorna código de erro se qualquer filial falhar.",
        )

    def handle(self, *args, **options):
        try:
            usuario = get_user_model().objects.get(
                username=options["usuario"],
                is_active=True,
            )
        except get_user_model().DoesNotExist as exc:
            raise CommandError("Usuário técnico ativo não encontrado.") from exc

        filiais = Filial.objects.filter(is_active=True).select_related("empresa")
        empresa_usuario = empresa_id_do_usuario(usuario)
        if empresa_usuario is not None:
            filiais = filiais.filter(empresa_id=empresa_usuario)
        if options.get("empresa_id"):
            filiais = filiais.filter(empresa_id=options["empresa_id"])
        if options.get("filial_id"):
            filiais = filiais.filter(pk=options["filial_id"])
        filiais = filiais.order_by("empresa_id", "nome")

        if not filiais.exists():
            raise CommandError("Nenhuma filial ativa encontrada no escopo informado.")

        falhas = []
        recebidos = 0
        for filial in filiais.iterator():
            try:
                resultado = consultar_distribuicao_dfe(
                    filial=filial,
                    usuario=usuario,
                    limite=options["limite"],
                )
            except Exception as exc:
                falhas.append(f"{filial}: {exc}")
                self.stderr.write(self.style.ERROR(f"FALHA {filial}: {exc}"))
                continue
            recebidos += resultado["recebidos"]
            self.stdout.write(
                self.style.SUCCESS(
                    f"OK {filial}: {resultado['recebidos']} recebido(s), "
                    f"{resultado['criados']} novo(s)."
                )
            )

        self.stdout.write(
            f"Consulta concluída: {recebidos} documento(s), {len(falhas)} falha(s)."
        )
        if falhas and options["estrito"]:
            raise CommandError("Uma ou mais filiais falharam na consulta DF-e.")