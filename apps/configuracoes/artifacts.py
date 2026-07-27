import hashlib
import json

from django.conf import settings
from django.utils import timezone


def artefato_pdv_desktop():
    caminho = settings.PDV_DESKTOP_INSTALLER_PATH
    metadados_caminho = caminho.with_name(caminho.name + ".version.json")
    resultado = {
        "caminho": caminho,
        "nome": caminho.name,
        "tamanho": 0,
        "sha256": "",
        "atualizado_em": None,
        "arquivo_encontrado": caminho.is_file(),
        "metadados_encontrados": metadados_caminho.is_file(),
        "metadados": {},
        "integridade_valida": False,
        "versao_valida": False,
        "assinatura_valida": False,
        "assinatura_exigida": settings.PDV_DESKTOP_REQUIRE_SIGNED_INSTALLER,
        "publicavel": False,
        "disponivel": False,
        "problemas": [],
    }
    if not resultado["arquivo_encontrado"]:
        resultado["problemas"].append("Artefato do PDV desktop nao encontrado.")
        return resultado

    digest = hashlib.sha256()
    with caminho.open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            digest.update(bloco)
    stat = caminho.stat()
    resultado.update(
        {
            "tamanho": stat.st_size,
            "sha256": digest.hexdigest(),
            "atualizado_em": timezone.datetime.fromtimestamp(stat.st_mtime, tz=timezone.get_current_timezone()),
        }
    )

    if caminho.suffix.lower() not in {".msi", ".exe"}:
        resultado["problemas"].append("Formato de instalador nao permitido; use MSI ou EXE.")
    if not resultado["metadados_encontrados"]:
        resultado["problemas"].append("Manifesto .version.json do instalador nao encontrado.")
        return resultado
    try:
        metadados = json.loads(metadados_caminho.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        resultado["problemas"].append("Manifesto .version.json invalido.")
        return resultado
    resultado["metadados"] = metadados

    hash_declarado = str(metadados.get("sha256") or "").lower()
    resultado["integridade_valida"] = bool(hash_declarado and hash_declarado == resultado["sha256"])
    if not resultado["integridade_valida"]:
        resultado["problemas"].append("SHA-256 do instalador diverge do manifesto.")

    versao_declarada = str(metadados.get("version") or "")
    resultado["versao_valida"] = versao_declarada == settings.PDV_DESKTOP_VERSION
    if not resultado["versao_valida"]:
        resultado["problemas"].append(
            f"Versao do manifesto ({versao_declarada or 'ausente'}) diverge da versao vigente ({settings.PDV_DESKTOP_VERSION})."
        )

    assinatura_msi = str(metadados.get("msi_signature") or "")
    assinatura_exe = str(metadados.get("executable_signature") or "")
    if caminho.suffix.lower() == ".msi":
        resultado["assinatura_valida"] = assinatura_msi == "Valid" and assinatura_exe == "Valid"
    else:
        resultado["assinatura_valida"] = assinatura_exe == "Valid"
    if resultado["assinatura_exigida"] and not resultado["assinatura_valida"]:
        resultado["problemas"].append("Assinatura digital valida e obrigatoria nao confirmada no manifesto.")

    resultado["publicavel"] = bool(
        resultado["integridade_valida"]
        and resultado["versao_valida"]
        and caminho.suffix.lower() in {".msi", ".exe"}
        and (resultado["assinatura_valida"] or not resultado["assinatura_exigida"])
    )
    resultado["disponivel"] = resultado["publicavel"]
    return resultado
