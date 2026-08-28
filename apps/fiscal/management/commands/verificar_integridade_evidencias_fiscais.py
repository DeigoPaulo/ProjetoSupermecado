import json
import os
import tempfile
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.fiscal.evidencias import (
    gerar_manifesto_integridade_evidencias,
    verificar_continuidade_manifesto_anterior,
)
from apps.fiscal.integridade_operacional import registrar_resultado_integridade


class Command(BaseCommand):
    help = (
        "Recalcula a cadeia append-only das evidências fiscais sem acessar a rede "
        "e pode gravar um manifesto externo de âncoras."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--arquivo",
            help="Caminho do manifesto JSON. A promoção para o destino é atômica.",
        )
        parser.add_argument(
            "--comparar-arquivo",
            help="Compara sem sobrescrever com uma âncora externa anterior.",
        )
        parser.add_argument(
            "--estrito",
            action="store_true",
            help="Retorna erro quando qualquer cadeia fiscal estiver divergente.",
        )
        parser.add_argument(
            "--registrar-alerta",
            action="store_true",
            help="Registra na auditoria um resumo sanitizado para o painel Master.",
        )
        parser.add_argument(
            "--origem",
            choices=["backup", "restauracao", "manual"],
            default="manual",
            help="Origem operacional da verificação registrada.",
        )

    def handle(self, *args, **options):
        manifesto = gerar_manifesto_integridade_evidencias()
        conteudo = json.dumps(
            manifesto,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        ) + "\n"
        arquivo = str(options.get("arquivo") or "").strip()
        comparar_arquivo = str(options.get("comparar_arquivo") or "").strip()
        if not comparar_arquivo and arquivo and Path(arquivo).expanduser().exists():
            comparar_arquivo = arquivo
        divergencias_externas = []
        if comparar_arquivo:
            anterior_path = Path(comparar_arquivo).expanduser().resolve()
            try:
                anterior = json.loads(anterior_path.read_text(encoding="utf-8-sig"))
            except (OSError, ValueError) as exc:
                divergencias_externas = [
                    f"Não foi possível validar a âncora externa anterior: {exc}"
                ]
            else:
                divergencias_externas = verificar_continuidade_manifesto_anterior(
                    anterior,
                    manifesto,
                )
        manifesto["continuidade_externa"] = not divergencias_externas
        manifesto["divergencias_externas"] = divergencias_externas
        if divergencias_externas:
            manifesto["integra"] = False
            manifesto["total_divergencias"] += len(divergencias_externas)

        if arquivo and not divergencias_externas:
            destino = Path(arquivo).expanduser().resolve()
            destino.parent.mkdir(parents=True, exist_ok=True)
            temporario = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    newline="\n",
                    dir=destino.parent,
                    prefix=f".{destino.name}.",
                    suffix=".tmp",
                    delete=False,
                ) as fluxo:
                    temporario = Path(fluxo.name)
                    fluxo.write(conteudo)
                    fluxo.flush()
                    os.fsync(fluxo.fileno())
                os.replace(temporario, destino)
                temporario = None
            finally:
                if temporario and temporario.exists():
                    temporario.unlink()
            manifesto["arquivo"] = str(destino)

        if options["registrar_alerta"]:
            _, criado = registrar_resultado_integridade(
                manifesto,
                origem=options["origem"],
            )
            manifesto["alerta_operacional"] = {
                "status": "integra" if manifesto["integra"] else "divergente",
                "registrado": criado,
                "origem": options["origem"],
            }

        self.stdout.write(
            json.dumps(manifesto, ensure_ascii=False, sort_keys=True)
        )
        if options["estrito"] and not manifesto["integra"]:
            raise CommandError(
                f"Foram detectadas {manifesto['total_divergencias']} cadeia(s) fiscal(is) divergente(s)."
            )