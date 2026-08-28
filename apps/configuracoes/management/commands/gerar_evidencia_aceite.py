import hashlib
import json
import os
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.configuracoes.acceptance_evidence import gerar_evidencia_aceite


class Command(BaseCommand):
    help = "Gera a evidência consolidada do aceite técnico da instalação local."

    def add_arguments(self, parser):
        parser.add_argument("--dossie", required=True)
        parser.add_argument(
            "--saida",
            default="artifacts/evidencia_aceite_implantacao.json",
        )
        parser.add_argument("--url")
        parser.add_argument("--timeout", type=int, default=5)
        parser.add_argument(
            "--backup-max-horas",
            type=int,
            help="Substitui explicitamente LOCAL_BACKUP_MAX_AGE_HOURS nesta execução.",
        )
        parser.add_argument("--estrito", action="store_true")

    def handle(self, *args, **options):
        evidencia = gerar_evidencia_aceite(
            options["dossie"],
            url=options["url"],
            timeout=max(1, min(options["timeout"], 30)),
            idade_maxima_backup_horas=(
                max(1, options["backup_max_horas"])
                if options["backup_max_horas"] is not None
                else None
            ),
        )
        destino = Path(options["saida"]).expanduser().resolve()
        destino.parent.mkdir(parents=True, exist_ok=True)
        conteudo = (json.dumps(evidencia, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
            "utf-8"
        )
        temporario = destino.with_name(f".{destino.name}.{os.getpid()}.tmp")
        try:
            temporario.write_bytes(conteudo)
            temporario.replace(destino)
        finally:
            temporario.unlink(missing_ok=True)
        digest = hashlib.sha256(conteudo).hexdigest()
        destino.with_name(destino.name + ".sha256").write_text(
            f"{digest}  {destino.name}\n",
            encoding="ascii",
        )
        estado = "LIBERÁVEL" if evidencia["liberavel"] else "BLOQUEADA"
        self.stdout.write(f"Evidência de aceite gerada: {destino.name} ({estado}).")
        self.stdout.write(f"SHA-256: {digest}")
        if options["estrito"] and not evidencia["liberavel"]:
            raise CommandError("A instalação não está liberada para aceite.")
