import hashlib
import json
import os
import re
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from cryptography.hazmat.primitives import hashes, padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

CONTRATO_VALIDACAO = "local_backup_package_validation_v1"
CONTRATO_BACKUP = "erp_local_backup_v2"
CONTRATO_ANCORA = "fiscal_evidence_anchor_v1"
SHA_RE = re.compile(r"^[0-9a-fA-F]{64}$")


class BackupInvalido(Exception):
    def __init__(self, codigo):
        self.codigo = codigo
        super().__init__(codigo)


def _sha256(caminho):
    digest = hashlib.sha256()
    with Path(caminho).open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            digest.update(bloco)
    return digest.hexdigest()


def _validar_checksum(caminho):
    sidecar = Path(f"{caminho}.sha256")
    if not sidecar.is_file():
        raise BackupInvalido("checksum_ausente")
    try:
        partes = sidecar.read_text(encoding="ascii").strip().split()
    except (OSError, UnicodeError):
        raise BackupInvalido("checksum_invalido") from None
    if not partes or len(partes) > 2 or not SHA_RE.fullmatch(partes[0]):
        raise BackupInvalido("checksum_invalido")
    if len(partes) == 2 and partes[1].lstrip("*") != Path(caminho).name:
        raise BackupInvalido("checksum_arquivo_divergente")
    if _sha256(caminho).casefold() != partes[0].casefold():
        raise BackupInvalido("checksum_divergente")


def _descriptografar(caminho, destino, senha):
    with Path(caminho).open("rb") as origem:
        if origem.read(9) != b"MFLOWAES1":
            raise BackupInvalido("criptografia_cabecalho_invalido")
        salt, iv = origem.read(16), origem.read(16)
        if len(salt) != 16 or len(iv) != 16:
            raise BackupInvalido("criptografia_incompleta")
        chave = PBKDF2HMAC(
            algorithm=hashes.SHA256(), length=32, salt=salt, iterations=200_000
        ).derive(senha.encode("utf-8"))
        decryptor = Cipher(algorithms.AES(chave), modes.CBC(iv)).decryptor()
        unpadder = padding.PKCS7(128).unpadder()
        try:
            with Path(destino).open("wb") as saida:
                for bloco in iter(lambda: origem.read(1024 * 1024), b""):
                    saida.write(unpadder.update(decryptor.update(bloco)))
                final = decryptor.finalize()
                saida.write(unpadder.update(final) + unpadder.finalize())
        except (OSError, ValueError):
            Path(destino).unlink(missing_ok=True)
            raise BackupInvalido("criptografia_recusada") from None


def _nome_seguro(nome):
    nome = nome.replace("\\", "/")
    return bool(
        nome
        and not nome.startswith("/")
        and not re.match(r"^[A-Za-z]:", nome)
        and ".." not in PurePosixPath(nome).parts
    )


def _ler_json(arquivo, nome, codigo):
    try:
        info = arquivo.getinfo(nome)
        if info.file_size > 1024**2:
            raise BackupInvalido(codigo)
        return json.loads(arquivo.read(info).decode("utf-8"))
    except BackupInvalido:
        raise
    except (KeyError, UnicodeError, json.JSONDecodeError, RuntimeError, zipfile.BadZipFile):
        raise BackupInvalido(codigo) from None


