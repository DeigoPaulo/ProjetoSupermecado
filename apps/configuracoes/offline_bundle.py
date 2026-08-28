import hashlib
import json
import re
import zipfile
from datetime import datetime, timezone as datetime_timezone
from pathlib import PurePosixPath

from django.conf import settings
from django.utils import timezone

from .artifacts import validar_conteudo_pacote_servidor


CONTRATO_VALIDACAO_PACOTE_OFFLINE = "detech_server_offline_package_validation_v2"
TIPOS_OBRIGATORIOS = {
    "servidor", "python-runtime", "python-wheelhouse", "postgresql", "winsw", "launcher",
    "pdv-desktop", "pdv-desktop-manifest", "admin-desktop", "admin-desktop-manifest",
}
PADRAO_VERSAO = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


def _hash_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            digest.update(bloco)
    return digest.hexdigest()


def _hash_member(archive, info):
    digest = hashlib.sha256()
    with archive.open(info) as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            digest.update(bloco)
    return digest.hexdigest()


def _safe_member(name):
    path = PurePosixPath(name.replace("\\", "/"))
    return not (path.is_absolute() or ".." in path.parts or (path.parts and ":" in path.parts[0]))


def _entry_problem(info):
    if not _safe_member(info.filename):
        return "caminho inseguro"
    if (info.external_attr >> 16) & 0o170000 == 0o120000:
        return "link simbólico"
    if info.flag_bits & 0x1:
        return "arquivo criptografado"
    if info.file_size > 10 * 1024 * 1024 and info.compress_size and info.file_size / info.compress_size > 1_000:
        return "taxa de compressão abusiva"
    return ""


def _validate_wheelhouse(archive, info):
    problems = []
    try:
        with archive.open(info) as nested, zipfile.ZipFile(nested) as wheels:
            entries = [entry for entry in wheels.infolist() if not entry.is_dir()]
            if len(entries) > 2_000 or sum(entry.file_size for entry in entries) > 4 * 1024**3:
                problems.append("Wheelhouse excede os limites seguros.")
            names = set()
            for entry in entries:
                name = entry.filename.replace("\\", "/").casefold()
                problem = _entry_problem(entry)
                if problem:
                    problems.append(f"Wheelhouse contém {problem}.")
                if name in names:
                    problems.append("Wheelhouse contém entrada duplicada.")
                names.add(name)
                if PurePosixPath(name).suffix != ".whl":
                    problems.append("Wheelhouse contém arquivo que não é pacote .whl.")
            if not entries:
                problems.append("Wheelhouse não contém pacotes .whl.")
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile):
        problems.append("Wheelhouse inválido ou ilegível.")
    return problems


def _validate_desktop(archive, manifest_info, artifact_info, label):
    try:
        metadata = json.loads(archive.read(manifest_info).decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError):
        return [f"Manifesto do {label} inválido."]
    problems = []
    if not PADRAO_VERSAO.fullmatch(str(metadata.get("version") or "").strip()):
        problems.append(f"Manifesto do {label} sem versão válida.")
    if str(metadata.get("sha256") or "").lower() != _hash_member(archive, artifact_info):
        problems.append(f"Manifesto do {label} não corresponde ao aplicativo incluído.")
    return problems


