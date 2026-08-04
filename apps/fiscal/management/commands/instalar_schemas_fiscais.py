import hashlib
import io
import json
import os
import re
import shutil
import stat
import tempfile
import urllib.parse
import urllib.request
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from lxml import etree


HOSTS_OFICIAIS = {
    "www.nfe.fazenda.gov.br",
    "nfe.fazenda.gov.br",
    "hom.nfe.fazenda.gov.br",
}
LIMITE_DOWNLOAD = 25 * 1024 * 1024
LIMITE_EXTRAIDO = 100 * 1024 * 1024
LIMITE_ARQUIVOS = 500


def _sha256(conteudo):
    return hashlib.sha256(conteudo).hexdigest()


def _slug_versao(valor):
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", valor.strip()).strip(".-")
    if not slug:
        raise CommandError("Informe uma versão valida para identificar o pacote.")
    return slug


def _baixar_url_oficial(url):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in HOSTS_OFICIAIS:
        raise CommandError("A URL deve usar HTTPS e pertencer ao Portal Nacional da NF-e.")
    request = urllib.request.Request(url, headers={"User-Agent": "SupermercadoERP/schema-installer"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            tamanho = int(response.headers.get("Content-Length") or 0)
            if tamanho > LIMITE_DOWNLOAD:
                raise CommandError("Pacote fiscal excede o limite de download.")
            conteudo = response.read(LIMITE_DOWNLOAD + 1)
    except CommandError:
        raise
    except Exception as exc:
        raise CommandError("Não foi possível baixar o pacote fiscal oficial.") from exc
    if len(conteudo) > LIMITE_DOWNLOAD:
        raise CommandError("Pacote fiscal excede o limite de download.")
    return conteudo


def _ler_pacote(arquivo=None, url=None):
    if bool(arquivo) == bool(url):
        raise CommandError("Informe exatamente uma origem: --arquivo ou --url.")
    if url:
        return _baixar_url_oficial(url), url
    caminho = Path(arquivo).expanduser().resolve()
    if not caminho.is_file():
        raise CommandError("Arquivo ZIP de schemas não encontrado.")
    if caminho.stat().st_size > LIMITE_DOWNLOAD:
        raise CommandError("Pacote fiscal excede o limite permitido.")
    return caminho.read_bytes(), str(caminho)


def _validar_membro(info):
    nome = PurePosixPath(info.filename.replace("\\", "/"))
    if nome.is_absolute() or ".." in nome.parts:
        raise CommandError("Pacote fiscal contem caminho inseguro.")
    modo = info.external_attr >> 16
    if stat.S_ISLNK(modo):
        raise CommandError("Pacote fiscal não pode conter links simbolicos.")
    return nome


def _extrair_seguro(conteudo, destino):
    try:
        with zipfile.ZipFile(io.BytesIO(conteudo)) as pacote:
            arquivos = [info for info in pacote.infolist() if not info.is_dir()]
            if not arquivos or len(arquivos) > LIMITE_ARQUIVOS:
                raise CommandError("Quantidade de arquivos do pacote fiscal e inválida.")
            total = sum(info.file_size for info in arquivos)
            if total > LIMITE_EXTRAIDO:
                raise CommandError("Conteudo extraido do pacote fiscal excede o limite.")
            for info in arquivos:
                nome = _validar_membro(info)
                if nome.suffix.lower() != ".xsd":
                    continue
                alvo = destino.joinpath(*nome.parts)
                alvo.parent.mkdir(parents=True, exist_ok=True)
                with pacote.open(info) as origem, alvo.open("wb") as saida:
                    shutil.copyfileobj(origem, saida)
    except zipfile.BadZipFile as exc:
        raise CommandError("O arquivo informado não e um ZIP fiscal valido.") from exc


def _localizar_raiz(destino, nome):
    candidatos = list(destino.rglob(nome))
    if len(candidatos) != 1:
        raise CommandError(
            f"O pacote deve conter exatamente um arquivo raiz {nome}; encontrados: {len(candidatos)}."
        )
    return candidatos[0]


def _validar_schema(arquivo):
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    try:
        etree.XMLSchema(etree.parse(str(arquivo), parser))
    except (OSError, etree.XMLSyntaxError, etree.XMLSchemaParseError) as exc:
        raise CommandError(f"O XSD raiz ou seus imports sao invalidos: {exc}") from exc


class Command(BaseCommand):
    help = "Instala e valida um pacote oficial de schemas NF-e/NFC-e com manifesto e hash."

    def add_arguments(self, parser):
        origem = parser.add_mutually_exclusive_group(required=True)
        origem.add_argument("--arquivo", help="Caminho do ZIP oficial previamente baixado.")
        origem.add_argument("--url", help="URL HTTPS do Portal Nacional da NF-e.")
        parser.add_argument("--sha256", required=True, help="SHA-256 esperado do ZIP oficial.")
        parser.add_argument("--versao", required=True, help="Identificador controlado do pacote.")
        parser.add_argument("--arquivo-raiz", default="nfe_v4.00.xsd")
        parser.add_argument("--substituir", action="store_true", help="Substitui a mesma versão ja instalada.")

    def handle(self, *args, **options):
        esperado = options["sha256"].strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", esperado):
            raise CommandError("O SHA-256 esperado deve possuir 64 caracteres hexadecimais.")
        conteudo, origem = _ler_pacote(options["arquivo"], options["url"])
        calculado = _sha256(conteudo)
        if calculado != esperado:
            raise CommandError(f"SHA-256 do pacote diverge do esperado: {calculado}.")

        versao = _slug_versao(options["versao"])
        base = Path(settings.FISCAL_SCHEMA_DIR).resolve()
        pacotes = base / "pacotes"
        destino = pacotes / versao
        if destino.exists() and not options["substituir"]:
            raise CommandError("Esta versão ja está instalada. Use --substituir para promove-la novamente.")
        pacotes.mkdir(parents=True, exist_ok=True)

        temporario = Path(tempfile.mkdtemp(prefix=f".{versao}-", dir=pacotes))
        try:
            _extrair_seguro(conteudo, temporario)
            raiz = _localizar_raiz(temporario, options["arquivo_raiz"])
            _validar_schema(raiz)
            diretorio_schema = raiz.parent
            raiz_relativa = raiz.relative_to(temporario)
            diretorio_relativo = diretorio_schema.relative_to(temporario)
            raiz_sha256 = _sha256(raiz.read_bytes())
            manifesto = {
                "contrato": "fiscal_schema_package_v1",
                "versao": versao,
                "origem": origem,
                "pacote_sha256": calculado,
                "arquivo_raiz": raiz.name,
                "arquivo_raiz_sha256": raiz_sha256,
                "instalado_em": datetime.now(UTC).isoformat(),
                "arquivos_xsd": sorted(
                    str(item.relative_to(temporario)).replace(os.sep, "/")
                    for item in temporario.rglob("*.xsd")
                ),
            }
            (temporario / "manifesto.json").write_text(
                json.dumps(manifesto, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            if destino.exists():
                backup = pacotes / f".{versao}-anterior"
                if backup.exists():
                    shutil.rmtree(backup)
                os.replace(destino, backup)
                try:
                    os.replace(temporario, destino)
                except Exception:
                    os.replace(backup, destino)
                    raise
                shutil.rmtree(backup)
            else:
                os.replace(temporario, destino)
            temporario = None
        finally:
            if temporario and temporario.exists():
                shutil.rmtree(temporario)

        raiz_final = destino / raiz_relativa
        diretorio_final = destino / diretorio_relativo
        self.stdout.write(self.style.SUCCESS(f"Pacote fiscal {versao} instalado e validado."))
        self.stdout.write(f"FISCAL_SCHEMA_DIR={diretorio_final}")
        self.stdout.write(f"FISCAL_NFE_SCHEMA_FILE={raiz_final.name}")
        self.stdout.write(f"FISCAL_SCHEMA_SHA256={raiz_sha256}")
