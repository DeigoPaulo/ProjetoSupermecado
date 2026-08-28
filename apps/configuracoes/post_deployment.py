import os
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from django.conf import settings

from .backup_operacional import politica_periodicidade_backup
from .backup_validation import validar_pacote_backup
from .readiness import diagnostico_prontidao_banco_dados


def _diretorio_gravavel(caminho):
    caminho = Path(caminho)
    if not caminho.is_dir():
        return False
    teste = caminho / f".deigo-health-{uuid.uuid4().hex}.tmp"
    try:
        teste.write_bytes(b"")
        return True
    except OSError:
        return False
    finally:
        teste.unlink(missing_ok=True)


def _diagnostico_http(url, timeout):
    try:
        requisicao = urllib.request.Request(url, headers={"User-Agent": "DeigoVarejo-Healthcheck/1"})
        with urllib.request.urlopen(requisicao, timeout=timeout) as resposta:
            status = int(resposta.status)
        pronto = 200 <= status < 400
        erro_tipo = ""
    except (OSError, urllib.error.URLError, ValueError) as exc:
        status = 0
        pronto = False
        erro_tipo = exc.__class__.__name__
    return {
        "contrato": "local_http_health_v1",
        "pronto": pronto,
        "status_http": status,
        "erro_tipo": erro_tipo,
        "url_exposta": False,
    }


def _diretorio_backup():
    configurado = (os.getenv("LOCAL_BACKUP_DIR") or "").strip()
    if configurado:
        return Path(configurado), True
    program_data = (os.getenv("ProgramData") or "").strip()
    if program_data:
        return Path(program_data) / "DeigoVarejo" / "Backups", True
    return None, False


def _diagnostico_backup(*, idade_maxima_horas=None):
    politica = politica_periodicidade_backup(idade_maxima_horas=idade_maxima_horas)
    idade_maxima_horas = politica["idade_maxima_horas"]
    diretorio, configurado = _diretorio_backup()
    arquivos = []
    if diretorio and diretorio.is_dir():
        arquivos = [
            item
            for item in diretorio.glob("supermercado-local-*.zip*")
            if item.is_file() and not item.name.endswith(".sha256")
        ]
    ultimo = max(arquivos, key=lambda item: item.stat().st_mtime) if arquivos else None
    idade_horas = None
    if ultimo:
        idade_horas = round(max(0, time.time() - ultimo.stat().st_mtime) / 3600, 2)
    validacao = validar_pacote_backup(ultimo) if ultimo else {
        "contrato": "local_backup_package_validation_v1",
        "validado": False,
        "checksum_encontrado": False,
        "sha256_valido": False,
        "conteudo_validado": False,
        "backup_contrato": "",
        "estrutura_valida": False,
        "ancora_fiscal_valida": False,
        "criptografado": False,
        "banco_tipo": "",
        "codigo": "backup_ausente",
        "caminho_exposto": False,
        "segredo_exposto": False,
    }
    pronto = bool(
        politica["configurada"]
        and configurado
        and ultimo
        and idade_horas <= idade_maxima_horas
        and validacao["validado"]
    )
    alertas = []
    if not politica["configurada"]:
        alertas.append(
            "Configure LOCAL_BACKUP_MAX_AGE_HOURS com o prazo homologado antes do aceite."
        )
    if not configurado:
        alertas.append("Configure LOCAL_BACKUP_DIR ou o diretório ProgramData do serviço.")
    elif not ultimo:
        alertas.append("Execute e valide ao menos um backup local antes do aceite.")
    elif politica["configurada"] and idade_horas > idade_maxima_horas:
        alertas.append("O backup local mais recente excede a idade máxima permitida.")
    if ultimo and not validacao["validado"]:
        mensagens = {
            "checksum_ausente": "O backup mais recente não possui o arquivo de integridade SHA-256.",
            "checksum_invalido": "O arquivo de integridade do backup mais recente é inválido.",
            "checksum_arquivo_divergente": "O arquivo de integridade não corresponde ao pacote de backup.",
            "checksum_divergente": "O backup mais recente foi alterado ou está corrompido.",
            "senha_criptografia_indisponivel": "Configure a senha operacional para validar o conteúdo do backup criptografado.",
            "contrato_incompativel": "O backup mais recente usa um contrato incompatível.",
        }
        alertas.append(
            mensagens.get(
                validacao["codigo"],
                "O conteúdo do backup mais recente não passou na validação de segurança.",
            )
        )
    return {
        "contrato": "local_backup_health_v1",
        "pronto": pronto,
        "configurado": configurado,
        "backup_encontrado": bool(ultimo),
        "idade_horas": idade_horas,
        "idade_maxima_horas": idade_maxima_horas,
        "politica_contrato": politica["contrato"],
        "politica_configurada": politica["configurada"],
        "politica_origem": politica["origem"],
        "validacao": validacao,
        "alertas": alertas,
        "caminho_exposto": False,
    }


def diagnostico_pos_implantacao_local(
    *,
    url=None,
    timeout=5,
    idade_maxima_backup_horas=None,
    http_resultado=None,
):
    url = url or os.getenv("LOCAL_HEALTHCHECK_URL") or "http://127.0.0.1:8000/login/"
    http = http_resultado or _diagnostico_http(url, timeout)
    banco = diagnostico_prontidao_banco_dados(producao=True)
    diretorios = {
        "static": _diretorio_gravavel(settings.STATIC_ROOT),
        "media": _diretorio_gravavel(settings.MEDIA_ROOT),
        "logs": _diretorio_gravavel(settings.LOG_DIR),
    }
    backup = _diagnostico_backup(idade_maxima_horas=idade_maxima_backup_horas)
    verificacoes = [
        {"id": "http", "pronta": http["pronto"], "alertas": []},
        {"id": "banco", "pronta": banco["pronto"], "alertas": banco["alertas"]},
        {
            "id": "diretorios",
            "pronta": all(diretorios.values()),
            "alertas": [
                f"Diretório operacional sem escrita: {nome}."
                for nome, pronto in diretorios.items()
                if not pronto
            ],
        },
        {"id": "backup", "pronta": backup["pronto"], "alertas": backup["alertas"]},
    ]
    bloqueios = [
        f"{item['id']}: {alerta}"
        for item in verificacoes
        if not item["pronta"]
        for alerta in (item["alertas"] or ["Verificação pós-instalação pendente."])
    ]
    pronto = all(item["pronta"] for item in verificacoes)
    return {
        "contrato": "local_post_deployment_health_v1",
        "pronto": pronto,
        "status": "ready" if pronto else "blocked",
        "http": http,
        "banco": {
            "pronto": banco["pronto"],
            "postgresql": banco["postgresql"],
            "migracoes_pendentes": banco["migracoes_pendentes"],
        },
        "diretorios": diretorios,
        "backup": backup,
        "verificacoes": verificacoes,
        "bloqueios": bloqueios,
        "segredos_expostos": False,
    }
