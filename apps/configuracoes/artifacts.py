import hashlib
import json
import re

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


def artefato_servidor_local():
    caminho = settings.LOCAL_SERVER_PACKAGE_PATH
    metadados_caminho = caminho.with_suffix(".manifest.json")
    resultado = {
        "caminho": caminho,
        "manifesto_caminho": metadados_caminho,
        "nome": caminho.name,
        "tamanho": 0,
        "sha256": "",
        "atualizado_em": None,
        "arquivo_encontrado": caminho.is_file(),
        "metadados_encontrados": metadados_caminho.is_file(),
        "metadados": {},
        "integridade_valida": False,
        "tamanho_valido": False,
        "versao_valida": False,
        "origem_rastreavel": False,
        "sem_dados_cliente": False,
        "assinatura_commit_exigida": settings.LOCAL_SERVER_REQUIRE_SIGNED_COMMIT,
        "assinatura_commit_confirmada": False,
        "publicavel": False,
        "disponivel": False,
        "problemas": [],
    }
    if not resultado["arquivo_encontrado"]:
        resultado["problemas"].append("Pacote do servidor local nao encontrado.")
        return resultado
    if caminho.suffix.lower() != ".zip":
        resultado["problemas"].append("Formato do servidor local nao permitido; use ZIP.")

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
    if not resultado["metadados_encontrados"]:
        resultado["problemas"].append("Manifesto .manifest.json do servidor local nao encontrado.")
        return resultado
    try:
        metadados = json.loads(metadados_caminho.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        resultado["problemas"].append("Manifesto .manifest.json do servidor local invalido.")
        return resultado
    resultado["metadados"] = metadados

    if metadados.get("contrato") != "local_server_package_v1":
        resultado["problemas"].append("Contrato do pacote do servidor local invalido.")
    hash_declarado = str(metadados.get("sha256") or "").lower()
    resultado["integridade_valida"] = bool(hash_declarado and hash_declarado == resultado["sha256"])
    if not resultado["integridade_valida"]:
        resultado["problemas"].append("SHA-256 do servidor local diverge do manifesto.")
    resultado["tamanho_valido"] = metadados.get("tamanho_bytes") == resultado["tamanho"]
    if not resultado["tamanho_valido"]:
        resultado["problemas"].append("Tamanho do servidor local diverge do manifesto.")

    versao_declarada = str(metadados.get("versao") or "")
    resultado["versao_valida"] = versao_declarada == settings.LOCAL_SERVER_VERSION
    if not resultado["versao_valida"]:
        resultado["problemas"].append(
            f"Versao do pacote ({versao_declarada or 'ausente'}) diverge da versao vigente ({settings.LOCAL_SERVER_VERSION})."
        )
    commit = str(metadados.get("commit") or "")
    arquivo_declarado = str(metadados.get("arquivo") or "")
    resultado["origem_rastreavel"] = bool(re.fullmatch(r"[0-9a-fA-F]{40}", commit) and arquivo_declarado == caminho.name)
    if not resultado["origem_rastreavel"]:
        resultado["problemas"].append("Commit ou nome do arquivo nao permitem rastrear a origem do pacote.")

    resultado["sem_dados_cliente"] = metadados.get("contem_dados_cliente") is False
    if not resultado["sem_dados_cliente"]:
        resultado["problemas"].append("O manifesto nao confirma a ausencia de dados do cliente.")
    resultado["assinatura_commit_confirmada"] = metadados.get("commit_assinado_exigido") is True
    if resultado["assinatura_commit_exigida"] and not resultado["assinatura_commit_confirmada"]:
        resultado["problemas"].append("O pipeline nao confirmou commit Git assinado para este pacote.")

    resultado["publicavel"] = bool(
        caminho.suffix.lower() == ".zip"
        and metadados.get("contrato") == "local_server_package_v1"
        and resultado["integridade_valida"]
        and resultado["tamanho_valido"]
        and resultado["versao_valida"]
        and resultado["origem_rastreavel"]
        and resultado["sem_dados_cliente"]
        and (resultado["assinatura_commit_confirmada"] or not resultado["assinatura_commit_exigida"])
    )
    resultado["disponivel"] = resultado["publicavel"]
    return resultado
