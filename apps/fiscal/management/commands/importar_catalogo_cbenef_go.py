from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.fiscal.cbenef import ler_catalogo_cbenef_go_docx, sha256_arquivo
from apps.fiscal.models import CatalogoBeneficioFiscal, ItemBeneficioFiscal


class Command(BaseCommand):
    help = (
        "Importa um DOCX oficial de cBenef GO com hash e vigência explícitos. "
        "O comando não acessa a internet e não ativa o catálogo por padrão."
    )

    def add_arguments(self, parser):
        parser.add_argument("arquivo")
        parser.add_argument("--versao", required=True)
        parser.add_argument("--fonte-url", required=True)
        parser.add_argument("--fonte-nome", default="Secretaria da Economia de Goiás")
        parser.add_argument("--sha256-esperado", required=True)
        parser.add_argument("--publicado-em")
        parser.add_argument("--vigencia-inicio", required=True)
        parser.add_argument("--vigencia-fim")
        parser.add_argument("--quantidade-esperada", type=int)
        parser.add_argument("--ativar", action="store_true")

    def handle(self, *args, **opcoes):
        caminho = Path(opcoes["arquivo"]).resolve()
        if not caminho.is_file():
            raise CommandError(f"Arquivo não encontrado: {caminho}")
        if caminho.suffix.lower() != ".docx":
            raise CommandError("A fonte deve ser o arquivo DOCX oficial.")
        if caminho.stat().st_size > 10 * 1024 * 1024:
            raise CommandError("Arquivo excede o limite seguro de 10 MB.")

        fonte_url = opcoes["fonte_url"].strip()
        url = urlparse(fonte_url)
        host = (url.hostname or "").lower()
        if url.scheme != "https" or not (host == "goias.gov.br" or host.endswith(".goias.gov.br")):
            raise CommandError("A fonte deve usar HTTPS em domínio oficial goias.gov.br.")

        esperado = opcoes["sha256_esperado"].strip().lower()
        calculado = sha256_arquivo(caminho)
        if calculado != esperado:
            raise CommandError(
                f"SHA-256 divergente. Esperado {esperado}; calculado {calculado}. "
                "Nenhum dado foi importado."
            )

        try:
            vigencia_inicio = date.fromisoformat(opcoes["vigencia_inicio"])
            vigencia_fim = (
                date.fromisoformat(opcoes["vigencia_fim"]) if opcoes.get("vigencia_fim") else None
            )
            publicado_em = (
                date.fromisoformat(opcoes["publicado_em"]) if opcoes.get("publicado_em") else None
            )
        except ValueError as exc:
            raise CommandError("Datas devem usar o formato AAAA-MM-DD.") from exc
        if vigencia_fim and vigencia_fim < vigencia_inicio:
            raise CommandError("A vigência final não pode anteceder a inicial.")

        try:
            itens, duplicados = ler_catalogo_cbenef_go_docx(caminho)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        quantidade_esperada = opcoes.get("quantidade_esperada")
        if quantidade_esperada is not None and len(itens) != quantidade_esperada:
            raise CommandError(
                f"Quantidade divergente. Esperada {quantidade_esperada}; encontrada {len(itens)}."
            )

        with transaction.atomic():
            existente = CatalogoBeneficioFiscal.objects.filter(
                uf="GO",
                versao=opcoes["versao"].strip(),
                fonte_sha256=calculado,
            ).first()
            if existente:
                if existente.quantidade_itens != len(itens) or existente.itens.count() != len(itens):
                    raise CommandError("Catálogo existente está inconsistente; revise-o manualmente.")
                if opcoes["ativar"] and not existente.ativo:
                    CatalogoBeneficioFiscal.objects.filter(
                        uf="GO", ativo=True, vigencia_inicio=vigencia_inicio
                    ).exclude(pk=existente.pk).update(ativo=False)
                    existente.ativo = True
                    existente.save(update_fields=["ativo"])
                self.stdout.write(
                    self.style.WARNING(
                        f"Catálogo já importado: {existente} ({existente.quantidade_itens} itens)."
                    )
                )
                return

            catalogo = CatalogoBeneficioFiscal(
                uf="GO",
                versao=opcoes["versao"].strip(),
                fonte_nome=opcoes["fonte_nome"].strip(),
                fonte_url=fonte_url,
                fonte_sha256=calculado,
                publicado_em=publicado_em,
                vigencia_inicio=vigencia_inicio,
                vigencia_fim=vigencia_fim,
                ativo=False,
                quantidade_itens=len(itens),
                codigos_duplicados=duplicados,
            )
            catalogo.full_clean()
            catalogo.save()
            ItemBeneficioFiscal.objects.bulk_create(
                [ItemBeneficioFiscal(catalogo=catalogo, **item) for item in itens],
                batch_size=500,
            )
            if opcoes["ativar"]:
                CatalogoBeneficioFiscal.objects.filter(
                    uf="GO", ativo=True, vigencia_inicio=vigencia_inicio
                ).exclude(pk=catalogo.pk).update(ativo=False)
                catalogo.ativo = True
                catalogo.save(update_fields=["ativo"])

        estado = "ativo" if catalogo.ativo else "inativo"
        detalhe_duplicados = f"; redações substituídas: {', '.join(duplicados)}" if duplicados else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"Catálogo {catalogo.versao} importado com {len(itens)} itens, {estado}"
                f"{detalhe_duplicados}. SHA-256: {calculado}"
            )
        )
