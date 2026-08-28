import json
import re

from django.core.management.base import BaseCommand, CommandError

from apps.fiscal.models import ConfiguracaoFiscal
from apps.fiscal.readiness import diagnostico_prontidao_homologacao_goias


class Command(BaseCommand):
    help = "Verifica localmente a prontidão fiscal por filial, sem acessar a rede."

    def add_arguments(self, parser):
        grupo = parser.add_mutually_exclusive_group()
        grupo.add_argument("--filial-id", type=int)
        grupo.add_argument("--cnpj")
        parser.add_argument(
            "--estrito",
            action="store_true",
            help="Retorna erro quando alguma filial selecionada não estiver pronta.",
        )

    def handle(self, *args, **options):
        configuracoes = ConfiguracaoFiscal.objects.select_related(
            "filial__empresa"
        ).order_by("filial__empresa__nome_fantasia", "filial__nome")
        if options["filial_id"]:
            configuracoes = configuracoes.filter(filial_id=options["filial_id"])
        elif options["cnpj"]:
            cnpj = re.sub(r"\D", "", options["cnpj"])
            configuracoes = configuracoes.filter(filial__cnpj=cnpj)

        filiais = [
            diagnostico_prontidao_homologacao_goias(configuracao)
            for configuracao in configuracoes
        ]
        pendencias = []
        if not filiais:
            pendencias.append(
                "Nenhuma configuração fiscal foi encontrada para o filtro informado."
            )
        for filial in filiais:
            if not filial["pronto"]:
                pendencias.append(
                    f"Filial {filial['filial']['id']}: "
                    + ", ".join(filial["pendencias"])
                )
        resultado = {
            "contrato": "fiscal_readiness_command_v1",
            "pronto": bool(filiais) and not pendencias,
            "total_filiais": len(filiais),
            "filiais": filiais,
            "pendencias": pendencias,
            "observacao": (
                "Diagnóstico exclusivamente local; não acessa Focus/SEFAZ e não retorna "
                "token, CSC, certificado ou senha."
            ),
        }
        self.stdout.write(json.dumps(resultado, ensure_ascii=False, sort_keys=True))
        if options["estrito"] and not resultado["pronto"]:
            raise CommandError("A prontidão fiscal da filial está incompleta.")
