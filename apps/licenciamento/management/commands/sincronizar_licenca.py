from django.core.management.base import BaseCommand

from apps.empresas.models import Empresa
from apps.licenciamento.services import sincronizar_licenca_local


class Command(BaseCommand):
    help = "Renova automaticamente a concessão de licença de cada empresa local junto à central."

    def handle(self, *args, **options):
        resultados = {"sincronizado": 0, "erro": 0, "nao_configurado": 0}
        for empresa in Empresa.objects.filter(is_active=True):
            resultado = sincronizar_licenca_local(empresa)
            status = resultado["status"]
            resultados[status] = resultados.get(status, 0) + 1
        self.stdout.write(
            self.style.SUCCESS(
                "Licenciamento: "
                f"{resultados['sincronizado']} renovado(s), "
                f"{resultados['erro']} erro(s), "
                f"{resultados['nao_configurado']} não configurado(s)."
            )
        )