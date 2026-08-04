import hashlib
import json
import re
import zipfile
from pathlib import PurePosixPath

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
        resultado["problemas"].append("Artefato do PDV desktop não encontrado.")
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
        resultado["problemas"].append("Formato de instalador não permitido; use MSI ou EXE.")
    if not resultado["metadados_encontrados"]:
        resultado["problemas"].append("Manifesto .version.json do instalador não encontrado.")
        return resultado
    try:
        metadados = json.loads(metadados_caminho.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        resultado["problemas"].append("Manifesto .version.json inválido.")
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
        resultado["problemas"].append("Assinatura digital valida e obrigatória não confirmada no manifesto.")

    resultado["publicavel"] = bool(
        resultado["integridade_valida"]
        and resultado["versao_valida"]
        and caminho.suffix.lower() in {".msi", ".exe"}
        and (resultado["assinatura_valida"] or not resultado["assinatura_exigida"])
    )
    resultado["disponivel"] = resultado["publicavel"]
    return resultado


PACOTE_SERVIDOR_ARQUIVOS_OBRIGATORIOS = {
    "manage.py",
    "requirements.txt",
    "config/settings.py",
}
PACOTE_SERVIDOR_SEGMENTOS_PROIBIDOS = {
    ".git", ".venv", "venv", "__pycache__", "artifacts", "backups",
    "dist", "logs", "media", "node_modules",
}
PACOTE_SERVIDOR_NOMES_PROIBIDOS = {".env", "db.sqlite3"}
PACOTE_SERVIDOR_EXTENSOES_PROIBIDAS = {".db", ".key", ".p12", ".pem", ".pfx", ".sqlite", ".sqlite3"}
PACOTE_SERVIDOR_DOCUMENTOS_INTERNOS = {"prototipos", "protótipos", "referencias"}
PACOTE_SERVIDOR_TESTES_NOMES = {"conftest.py", "tests.py"}


def _arquivo_teste_interno(caminho_zip):
    nome = caminho_zip.name.casefold()
    partes = {parte.casefold() for parte in caminho_zip.parts}
    return caminho_zip.suffix.casefold() == ".py" and (
        nome in PACOTE_SERVIDOR_TESTES_NOMES
        or nome.startswith("test_")
        or nome.endswith("_test.py")
        or "tests" in partes
    )


def _documento_interno(caminho_zip):
    partes = [parte.casefold() for parte in caminho_zip.parts]
    if not partes or partes[0] != "docs":
        return False
    if len(partes) > 1 and partes[1] in PACOTE_SERVIDOR_DOCUMENTOS_INTERNOS:
        return True
    return len(partes) == 2 and caminho_zip.suffix.casefold() == ".docx"



def validar_conteudo_pacote_servidor(caminho):
    resultado = {
        "contrato": "local_server_package_content_v1",
        "valido": False,
        "arquivos": 0,
        "tamanho_descompactado": 0,
        "problemas": [],
    }
    try:
        with zipfile.ZipFile(caminho) as pacote:
            infos = pacote.infolist()
            resultado["arquivos"] = len(infos)
            resultado["tamanho_descompactado"] = sum(info.file_size for info in infos)
            if len(infos) > 20_000:
                resultado["problemas"].append("Pacote excede o limite de 20.000 entradas.")
            if resultado["tamanho_descompactado"] > 2 * 1024 * 1024 * 1024:
                resultado["problemas"].append("Pacote excede 2 GB após descompactação.")

            nomes = set()
            nomes_sem_caixa = set()
            for info in infos:
                nome = info.filename.replace("\\", "/")
                caminho_zip = PurePosixPath(nome)
                partes = [parte.casefold() for parte in caminho_zip.parts]
                if (
                    caminho_zip.is_absolute()
                    or ".." in caminho_zip.parts
                    or (caminho_zip.parts and ":" in caminho_zip.parts[0])
                ):
                    resultado["problemas"].append(f"Caminho inseguro no pacote: {nome}")
                    continue
                modo_unix = info.external_attr >> 16
                if modo_unix & 0o170000 == 0o120000:
                    resultado["problemas"].append(f"Link simbólico não permitido no pacote: {nome}")
                if info.flag_bits & 0x1:
                    resultado["problemas"].append(f"Arquivo criptografado não permitido: {nome}")
                if info.is_dir():
                    continue
                nome_normalizado = caminho_zip.as_posix().lstrip("./")
                nome_sem_caixa = nome_normalizado.casefold()
                if nome_sem_caixa in nomes_sem_caixa:
                    resultado["problemas"].append(f"Entrada duplicada no pacote: {nome}")
                nomes.add(nome_normalizado)
                nomes_sem_caixa.add(nome_sem_caixa)
                if info.file_size > 10 * 1024 * 1024 and info.compress_size and info.file_size / info.compress_size > 1_000:
                    resultado["problemas"].append(f"Taxa de compressão abusiva no pacote: {nome}")
                nome_base = caminho_zip.name.casefold()
                if PACOTE_SERVIDOR_SEGMENTOS_PROIBIDOS.intersection(partes):
                    resultado["problemas"].append(f"Diretório proibido no pacote: {nome}")
                if nome_base in PACOTE_SERVIDOR_NOMES_PROIBIDOS:
                    resultado["problemas"].append(f"Arquivo de dados ou segredo proibido: {nome}")
                if caminho_zip.suffix.casefold() in PACOTE_SERVIDOR_EXTENSOES_PROIBIDAS:
                    resultado["problemas"].append(f"Extensão sensível proibida no pacote: {nome}")
                if _arquivo_teste_interno(caminho_zip):
                    resultado["problemas"].append(f"Teste interno proibido no pacote comercial: {nome}")
                if _documento_interno(caminho_zip):
                    resultado["problemas"].append(f"Documentação interna proibida no pacote comercial: {nome}")

            ausentes = sorted(PACOTE_SERVIDOR_ARQUIVOS_OBRIGATORIOS - nomes)
            if ausentes:
                resultado["problemas"].append("Estrutura mínima ausente: " + ", ".join(ausentes))
            if not any(nome.startswith("apps/") and nome.endswith(".py") for nome in nomes):
                resultado["problemas"].append("Aplicações Django não encontradas no pacote.")
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile):
        resultado["problemas"].append("ZIP do servidor local inválido ou ilegível.")

    resultado["problemas"] = list(dict.fromkeys(resultado["problemas"]))
    resultado["valido"] = not resultado["problemas"]
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
        "conteudo_valido": False,
        "diagnostico_conteudo": {},
        "assinatura_commit_exigida": settings.LOCAL_SERVER_REQUIRE_SIGNED_COMMIT,
        "assinatura_commit_confirmada": False,
        "publicavel": False,
        "disponivel": False,
        "problemas": [],
    }
    if not resultado["arquivo_encontrado"]:
        resultado["problemas"].append("Pacote do servidor local não encontrado.")
        return resultado
    if caminho.suffix.lower() != ".zip":
        resultado["problemas"].append("Formato do servidor local não permitido; use ZIP.")

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
        resultado["problemas"].append("Manifesto .manifest.json do servidor local não encontrado.")
        return resultado
    try:
        metadados = json.loads(metadados_caminho.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        resultado["problemas"].append("Manifesto .manifest.json do servidor local inválido.")
        return resultado
    resultado["metadados"] = metadados

    if metadados.get("contrato") != "local_server_package_v1":
        resultado["problemas"].append("Contrato do pacote do servidor local inválido.")
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
        resultado["problemas"].append("Commit ou nome do arquivo não permitem rastrear a origem do pacote.")

    resultado["sem_dados_cliente"] = metadados.get("contem_dados_cliente") is False
    if not resultado["sem_dados_cliente"]:
        resultado["problemas"].append("O manifesto não confirma a ausencia de dados do cliente.")
    diagnostico_conteudo = validar_conteudo_pacote_servidor(caminho)
    resultado["diagnostico_conteudo"] = diagnostico_conteudo
    resultado["conteudo_valido"] = diagnostico_conteudo["valido"]
    resultado["problemas"].extend(diagnostico_conteudo["problemas"])
    resultado["assinatura_commit_confirmada"] = metadados.get("commit_assinado_exigido") is True
    if resultado["assinatura_commit_exigida"] and not resultado["assinatura_commit_confirmada"]:
        resultado["problemas"].append("O pipeline não confirmou commit Git assinado para este pacote.")

    resultado["publicavel"] = bool(
        caminho.suffix.lower() == ".zip"
        and metadados.get("contrato") == "local_server_package_v1"
        and resultado["integridade_valida"]
        and resultado["tamanho_valido"]
        and resultado["versao_valida"]
        and resultado["origem_rastreavel"]
        and resultado["sem_dados_cliente"]
        and resultado["conteudo_valido"]
        and (resultado["assinatura_commit_confirmada"] or not resultado["assinatura_commit_exigida"])
    )
    resultado["disponivel"] = resultado["publicavel"]
    return resultado
