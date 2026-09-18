"""Geração de build e validação fail-closed da qualificação fiscal instalada."""

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings

from .politica_canais_fiscais import CANAL_PILOTO_GO, OPERACOES_FISCAIS_CANONICAS
from .qualificacao_canais_fiscais import construir_matriz_qualificacao_canais


CONTRATO_MANIFESTO_QUALIFICACAO = "fiscal_channel_qualification_manifest_v1"
CONTRATO_IDENTIDADE_INSTALACAO = "local_server_installation_identity_v1"
NOME_MANIFESTO = "fiscal_channel_qualification_manifest.json"
NOME_IDENTIDADE = "server_installation_identity.json"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
PROVAS_BUILD_TESTES = {
    "FOCUS": (
        "apps/fiscal/test_focus_sefaz_adapter.py",
        "apps/fiscal/test_focus_dfe_adapter.py",
    ),
    CANAL_PILOTO_GO: (
        "apps/fiscal/test_sefaz_direta_adapter.py",
        "apps/fiscal/test_carta_correcao.py",
        "apps/fiscal/test_manifestacao_destinatario.py",
        "apps/fiscal/test_sefaz_direta_dfe.py",
    ),
}


def _json_canonico(payload):
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _hash_payload(payload):
    base = {chave: valor for chave, valor in payload.items() if chave != "hash_integridade"}
    return hashlib.sha256(_json_canonico(base)).hexdigest()


def gerar_manifesto_qualificacao(*, raiz_projeto, versao, commit, hash_base_pacote, gerado_em=None):
    raiz_projeto = Path(raiz_projeto)
    matriz = construir_matriz_qualificacao_canais(raiz_projeto)
    if not COMMIT_RE.fullmatch(str(commit or "").lower()):
        raise ValueError("Commit de qualificação inválido.")
    if not SHA256_RE.fullmatch(str(hash_base_pacote or "").lower()):
        raise ValueError("Hash-base do pacote inválido.")
    if matriz["canais"][CANAL_PILOTO_GO]["compativeis_offline"] != len(OPERACOES_FISCAIS_CANONICAS):
        raise ValueError("SEFAZ direta GO não possui qualificação offline 7/7.")
    provas_ausentes = [
        arquivo for arquivos in PROVAS_BUILD_TESTES.values() for arquivo in arquivos
        if not (raiz_projeto / arquivo).is_file()
    ]
    if provas_ausentes:
        raise ValueError("Provas automatizadas do build ausentes: " + ", ".join(provas_ausentes))
    canais = {}
    for canal, resumo in matriz["canais"].items():
        itens = [item for item in matriz["resultados"] if item["canal"] == canal]
        canais[canal] = {
            "operacoes": {item["operacao"]: item["estado"] for item in itens},
            "compativeis_offline": resumo["compativeis_offline"],
            "lacunas_internas": resumo["lacunas_internas"],
            "provas_build": sorted(
                {arquivo for item in itens for arquivo, _ in item["evidencias"]}
                | set(PROVAS_BUILD_TESTES[canal])
            ),
        }
    payload = {
        "contrato": CONTRATO_MANIFESTO_QUALIFICACAO, "versao_contrato": 1,
        "versao_aplicacao": str(versao), "commit": str(commit).lower(),
        "gerado_em": gerado_em or datetime.now(timezone.utc).isoformat(),
        "canal_piloto": CANAL_PILOTO_GO,
        "operacoes_obrigatorias": list(OPERACOES_FISCAIS_CANONICAS),
        "canais": canais,
        "pacote": {"contrato": "local_server_package_v1", "hash_base_sha256": str(hash_base_pacote).lower()},
        "matriz_build": matriz["contrato"], "rede_acessada": False,
        "credenciais_lidas": False, "homologacao_real_executada": False,
        "producao_liberada": False,
    }
    payload["hash_integridade"] = _hash_payload(payload)
    return payload


def gerar_identidade_instalacao(*, versao, commit):
    payload = {"contrato": CONTRATO_IDENTIDADE_INSTALACAO, "versao_aplicacao": str(versao), "commit": str(commit).lower()}
    payload["hash_integridade"] = _hash_payload(payload)
    return payload


def validar_qualificacao_instalada_payload(manifesto, identidade, *, canal, operacoes=None):
    problemas = []
    operacoes = tuple(operacoes or OPERACOES_FISCAIS_CANONICAS)
    if not isinstance(manifesto, dict) or manifesto.get("contrato") != CONTRATO_MANIFESTO_QUALIFICACAO:
        problemas.append("Manifesto de qualificação fiscal ausente ou com contrato desconhecido.")
        manifesto = manifesto if isinstance(manifesto, dict) else {}
    if not isinstance(identidade, dict) or identidade.get("contrato") != CONTRATO_IDENTIDADE_INSTALACAO:
        problemas.append("Identidade da versão instalada ausente ou desconhecida.")
        identidade = identidade if isinstance(identidade, dict) else {}
    for nome, payload in (("manifesto", manifesto), ("identidade", identidade)):
        hash_declarado = str(payload.get("hash_integridade") or "").lower()
        if not SHA256_RE.fullmatch(hash_declarado) or hash_declarado != _hash_payload(payload):
            problemas.append(f"Integridade do {nome} não confirmada.")
    if manifesto.get("versao_aplicacao") != identidade.get("versao_aplicacao"):
        problemas.append("Versão qualificada diverge da versão instalada.")
    if manifesto.get("commit") != identidade.get("commit"):
        problemas.append("Commit qualificado diverge do commit instalado.")
    pacote = manifesto.get("pacote") or {}
    if (
        pacote.get("contrato") != "local_server_package_v1"
        or not SHA256_RE.fullmatch(str(pacote.get("hash_base_sha256") or "").lower())
    ):
        problemas.append("Vínculo da qualificação com o pacote é inválido.")
    if tuple(manifesto.get("operacoes_obrigatorias") or ()) != OPERACOES_FISCAIS_CANONICAS:
        problemas.append("Conjunto canônico de operações fiscais divergente.")
    canal_info = (manifesto.get("canais") or {}).get(str(canal or ""))
    if not isinstance(canal_info, dict):
        problemas.append("Canal fiscal não qualificado para esta versão.")
        canal_info = {}
    estados = canal_info.get("operacoes") or {}
    for operacao in operacoes:
        if operacao not in OPERACOES_FISCAIS_CANONICAS:
            problemas.append(f"Operação fiscal desconhecida: {operacao}.")
        elif estados.get(operacao) != "COMPATIVEL_OFFLINE":
            problemas.append(f"Operação {operacao} não qualificada no canal {canal}.")
    return {
        "contrato": "fiscal_installed_qualification_validation_v1", "valido": not problemas,
        "canal": str(canal or ""), "operacoes": operacoes,
        "problemas": tuple(dict.fromkeys(problemas)),
        "homologacao_real_executada": False, "producao_liberada": False,
    }


def diagnosticar_qualificacao_instalada(*, canal, operacoes=None, caminho_manifesto=None, caminho_identidade=None):
    caminho_manifesto = Path(caminho_manifesto or settings.FISCAL_QUALIFICATION_MANIFEST_PATH)
    caminho_identidade = Path(caminho_identidade or settings.FISCAL_INSTALLATION_IDENTITY_PATH)
    try:
        manifesto = json.loads(caminho_manifesto.read_text(encoding="utf-8-sig"))
        identidade = json.loads(caminho_identidade.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        manifesto, identidade = {}, {}
    return validar_qualificacao_instalada_payload(manifesto, identidade, canal=canal, operacoes=operacoes)
