from django.core.management.base import BaseCommand

from apps.empresas.models import Empresa
from apps.empresas.services_eventos_entrada import processar_entrada_sincronizacao
from apps.empresas.services_sincronizacao import processar_fila
from apps.licenciamento.services import sincronizar_licenca_local


class Command(BaseCommand):
    help = "Processa sincronização operacional e renova a licença local em uma única execução agendável."

    def add_arguments(self, parser):
        parser.add_argument("--limite-saida", type=int, default=50)
        parser.add_argument("--limite-entrada", type=int, default=50)
        parser.add_argument(
            "--entrada-primeiro",
            action="store_true",
            help="Processa primeiro os eventos recebidos antes de enviar a fila local.",
        )

    def handle(self, *args, **options):
        limite_saida = max(1, options["limite_saida"])
        limite_entrada = max(1, options["limite_entrada"])
        if options["entrada_primeiro"]:
            entrada = processar_entrada_sincronizacao(limite=limite_entrada)
            saida = processar_fila(limite=limite_saida)
        else:
            saida = processar_fila(limite=limite_saida)
            entrada = processar_entrada_sincronizacao(limite=limite_entrada)

        licencas = [sincronizar_licenca_local(empresa) for empresa in Empresa.objects.filter(is_active=True)]
        renovadas = sum(1 for item in licencas if item["status"] == "sincronizado")
        erros_licenca = sum(1 for item in licencas if item["status"] == "erro")
        self.stdout.write(
            self.style.SUCCESS(
                "Sincronização completa: "
                f"{saida['enviados']} enviado(s), {saida['erros']} erro(s) de saída; "
                f"{entrada['processados']} entrada(s) processada(s), {entrada['erros']} erro(s) de entrada; "
                f"{renovadas} licenca(s) renovada(s), {erros_licenca} erro(s) de licença."
            )
        )