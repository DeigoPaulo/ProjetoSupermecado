import hashlib
import json
import zipfile
from pathlib import PurePosixPath

from django.conf import settings
from django.utils import timezone


def _hash_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            digest.update(bloco)
    return digest.hexdigest()


def _safe_member(name):
    path = PurePosixPath(name.replace("\\", "/"))
    return not (path.is_absolute() or ".." in path.parts or (path.parts and ":" in path.parts[0]))


def artefato_servidor_offline():
    path = settings.LOCAL_SERVER_OFFLINE_PACKAGE_PATH
    result = {
        "caminho": path,
        "nome": path.name,
        "tamanho": 0,
        "sha256": "",
        "atualizado_em": None,
        "arquivo_encontrado": path.is_file(),
        "integridade_valida": False,
        "versao_valida": False,
        "publicavel": False,
        "disponivel": False,
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
    result["atualizado_em"] = timezone.datetime.fromtimestamp(stat.st_mtime, tz=timezone.get_current_timezone())
    try:
        with zipfile.ZipFile(path) as archive:
            infos = {info.filename.replace("\\", "/"): info for info in archive.infolist() if not info.is_dir()}
            if "bundle.manifest.json" not in infos or "Install-DeTecServer.ps1" not in infos:
                result["problemas"].append("Estrutura obrigatória do pacote offline ausente.")
                return result
            if any(not _safe_member(name) for name in infos):
                result["problemas"].append("O pacote offline contém caminho inseguro.")
                return result
            manifest = json.loads(archive.read("bundle.manifest.json").decode("utf-8-sig"))
            if manifest.get("contrato") != "detech_server_offline_bundle_v1":
                result["problemas"].append("Contrato do pacote offline inválido.")
                return result
            result["versao_valida"] = str(manifest.get("versao") or "") == settings.LOCAL_SERVER_VERSION
            if not result["versao_valida"]:
                result["problemas"].append("Versão do pacote offline diverge da versão vigente.")
            required_types = {"servidor", "python-runtime", "postgresql", "winsw"}
            declared_types = set()
            for item in manifest.get("arquivos") or []:
                item_type = str(item.get("tipo") or "")
                member = str(item.get("caminho") or "").replace("\\", "/")
                declared_types.add(item_type)
                info = infos.get(member)
                if not info or not _safe_member(member):
                    result["problemas"].append(f"Arquivo declarado ausente: {member or item_type}")
                    continue
                digest = hashlib.sha256(archive.read(member)).hexdigest()
                if digest != str(item.get("sha256") or "").lower() or info.file_size != item.get("tamanho_bytes"):
                    result["problemas"].append(f"Integridade inválida para {item_type or member}.")
            missing = required_types - declared_types
            if missing:
                result["problemas"].append("Componentes obrigatórios ausentes: " + ", ".join(sorted(missing)))
            result["integridade_valida"] = not result["problemas"]
    except (OSError, UnicodeError, json.JSONDecodeError, zipfile.BadZipFile, zipfile.LargeZipFile):
        result["problemas"].append("Pacote offline inválido ou ilegível.")

    result["publicavel"] = bool(result["integridade_valida"] and result["versao_valida"])
    result["disponivel"] = result["publicavel"]
    return result
