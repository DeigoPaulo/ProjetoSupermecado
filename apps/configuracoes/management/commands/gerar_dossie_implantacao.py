import hashlib
import json
import os
from pathlib import Path

from django.core.management.base import BaseCommand

from apps.configuracoes.deployment_evidence import gerar_dossie_implantacao


class Command(BaseCommand):
    help = "Gera a evidência técnica sanitizada de uma implantação."

    def add_arguments(self, parser):
        parser.add_argument(
            "--perfil",
            choices=("central", "servidor-local"),
            default="central",
        )
        parser.add_argument("--producao", action="store_true")
        parser.add_argument(
            "--saida",
            default="artifacts/dossie_implantacao.json",
            help="Arquivo JSON de destino.",
        )

    def handle(self, *args, **options):
        destino = Path(options["saida"]).expanduser().resolve()
        destino.parent.mkdir(parents=True, exist_ok=True)
        dossie = gerar_dossie_implantacao(
            perfil=options["perfil"],
            producao=options["producao"],
        )
        conteudo = json.dumps(dossie, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        conteudo_bytes = conteudo.encode("utf-8")
        temporario = destino.with_name(f".{destino.name}.{os.getpid()}.tmp")
        try:
            temporario.write_bytes(conteudo_bytes)
            temporario.replace(destino)
        finally:
            temporario.unlink(missing_ok=True)

        digest = hashlib.sha256(conteudo_bytes).hexdigest()
        hash_destino = destino.with_name(destino.name + ".sha256")
        hash_destino.write_text(f"{digest}  {destino.name}\n", encoding="ascii")
        estado = "PRONTO" if dossie["prontidao"]["pronto"] else "BLOQUEADO"
        self.stdout.write(
            self.style.SUCCESS(
                f"Dossiê {dossie['contrato']} gerado: {destino.name} ({estado})."
            )
        )
        self.stdout.write(f"SHA-256: {digest}")