def validar_pacote_servidor_offline(path, versao_esperada):
    result = {
        "contrato": CONTRATO_VALIDACAO_PACOTE_OFFLINE,
        "caminho": path, "nome": path.name, "tamanho": 0, "sha256": "", "atualizado_em": None,
        "arquivo_encontrado": path.is_file(), "integridade_valida": False, "versao_valida": False,
        "conteudo_servidor_valido": False, "wheelhouse_valido": False,
        "componentes_obrigatorios_validos": False, "publicavel": False, "disponivel": False,
        "problemas": [],
    }
    if not result["arquivo_encontrado"]:
        result["problemas"].append("Pacote offline do servidor não encontrado.")
        return result
    if path.suffix.lower() != ".zip":
        result["problemas"].append("Formato do pacote offline não permitido; use ZIP.")
        return result

    result["sha256"] = _hash_file(path)
    stat = path.stat()
    result["tamanho"] = stat.st_size
    result["atualizado_em"] = datetime.fromtimestamp(stat.st_mtime, tz=datetime_timezone.utc)
    try:
        with zipfile.ZipFile(path) as archive:
            entries = [info for info in archive.infolist() if not info.is_dir()]
            if len(entries) > 100 or sum(info.file_size for info in entries) > 8 * 1024**3:
                result["problemas"].append("Pacote offline excede os limites seguros.")
            infos = {}
            for info in entries:
                name = info.filename.replace("\\", "/")
                key = name.casefold()
                problem = _entry_problem(info)
                if problem:
                    result["problemas"].append(f"Pacote offline contém {problem}: {name}")
                if key in infos:
                    result["problemas"].append(f"Entrada duplicada no pacote offline: {name}")
                else:
                    infos[key] = info

            manifest_info = infos.get("bundle.manifest.json")
            if not manifest_info or "install-detecserver.ps1" not in infos:
                result["problemas"].append("Estrutura obrigatória do pacote offline ausente.")
                return result
            manifest = json.loads(archive.read(manifest_info).decode("utf-8-sig"))
            if manifest.get("contrato") != "detech_server_offline_bundle_v1":
                result["problemas"].append("Contrato do pacote offline inválido.")
                return result
            if manifest.get("instalador") != "Install-DeTecServer.ps1":
                result["problemas"].append("Instalador PowerShell não corresponde ao contrato do pacote.")
            result["versao_valida"] = str(manifest.get("versao") or "") == str(versao_esperada)
            if not result["versao_valida"]:
                result["problemas"].append("Versão do pacote offline diverge da versão vigente.")

            declared, declared_paths = {}, set()
            for item in manifest.get("arquivos") or []:
                kind = str(item.get("tipo") or "").strip().casefold()
                member = str(item.get("caminho") or "").replace("\\", "/").strip().casefold()
                if not kind or kind in declared:
                    result["problemas"].append("Manifesto contém tipo ausente ou duplicado.")
                    continue
                if not member or member in declared_paths:
                    result["problemas"].append("Manifesto contém caminho ausente ou duplicado.")
                    continue
                declared[kind] = member
                declared_paths.add(member)
                info = infos.get(member)
                if not info or not _safe_member(member):
                    result["problemas"].append(f"Arquivo declarado ausente: {kind or 'componente'}")
                elif _hash_member(archive, info) != str(item.get("sha256") or "").lower() or info.file_size != item.get("tamanho_bytes"):
                    result["problemas"].append(f"Integridade inválida para {kind}.")

            missing = TIPOS_OBRIGATORIOS - set(declared)
            if missing:
                result["problemas"].append("Componentes obrigatórios ausentes: " + ", ".join(sorted(missing)))
            result["componentes_obrigatorios_validos"] = not missing
            if set(infos) - ({"bundle.manifest.json", "install-detecserver.ps1"} | declared_paths):
                result["problemas"].append("Pacote offline contém arquivo não declarado.")

            server_info = infos.get(declared.get("servidor", ""))
            if server_info:
                with archive.open(server_info) as nested:
                    validation = validar_conteudo_pacote_servidor(nested)
                result["conteudo_servidor_valido"] = validation["valido"]
                if not validation["valido"]:
                    result["problemas"].append("Conteúdo interno do servidor local inválido.")

            wheelhouse_info = infos.get(declared.get("python-wheelhouse", ""))
            if wheelhouse_info:
                problems = _validate_wheelhouse(archive, wheelhouse_info)
                result["wheelhouse_valido"] = not problems
                result["problemas"].extend(problems)

            for manifest_type, artifact_type, label in (
                ("pdv-desktop-manifest", "pdv-desktop", "DeTec PDV"),
                ("admin-desktop-manifest", "admin-desktop", "DeTec Admin"),
            ):
                manifest_entry = infos.get(declared.get(manifest_type, ""))
                artifact_entry = infos.get(declared.get(artifact_type, ""))
                if manifest_entry and artifact_entry:
                    result["problemas"].extend(_validate_desktop(archive, manifest_entry, artifact_entry, label))
            result["integridade_valida"] = not result["problemas"]
    except (OSError, UnicodeError, json.JSONDecodeError, zipfile.BadZipFile, zipfile.LargeZipFile):
        result["problemas"].append("Pacote offline inválido ou ilegível.")

    result["problemas"] = list(dict.fromkeys(result["problemas"]))
    result["publicavel"] = bool(result["integridade_valida"] and result["versao_valida"])
    result["disponivel"] = result["publicavel"]
    return result


CONTRATO_VALIDACAO_PUBLICACAO_OFFLINE = "detech_server_offline_publication_validation_v1"


def validar_publicacao_pacote_servidor_offline(path, versao_esperada):
    result = validar_pacote_servidor_offline(path, versao_esperada)
    result.update(
        {
            "contrato_publicacao": CONTRATO_VALIDACAO_PUBLICACAO_OFFLINE,
            "checksum_encontrado": False,
            "checksum_hash_valido": False,
            "checksum_nome_vinculado": False,
            "publicacao_valida": False,
        }
    )
    if not result["arquivo_encontrado"]:
        return result

    checksum_path = path.with_name(path.name + ".sha256")
    result["checksum_encontrado"] = checksum_path.is_file()
    if not result["checksum_encontrado"]:
        result["problemas"].append("Arquivo SHA-256 publicado não encontrado.")
    else:
        try:
            checksum_text = checksum_path.read_text(encoding="utf-8-sig").strip()
            match = re.fullmatch(r"([A-Fa-f0-9]{64}) {2}([^\r\n]+)", checksum_text)
            if not match:
                result["problemas"].append("Arquivo SHA-256 publicado inválido.")
            else:
                result["checksum_hash_valido"] = match.group(1).lower() == result["sha256"]
                result["checksum_nome_vinculado"] = match.group(2) == path.name
                if not result["checksum_hash_valido"]:
                    result["problemas"].append("SHA-256 publicado diverge do pacote offline.")
                if not result["checksum_nome_vinculado"]:
                    result["problemas"].append("SHA-256 publicado está vinculado a outro arquivo.")
        except (OSError, UnicodeError):
            result["problemas"].append("Arquivo SHA-256 publicado inválido.")

    result["problemas"] = list(dict.fromkeys(result["problemas"]))
    result["publicacao_valida"] = bool(
        result["publicavel"]
        and result["checksum_encontrado"]
        and result["checksum_hash_valido"]
        and result["checksum_nome_vinculado"]
    )
    result["integridade_valida"] = result["integridade_valida"] and result["publicacao_valida"]
    result["publicavel"] = result["publicacao_valida"]
    result["disponivel"] = result["publicacao_valida"]
    return result


def artefato_servidor_offline():
    return validar_publicacao_pacote_servidor_offline(
        settings.LOCAL_SERVER_OFFLINE_PACKAGE_PATH,
        settings.LOCAL_SERVER_VERSION,
    )
