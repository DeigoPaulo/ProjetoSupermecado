"""Build, validate and apply compiled-module overlays for local-server releases."""

from __future__ import annotations

import argparse
import hashlib
import importlib.machinery
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath


CONTRACT = "local_server_protected_modules_v1"
DEFAULT_MODULES = ("apps.licenciamento.services",)


class ProtectionError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def module_source(root: Path, module: str) -> Path:
    if not module or any(not part.isidentifier() for part in module.split(".")):
        raise ProtectionError(f"Nome de modulo invalido: {module!r}")
    source = root.joinpath(*module.split(".")).with_suffix(".py")
    if not source.is_file() or root.resolve() not in source.resolve().parents:
        raise ProtectionError(f"Fonte do modulo nao encontrado: {module}")
    return source


def runtime_identity() -> dict[str, str]:
    return {
        "implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "python_cache_tag": sys.implementation.cache_tag or "",
        "platform": sys.platform,
        "machine": platform.machine(),
    }


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build(root: Path, output: Path, modules: list[str], commit: str) -> Path:
    try:
        import nuitka  # noqa: F401
    except ImportError as exc:
        raise ProtectionError(
            "Nuitka nao instalado. Execute: python -m pip install -r requirements-build.txt"
        ) from exc

    output.mkdir(parents=True, exist_ok=True)
    records = []
    with tempfile.TemporaryDirectory(prefix="deigo-protected-") as temp_name:
        temp = Path(temp_name)
        for module in modules:
            source = module_source(root, module)
            module_output = temp / module.replace(".", "_")
            module_output.mkdir()
            command = [
                sys.executable,
                "-m",
                "nuitka",
                "--mode=module",
                "--assume-yes-for-downloads",
                "--remove-output",
                f"--output-dir={module_output}",
                str(source),
            ]
            subprocess.run(command, cwd=root, check=True)
            candidates = [
                path
                for path in module_output.iterdir()
                if path.is_file() and any(path.name.endswith(suffix) for suffix in importlib.machinery.EXTENSION_SUFFIXES)
            ]
            if len(candidates) != 1:
                raise ProtectionError(f"Nuitka nao gerou uma extensao unica para {module}.")
            binary = candidates[0]
            relative_binary = PurePosixPath(*module.split(".")[:-1], binary.name)
            destination = output / Path(*relative_binary.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(binary, destination)
            records.append(
                {
                    "module": module,
                    "source": source.relative_to(root).as_posix(),
                    "source_sha256": sha256(source),
                    "binary": relative_binary.as_posix(),
                    "binary_sha256": sha256(destination),
                    "binary_size": destination.stat().st_size,
                }
            )

    manifest = output / "protected-modules.manifest.json"
    _write_json(
        manifest,
        {
            "contract": CONTRACT,
            "commit": commit,
            "runtime": runtime_identity(),
            "modules": records,
        },
    )
    validate(root, output, commit=commit, require_sources=True)
    return manifest


def _safe_relative(value: str) -> PurePosixPath:
    path = PurePosixPath(value.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or not path.parts or ":" in path.parts[0]:
        raise ProtectionError(f"Caminho inseguro no manifesto: {value}")
    return path


def validate(root: Path, overlay: Path, commit: str | None = None, require_sources: bool = True) -> dict:
    manifest_path = overlay / "protected-modules.manifest.json"
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProtectionError("Manifesto dos modulos protegidos ausente ou invalido.") from exc
    if payload.get("contract") != CONTRACT:
        raise ProtectionError("Contrato dos modulos protegidos invalido.")
    if commit and payload.get("commit") != commit:
        raise ProtectionError("Overlay protegido pertence a outro commit.")
    if payload.get("runtime") != runtime_identity():
        raise ProtectionError("Overlay protegido pertence a outro Python, ABI ou plataforma.")

    records = payload.get("modules")
    if not isinstance(records, list) or not records:
        raise ProtectionError("Manifesto protegido nao contem modulos.")
    seen_modules: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            raise ProtectionError("Registro de modulo protegido invalido.")
        module = str(record.get("module") or "")
        if module in seen_modules:
            raise ProtectionError(f"Modulo protegido duplicado: {module}")
        seen_modules.add(module)
        expected_source = module_source(root, module) if require_sources else None
        source_relative = _safe_relative(str(record.get("source") or ""))
        binary_relative = _safe_relative(str(record.get("binary") or ""))
        if source_relative.suffix != ".py" or binary_relative.parent != source_relative.parent:
            raise ProtectionError(f"Destino compilado invalido para {module}.")
        if not any(binary_relative.name.endswith(suffix) for suffix in importlib.machinery.EXTENSION_SUFFIXES):
            raise ProtectionError(f"Extensao compilada incompativel para {module}.")
        binary = overlay / Path(*binary_relative.parts)
        if not binary.is_file() or sha256(binary) != record.get("binary_sha256"):
            raise ProtectionError(f"Binario protegido ausente ou adulterado: {module}")
        if binary.stat().st_size != record.get("binary_size"):
            raise ProtectionError(f"Tamanho do binario protegido diverge: {module}")
        if expected_source is not None:
            if expected_source.relative_to(root).as_posix() != source_relative.as_posix():
                raise ProtectionError(f"Fonte declarada incorreta: {module}")
            if sha256(expected_source) != record.get("source_sha256"):
                raise ProtectionError(f"Fonte alterada depois da compilacao: {module}")
    return payload


def apply(root: Path, archive: Path, overlay: Path, commit: str) -> None:
    payload = validate(root, overlay, commit=commit, require_sources=True)
    source_names = {record["source"] for record in payload["modules"]}
    additions = {
        record["binary"]: overlay / Path(*PurePosixPath(record["binary"]).parts)
        for record in payload["modules"]
    }
    additions["protected-modules.manifest.json"] = overlay / "protected-modules.manifest.json"
    temporary = archive.with_suffix(archive.suffix + ".protected")
    try:
        with zipfile.ZipFile(archive, "r") as source_zip, zipfile.ZipFile(
            temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
        ) as target_zip:
            for info in source_zip.infolist():
                name = info.filename.replace("\\", "/")
                if name in source_names:
                    continue
                if name in additions or name == "protected-modules.manifest.json":
                    raise ProtectionError(f"Entrada protegida duplicada no pacote: {name}")
                target_zip.writestr(info, source_zip.read(info))
            # Source presence is checked directly because it is intentionally omitted above.
            archived_names = {info.filename.replace("\\", "/") for info in source_zip.infolist()}
            if not source_names.issubset(archived_names):
                raise ProtectionError("O pacote base nao contem todos os fontes que seriam substituidos.")
            records_by_source = {record["source"]: record for record in payload["modules"]}
            for source_name, record in records_by_source.items():
                archived_hash = hashlib.sha256(source_zip.read(source_name)).hexdigest()
                if archived_hash != record["source_sha256"]:
                    raise ProtectionError(f"Fonte do pacote diverge do overlay protegido: {source_name}")
            for name, path in additions.items():
                target_zip.write(path, name)
        os.replace(temporary, archive)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("build", "validate", "apply"))
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--overlay", type=Path, required=True)
    parser.add_argument("--commit")
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--module", action="append", dest="modules")
    args = parser.parse_args()
    root = args.root.resolve()
    overlay = args.overlay.resolve()
    try:
        if args.command == "build":
            if not args.commit:
                raise ProtectionError("Informe --commit no build.")
            manifest = build(root, overlay, args.modules or list(DEFAULT_MODULES), args.commit)
            print(manifest)
        elif args.command == "validate":
            print(json.dumps(validate(root, overlay, args.commit), ensure_ascii=False))
        else:
            if not args.archive or not args.commit:
                raise ProtectionError("Informe --archive e --commit ao aplicar o overlay.")
            apply(root, args.archive.resolve(), overlay, args.commit)
            print(args.archive.resolve())
    except (ProtectionError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
