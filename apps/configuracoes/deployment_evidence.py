import hashlib
import json
import re
import sys
from pathlib import Path

import django
from django.conf import settings
from django.utils import timezone

from .artifacts import artefato_pdv_desktop, artefato_servidor_local
from .offline_bundle import artefato_servidor_offline
from .readiness import diagnostico_prontidao_implantacao


def _resumo_artefato(resultado, *, tipo):
    resumo = {
        "tipo": tipo,
        "nome": resultado["nome"],
        "encontrado": resultado["arquivo_encontrado"],
        "tamanho_bytes": resultado["tamanho"],
        "sha256": resultado["sha256"],
        "integridade_valida": resultado["integridade_valida"],
        "versao_valida": resultado["versao_valida"],
        "publicavel": resultado["publicavel"],
        "problemas": resultado["problemas"],
    }
    if tipo == "pdv_desktop":
        resumo["assinatura_exigida"] = resultado["assinatura_exigida"]
        resumo["assinatura_valida"] = resultado["assinatura_valida"]
    elif tipo == "servidor_local":
        resumo["conteudo_valido"] = resultado["conteudo_valido"]
        resumo["origem_rastreavel"] = resultado["origem_rastreavel"]
    else:
        resumo["contrato_pacote"] = resultado.get("contrato", "")
        resumo["contrato_publicacao"] = resultado.get("contrato_publicacao", "")
        resumo["checksum_encontrado"] = bool(resultado.get("checksum_encontrado"))
        resumo["checksum_hash_valido"] = bool(resultado.get("checksum_hash_valido"))
        resumo["checksum_nome_vinculado"] = bool(resultado.get("checksum_nome_vinculado"))
        resumo["publicacao_valida"] = bool(resultado.get("publicacao_valida"))
    return resumo


def gerar_dossie_implantacao(*, perfil="central", producao=False, exigir_midia_offline=False):
    exigir_midia_offline = bool(perfil == "servidor-local" and exigir_midia_offline)
    prontidao = diagnostico_prontidao_implantacao(
        perfil=perfil,
        producao=producao,
        exigir_midia_offline=exigir_midia_offline,
    )
    artefatos = {
        "pdv_desktop": _resumo_artefato(artefato_pdv_desktop(), tipo="pdv_desktop"),
        "servidor_local": _resumo_artefato(
            artefato_servidor_local(), tipo="servidor_local"
        ),
    }
    if perfil == "servidor-local":
        artefatos["servidor_offline"] = _resumo_artefato(
            artefato_servidor_offline(), tipo="servidor_offline"
        )
    return {
        "contrato": "deployment_evidence_v1",
        "gerado_em": timezone.now().isoformat(),
        "perfil": perfil,
        "alvo": "producao" if producao else "homologacao",
        "politica_instalacao": {
            "contrato": "local_installation_media_policy_v1",
            "midia_offline_exigida": exigir_midia_offline,
        },
        "aplicacao": {
            "django": django.get_version(),
            "python": ".".join(map(str, sys.version_info[:3])),
            "pdv_desktop": settings.PDV_DESKTOP_VERSION,
            "servidor_local": settings.LOCAL_SERVER_VERSION,
        },
        "prontidao": prontidao,
        "artefatos": artefatos,
        "seguranca": {
            "segredos_expostos": False,
            "caminhos_absolutos_expostos": False,
        },
    }

