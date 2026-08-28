import json

from django.core.management.base import BaseCommand, CommandError

from apps.fiscal.adapters import diagnosticar_contrato_adaptador_sefaz
from apps.fiscal.validacoes import diagnosticar_schemas_fiscais


class Command(BaseCommand):
    help = "Valida o contrato técnico do adaptador SEFAZ sem transmitir documentos ou expor credenciais."

    def add_arguments(self, parser):
        parser.add_argument(
            "--exigir-eventos",
            action="store_true",
            help="Exige cancelamento, inutilização e consulta de protocolo além da transmissão.",
        )
        parser.add_argument(
            "--exigir-configuracao",
            action="store_true",
            help="Exige diagnóstico operacional pronto, sem testar credenciais na rede.",
        )
        parser.add_argument(
            "--estrito",
            action="store_true",
            help="Encerra com erro quando o adaptador não estiver pronto para a etapa solicitada.",
        )

    def handle(self, *args, **options):
        adaptador = diagnosticar_contrato_adaptador_sefaz()
        schema = diagnosticar_schemas_fiscais()
        pendencias = list(adaptador["pendencias"])
        configuracao_operacional = adaptador["configuracao_operacional"]
        if options["exigir_configuracao"]:
            if not configuracao_operacional["diagnostico_disponivel"]:
                pendencias.append(
                    "O adaptador não expõe diagnóstico operacional seguro."
                )
            elif not configuracao_operacional["pronto"]:
                pendencias.append(configuracao_operacional["mensagem"])
        if not adaptador["requisitos"]["validacao_schema_pelo_provedor"] and not schema["pronto"]:
            pendencias.append("Instale um schema fiscal local válido ou use um provedor que valide o schema.")
        if options["exigir_eventos"]:
            for campo, titulo in (
                ("cancelamento", "cancelamento"),
                ("inutilizacao", "inutilização"),
                ("consulta", "consulta de protocolo"),
            ):
                if not adaptador["requisitos"][campo] and f"O adaptador não implementa {titulo}." not in pendencias:
                    pendencias.append(f"O adaptador não implementa {titulo}.")

        resultado = {
            "contrato": "sefaz_adapter_validation_v1",
            "adaptador": adaptador,
            "configuracao_operacional": configuracao_operacional,
            "schema": {
                "configurado": schema["configurado"],
                "pronto": schema["pronto"],
                "sha256": schema["sha256"],
            },
            "exigir_eventos": bool(options["exigir_eventos"]),
            "exigir_configuracao": bool(options["exigir_configuracao"]),
            "pronto": not pendencias,
            "pendencias": pendencias,
            "observacao": "Este comando não transmite documento, não valida credenciais na rede e não libera produção.",
        }
        self.stdout.write(json.dumps(resultado, ensure_ascii=False, sort_keys=True))
        if options["estrito"] and pendencias:
            raise CommandError("Adaptador fiscal não está pronto: " + " ".join(pendencias))