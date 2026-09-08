import hashlib
import hmac
import json
import re
import zipfile
from datetime import datetime, timezone
from io import BytesIO

from .verificador_artefatos_piloto import (
    CONTRATO_VERIFICACAO_ARTEFATOS_PILOTO,
    calcular_sha256_artefato,
    verificar_integridade_artefatos_piloto,
)


CONTRATO_DOSSIE_PILOTO = "inventory_pilot_dossier_v1"
_ARQUIVOS_DOSSIE = (
    ("ficha.json", "ficha"),
    ("relatorio.json", "relatorio"),
    ("verificacao_integridade.json", "verificacao"),
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _json_bytes(documento):
    return json.dumps(
        documento, ensure_ascii=False, sort_keys=True, indent=2
    ).encode("utf-8")


def _sha256_bytes(conteudo):
    return hashlib.sha256(conteudo).hexdigest()


def _valor_aninhado(documento, *chaves):
    atual = documento
    for chave in chaves:
        if not isinstance(atual, dict):
            return None
        atual = atual.get(chave)
    return atual


def _verificacao_corresponde(*, ficha, relatorio, verificacao, atual):
    if not isinstance(verificacao, dict):
        return False
    hash_informado = verificacao.get("conteudo_sha256")
    if (
        not isinstance(hash_informado, str)
        or not _SHA256_RE.fullmatch(hash_informado)
        or not hmac.compare_digest(
            hash_informado, calcular_sha256_artefato(verificacao)
        )
    ):
        return False
    protecoes = (
        verificacao.get("contrato") == CONTRATO_VERIFICACAO_ARTEFATOS_PILOTO,
        verificacao.get("integridade_confirmada") is True,
        verificacao.get("impedimentos") == [],
        verificacao.get("registra_aceite") is False,
        verificacao.get("persiste_resultado") is False,
        verificacao.get("consulta_banco") is False,
        verificacao.get("somente_leitura") is True,
        verificacao.get("comunicacao_externa") is False,
        _valor_aninhado(verificacao, "artefatos", "ficha", "sha256_informado")
        == ficha.get("conteudo_sha256"),
        _valor_aninhado(
            verificacao, "artefatos", "relatorio", "sha256_informado"
        )
        == relatorio.get("conteudo_sha256"),
        verificacao.get("vinculo") == atual.get("vinculo"),
        verificacao.get("verificacoes") == atual.get("verificacoes"),
    )
    return all(protecoes)


def gerar_dossie_piloto(*, ficha, relatorio, verificacao, momento=None):
    """Gera um ZIP em memória após reconferir os três artefatos do piloto."""
    if not all(isinstance(item, dict) for item in (ficha, relatorio, verificacao)):
        raise ValueError("Os três artefatos devem ser objetos JSON.")
    momento = momento or datetime.now(timezone.utc)
    atual = verificar_integridade_artefatos_piloto(
        ficha=ficha, relatorio=relatorio, momento=momento
    )
    if not atual["integridade_confirmada"] or not _verificacao_corresponde(
        ficha=ficha,
        relatorio=relatorio,
        verificacao=verificacao,
        atual=atual,
    ):
        raise ValueError("Os artefatos não formam um conjunto íntegro e coerente.")

    documentos = {
        "ficha": ficha,
        "relatorio": relatorio,
        "verificacao": verificacao,
    }
    conteudos = {
        chave: _json_bytes(documentos[chave]) for _, chave in _ARQUIVOS_DOSSIE
    }
    manifesto = {
        "contrato": CONTRATO_DOSSIE_PILOTO,
        "gerado_em": momento.isoformat(),
        "filial_id": atual["vinculo"]["filial_id"],
        "produto_id": atual["vinculo"]["produto_id"],
        "objetos": atual["vinculo"]["objetos"],
        "arquivos": [
            {
                "nome": nome,
                "bytes": len(conteudos[chave]),
                "sha256_arquivo": _sha256_bytes(conteudos[chave]),
                "sha256_artefato": documentos[chave].get("conteudo_sha256"),
            }
            for nome, chave in _ARQUIVOS_DOSSIE
        ],
        "integridade_confirmada": True,
        "registra_aceite": False,
        "persiste_dossie": False,
        "consulta_banco": False,
        "somente_leitura": True,
        "comunicacao_externa": False,
        "assinatura_digital": False,
    }
    manifesto["conteudo_sha256"] = calcular_sha256_artefato(manifesto)

    saida = BytesIO()
    with zipfile.ZipFile(saida, "w", compression=zipfile.ZIP_DEFLATED) as pacote:
        for nome, chave in _ARQUIVOS_DOSSIE:
            pacote.writestr(nome, conteudos[chave])
        pacote.writestr("manifesto.json", _json_bytes(manifesto))
    return saida.getvalue(), manifesto