def _validar_zip(caminho):
    try:
        with zipfile.ZipFile(caminho) as arquivo:
            entradas = arquivo.infolist()
            if len(entradas) > 100_000:
                raise BackupInvalido("estrutura_limite_entradas")
            nomes, total = set(), 0
            for entrada in entradas:
                nome = entrada.filename.replace("\\", "/")
                chave = nome.casefold()
                if not _nome_seguro(nome) or chave in nomes:
                    raise BackupInvalido("estrutura_caminho_inseguro")
                nomes.add(chave)
                if entrada.flag_bits & 0x1:
                    raise BackupInvalido("estrutura_entrada_criptografada")
                if (entrada.external_attr >> 16) & 0o170000 == 0o120000:
                    raise BackupInvalido("estrutura_link_inseguro")
                if entrada.file_size > 5 * 1024**3:
                    raise BackupInvalido("estrutura_limite_arquivo")
                total += entrada.file_size
                if total > 100 * 1024**3:
                    raise BackupInvalido("estrutura_limite_expandido")
            if arquivo.testzip() is not None:
                raise BackupInvalido("estrutura_crc_invalido")

            manifesto = _ler_json(arquivo, "manifesto.json", "manifesto_invalido")
            if manifesto.get("contrato") != CONTRATO_BACKUP:
                raise BackupInvalido("contrato_incompativel")
            if manifesto.get("inclui_dados_json") is not True or "dados.json" not in nomes:
                raise BackupInvalido("dados_logicos_ausentes")
            tipo = manifesto.get("banco_tipo")
            if not tipo:
                tipo = "sqlite" if manifesto.get("inclui_sqlite") is True else (
                    "postgresql" if manifesto.get("inclui_postgresql") is True else ""
                )
            if tipo == "sqlite":
                if (
                    manifesto.get("inclui_sqlite") is not True
                    or manifesto.get("sqlite_snapshot_consistente") is not True
                    or "db.sqlite3" not in nomes
                ):
                    raise BackupInvalido("banco_sqlite_ausente")
            elif tipo == "postgresql":
                if (
                    manifesto.get("inclui_postgresql") is not True
                    or manifesto.get("postgresql_dump_formato") != "custom"
                    or "database.dump" not in nomes
                ):
                    raise BackupInvalido("banco_postgresql_ausente")
            else:
                raise BackupInvalido("banco_tipo_invalido")

            ancora_valida = False
            if manifesto.get("inclui_ancora_evidencias_fiscais") is True:
                nome = manifesto.get("evidencias_fiscais_arquivo")
                if (
                    manifesto.get("evidencias_fiscais_contrato") != CONTRATO_ANCORA
                    or not isinstance(nome, str)
                    or PurePosixPath(nome).name != nome
                    or nome.casefold() not in nomes
                ):
                    raise BackupInvalido("ancora_fiscal_ausente")
                if arquivo.getinfo(nome).file_size > 1024**2:
                    raise BackupInvalido("ancora_fiscal_invalida")
                conteudo = arquivo.read(nome)
                esperado = str(manifesto.get("evidencias_fiscais_sha256") or "")
                if (
                    not SHA_RE.fullmatch(esperado)
                    or hashlib.sha256(conteudo).hexdigest().casefold() != esperado.casefold()
                ):
                    raise BackupInvalido("ancora_fiscal_checksum_divergente")
                ancora = _ler_json(arquivo, nome, "ancora_fiscal_invalida")
                if (
                    ancora.get("contrato") != CONTRATO_ANCORA
                    or ancora.get("integra") is not True
                    or not ancora.get("ancora_global_sha256")
                ):
                    raise BackupInvalido("ancora_fiscal_invalida")
                ancora_valida = True
            if manifesto.get("inclui_media") is True and not any(
                nome.startswith("media/") for nome in nomes
            ):
                raise BackupInvalido("midia_ausente")
            return tipo, ancora_valida
    except BackupInvalido:
        raise
    except (OSError, RuntimeError, zipfile.BadZipFile, zipfile.LargeZipFile):
        raise BackupInvalido("estrutura_zip_invalida") from None


def validar_pacote_backup(caminho, *, senha=None):
    caminho = Path(caminho)
    criptografado = caminho.name.casefold().endswith(".zip.aes")
    resultado = {
        "contrato": CONTRATO_VALIDACAO,
        "validado": False,
        "checksum_encontrado": Path(f"{caminho}.sha256").is_file(),
        "sha256_valido": False,
        "conteudo_validado": False,
        "backup_contrato": "",
        "estrutura_valida": False,
        "ancora_fiscal_valida": False,
        "criptografado": criptografado,
        "banco_tipo": "",
        "codigo": "pacote_invalido",
        "caminho_exposto": False,
        "segredo_exposto": False,
    }
    try:
        if not caminho.is_file() or not (
            caminho.name.casefold().endswith(".zip") or criptografado
        ):
            raise BackupInvalido("pacote_invalido")
        _validar_checksum(caminho)
        resultado["sha256_valido"] = True
        arquivo_zip = caminho
        with tempfile.TemporaryDirectory(prefix="deigo-backup-validation-") as temporario:
            if criptografado:
                senha = senha if senha is not None else os.getenv(
                    "BACKUP_ENCRYPTION_PASSPHRASE", ""
                )
                if not senha:
                    raise BackupInvalido("senha_criptografia_indisponivel")
                arquivo_zip = Path(temporario) / "backup.zip"
                _descriptografar(caminho, arquivo_zip, senha)
            tipo, ancora_valida = _validar_zip(arquivo_zip)
        resultado.update(
            validado=True,
            conteudo_validado=True,
            backup_contrato=CONTRATO_BACKUP,
            estrutura_valida=True,
            ancora_fiscal_valida=ancora_valida,
            banco_tipo=tipo,
            codigo="valido",
        )
    except BackupInvalido as exc:
        resultado["codigo"] = exc.codigo
    except OSError:
        resultado["codigo"] = "erro_leitura"
    return resultado