def validar_dossie_implantacao(caminho):
    caminho = Path(caminho)
    erros = []
    avisos = []
    payload = {}
    try:
        conteudo = caminho.read_bytes()
    except OSError:
        conteudo = b""
        erros.append("Dossiê não encontrado ou ilegível.")
    if len(conteudo) > 5 * 1024 * 1024:
        erros.append("Dossiê excede o limite de 5 MB.")
    digest = hashlib.sha256(conteudo).hexdigest() if conteudo else ""

    hash_caminho = caminho.with_name(caminho.name + ".sha256")
    hash_valido = False
    try:
        linha_hash = hash_caminho.read_text(encoding="ascii").strip()
        correspondencia = re.fullmatch(r"([0-9a-fA-F]{64})  (.+)", linha_hash)
        hash_valido = bool(
            correspondencia
            and correspondencia.group(1).lower() == digest
            and correspondencia.group(2) == caminho.name
        )
    except (OSError, UnicodeError):
        pass
    if not hash_valido:
        erros.append("SHA-256 ausente, inválido ou divergente do dossiê.")

    if conteudo and len(conteudo) <= 5 * 1024 * 1024:
        try:
            payload = json.loads(conteudo.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            erros.append("JSON do dossiê é inválido.")
    if payload and payload.get("contrato") != "deployment_evidence_v1":
        erros.append("Contrato do dossiê é inválido.")
    perfil = payload.get("perfil") if isinstance(payload, dict) else None
    if perfil not in {"central", "servidor-local"}:
        erros.append("Perfil do dossiê é inválido.")
    prontidao = payload.get("prontidao", {}) if isinstance(payload, dict) else {}
    if prontidao.get("contrato") != "deployment_readiness_v2":
        erros.append("Contrato de prontidão do dossiê é inválido.")
    if not prontidao.get("pronto"):
        avisos.append("A prontidão da implantação está bloqueada.")

    artefatos = payload.get("artefatos", {}) if isinstance(payload, dict) else {}
    politica = payload.get("politica_instalacao", {}) if isinstance(payload, dict) else {}
    midia_offline_exigida = bool(politica.get("midia_offline_exigida"))
    if politica and politica.get("contrato") != "local_installation_media_policy_v1":
        erros.append("Contrato da política de mídia de instalação é inválido.")
    if midia_offline_exigida and perfil != "servidor-local":
        erros.append("Mídia offline só pode ser exigida no perfil servidor-local.")
    obrigatorios = ["servidor_local"] if perfil == "servidor-local" else []
    if midia_offline_exigida:
        obrigatorios.append("servidor_offline")
    for nome in obrigatorios:
        artefato = artefatos.get(nome, {})
        if not artefato.get("publicavel"):
            avisos.append(f"Artefato obrigatório não publicável: {nome}.")
        if artefato.get("publicavel") and not re.fullmatch(
            r"[0-9a-f]{64}", str(artefato.get("sha256") or "")
        ):
            erros.append(f"SHA-256 do artefato obrigatório é inválido: {nome}.")
    if midia_offline_exigida:
        offline = artefatos.get("servidor_offline", {})
        if offline.get("contrato_publicacao") != "detech_server_offline_publication_validation_v1":
            erros.append("Contrato da publicação offline obrigatória é inválido.")
        verificacoes = prontidao.get("verificacoes", [])
        verificacao_offline = next(
            (item for item in verificacoes if item.get("id") == "midia_instalacao_offline"),
            {},
        )
        if not (
            verificacao_offline.get("obrigatoria") is True
            and verificacao_offline.get("pronta") is True
        ):
            avisos.append("A prontidão da mídia offline obrigatória está bloqueada.")

    serializado = conteudo.decode("utf-8", errors="ignore")
    if re.search(r"(?i)(?:[a-z]:\\|/home/|/users/)", serializado):
        erros.append("O dossiê contém caminho absoluto de máquina.")
    estrutura_valida = bool(payload) and not erros
    liberavel = estrutura_valida and prontidao.get("pronto") is True and not avisos
    return {
        "contrato": "deployment_evidence_validation_v1",
        "valido": estrutura_valida,
        "liberavel": liberavel,
        "hash_valido": hash_valido,
        "perfil": perfil or "",
        "alvo": payload.get("alvo", "") if isinstance(payload, dict) else "",
        "midia_offline_exigida": midia_offline_exigida,
        "erros": list(dict.fromkeys(erros)),
        "avisos": list(dict.fromkeys(avisos)),
        "nao_expoe_conteudo": True,
    }
