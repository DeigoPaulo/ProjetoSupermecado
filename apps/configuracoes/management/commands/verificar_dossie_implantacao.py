from django.core.management.base import BaseCommand, CommandError

from apps.configuracoes.deployment_evidence import validar_dossie_implantacao


class Command(BaseCommand):
    help = "Valida integridade e liberação de um dossiê de implantação."

    def add_arguments(self, parser):
        parser.add_argument("arquivo")
        parser.add_argument("--estrito", action="store_true")

    def handle(self, *args, **options):
        resultado = validar_dossie_implantacao(options["arquivo"])
        estado = (
            "LIBERÁVEL"
            if resultado["liberavel"]
            else ("VÁLIDO COM PENDÊNCIAS" if resultado["valido"] else "INVÁLIDO")
        )
        self.stdout.write(
            f"Dossiê {resultado['perfil'] or '-'} / {resultado['alvo'] or '-'}: {estado}"
        )
        self.stdout.write(
            f"Integridade SHA-256: {'OK' if resultado['hash_valido'] else 'FALHOU'}"
        )
        for erro in resultado["erros"]:
            self.stdout.write(f"ERRO: {erro}")
        for aviso in resultado["avisos"]:
            self.stdout.write(f"AVISO: {aviso}")
        if options["estrito"] and not resultado["liberavel"]:
            raise CommandError("O dossiê não autoriza a liberação da implantação.")
