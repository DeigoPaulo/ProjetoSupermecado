from pathlib import Path
from urllib.parse import urlparse

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.fiscal.cbenef import sha256_arquivo
from apps.fiscal.models import CatalogoNCM, ItemNCM
from apps.fiscal.ncm import FONTE_NCM_OFICIAL, ler_catalogo_ncm_json


class Command(BaseCommand):
    help = (
        "Importa um snapshot JSON oficial da NCM com hash e referência explícitos. "
        "O comando não acessa a internet e não ativa o catálogo por padrão."
    )

    def add_arguments(self, parser):
        parser.add_argument("arquivo")
        parser.add_argument("--versao", required=True)
        parser.add_argument("--fonte-url", default=FONTE_NCM_OFICIAL)
        parser.add_argument("--sha256-esperado", required=True)
        parser.add_argument("--referencia-esperada", required=True)
        parser.add_argument("--quantidade-esperada", type=int, required=True)
        parser.add_argument("--ativar", action="store_true")

    def handle(self, *args, **opcoes):
        caminho = Path(opcoes["arquivo"]).resolve()
        if not caminho.is_file():
            raise CommandError(f"Arquivo não encontrado: {caminho}")
        if caminho.suffix.lower() != ".json":
            raise CommandError("A fonte deve ser o arquivo JSON oficial.")
        if caminho.stat().st_size > 10 * 1024 * 1024:
            raise CommandError("Arquivo excede o limite seguro de 10 MB.")

        fonte_url = opcoes["fonte_url"].strip()
        url = urlparse(fonte_url)
        if url.scheme != "https" or (url.hostname or "").lower() != "portalunico.siscomex.gov.br":
            raise CommandError("A fonte deve usar HTTPS no host oficial portalunico.siscomex.gov.br.")

        esperado = opcoes["sha256_esperado"].strip().lower()
        calculado = sha256_arquivo(caminho)
        if calculado != esperado:
            raise CommandError(
                f"SHA-256 divergente. Esperado {esperado}; calculado {calculado}. "
                "Nenhum dado foi importado."
            )
        try:
            dados = ler_catalogo_ncm_json(caminho)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        referencia = dados["referencia_em"].isoformat()
        if referencia != opcoes["referencia_esperada"]:
            raise CommandError(
                f"Referência divergente. Esperada {opcoes['referencia_esperada']}; "
                f"arquivo informa {referencia}."
            )
        if len(dados["itens"]) != opcoes["quantidade_esperada"]:
            raise CommandError(
                f"Quantidade divergente. Esperada {opcoes['quantidade_esperada']}; "
                f"encontrada {len(dados['itens'])}."
            )

        with transaction.atomic():
            existente = CatalogoNCM.objects.filter(
                versao=opcoes["versao"].strip(),
                fonte_sha256=calculado,
            ).first()
            if existente:
                if existente.quantidade_itens != len(dados["itens"]) or existente.itens.count() != len(dados["itens"]):
                    raise CommandError("Catálogo existente está inconsistente; revise-o manualmente.")
                if opcoes["ativar"] and not existente.ativo:
                    CatalogoNCM.objects.filter(ativo=True).exclude(pk=existente.pk).update(ativo=False)
                    existente.ativo = True
                    existente.save(update_fields=["ativo"])
                self.stdout.write(
                    self.style.WARNING(
                        f"Catálogo já importado: {existente} ({existente.quantidade_itens} itens)."
                    )
                )
                return

            catalogo = CatalogoNCM(
                versao=opcoes["versao"].strip(),
                referencia_em=dados["referencia_em"],
                ato=dados["ato"],
                fonte_nome="Portal Único Siscomex / Receita Federal",
                fonte_url=fonte_url,
                fonte_sha256=calculado,
                ativo=False,
                quantidade_itens=len(dados["itens"]),
                quantidade_linhas_origem=dados["quantidade_linhas_origem"],
            )
            catalogo.full_clean()
            catalogo.save()
            ItemNCM.objects.bulk_create(
                [ItemNCM(catalogo=catalogo, **item) for item in dados["itens"]],
                batch_size=1000,
            )
            if opcoes["ativar"]:
                CatalogoNCM.objects.filter(ativo=True).exclude(pk=catalogo.pk).update(ativo=False)
                catalogo.ativo = True
                catalogo.save(update_fields=["ativo"])

        estado = "ativo" if catalogo.ativo else "inativo"
        self.stdout.write(
            self.style.SUCCESS(
                f"Catálogo NCM {catalogo.versao} importado com {catalogo.quantidade_itens} "
                f"códigos finais, {estado}. SHA-256: {calculado}"
            )
        )
