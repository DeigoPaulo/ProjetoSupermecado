import hashlib
import json
import re
import sys
from pathlib import Path

import django
from django.conf import settings
from django.utils import timezone

from .artifacts import artefato_pdv_desktop, artefato_servidor_local
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
    else:
        resumo["conteudo_valido"] = resultado["conteudo_valido"]
        resumo["origem_rastreavel"] = resultado["origem_rastreavel"]
    return resumo


def gerar_dossie_implantacao(*, perfil="central", producao=False):
    prontidao = diagnostico_prontidao_implantacao(perfil=perfil, producao=producao)
    return {
        "contrato": "deployment_evidence_v1",
        "gerado_em": timezone.now().isoformat(),
        "perfil": perfil,
        "alvo": "producao" if producao else "homologacao",
        "aplicacao": {
            "django": django.get_version(),
            "python": ".".join(map(str, sys.version_info[:3])),
            "pdv_desktop": settings.PDV_DESKTOP_VERSION,
            "servidor_local": settings.LOCAL_SERVER_VERSION,
        },
        "prontidao": prontidao,
        "artefatos": {
            "pdv_desktop": _resumo_artefato(artefato_pdv_desktop(), tipo="pdv_desktop"),
            "servidor_local": _resumo_artefato(
                artefato_servidor_local(), tipo="servidor_local"
            ),
        },
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
    obrigatorios = ["servidor_local"] if perfil == "servidor-local" else []
    for nome in obrigatorios:
        artefato = artefatos.get(nome, {})
        if not artefato.get("publicavel"):
            avisos.append(f"Artefato obrigatório não publicável: {nome}.")
        if artefato.get("publicavel") and not re.fullmatch(
            r"[0-9a-f]{64}", str(artefato.get("sha256") or "")
        ):
            erros.append(f"SHA-256 do artefato obrigatório é inválido: {nome}.")

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
        "erros": list(dict.fromkeys(erros)),
        "avisos": list(dict.fromkeys(avisos)),
        "nao_expoe_conteudo": True,
    }
