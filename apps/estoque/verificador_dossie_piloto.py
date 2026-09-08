import hashlib
import hmac
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from .dossie_piloto import CONTRATO_DOSSIE_PILOTO, gerar_dossie_piloto
from .verificador_artefatos_piloto import (
    LIMITE_ARQUIVO_JSON,
    calcular_sha256_artefato,
)


CONTRATO_VERIFICACAO_DOSSIE_PILOTO = "inventory_pilot_dossier_integrity_v1"
LIMITE_MANIFESTO_JSON = 256 * 1024
LIMITE_DOSSIE_ZIP = (
    (3 * LIMITE_ARQUIVO_JSON) + LIMITE_MANIFESTO_JSON + (1024 * 1024)
)
_NOMES_ESPERADOS = {
    "ficha.json",
    "relatorio.json",
    "verificacao_integridade.json",
    "manifesto.json",
}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MENSAGENS = {
    "estrutura_exata": "O ZIP não contém exatamente os quatro arquivos esperados.",
    "entradas_sem_criptografia": "O ZIP contém entrada criptografada.",
    "compressao_suportada": "O ZIP usa método de compressão não suportado.",
    "tamanhos_seguros": "Uma entrada ou a soma descompactada excede o limite.",
    "crc_integro": "Uma entrada do ZIP falhou na conferência CRC.",
    "jsons_validos": "Uma entrada não contém objeto JSON UTF-8 válido.",
    "manifesto_contrato": "O manifesto não usa o contrato de dossiê suportado.",
    "manifesto_sha256_integro": "O SHA-256 próprio do manifesto é inválido.",
    "gerado_em_valido": "O horário de geração do manifesto é inválido.",
    "conjunto_coerente": "Ficha, relatório e conferência não formam um conjunto íntegro.",
    "manifesto_corresponde_conteudo": "O manifesto não corresponde aos bytes e vínculos do pacote.",
}


def _instante_manifesto(valor):
    if not isinstance(valor, str):
        return None
    try:
        instante = datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except ValueError:
        return None
    if instante.tzinfo is None:
        return None
    return instante.astimezone(timezone.utc)


def _manifesto_sha_integro(manifesto):
    informado = manifesto.get("conteudo_sha256")
    return (
        isinstance(informado, str)
        and bool(_SHA256_RE.fullmatch(informado))
        and hmac.compare_digest(informado, calcular_sha256_artefato(manifesto))
    )


def _resultado(*, tamanho, sha256, verificacoes, manifesto, momento):
    impedimentos = [
        {"codigo": chave.upper(), "mensagem": _MENSAGENS[chave]}
        for chave, passou in verificacoes.items()
        if not passou
    ]
    integro = all(verificacoes.values())
    payload = {
        "contrato": CONTRATO_VERIFICACAO_DOSSIE_PILOTO,
        "verificado_em": momento.isoformat(),
        "dossie": {"bytes": tamanho, "sha256_arquivo": sha256},
        "vinculo": {
            "filial_id": manifesto.get("filial_id") if integro else None,
            "produto_id": manifesto.get("produto_id") if integro else None,
            "objetos": manifesto.get("objetos") if integro else None,
        },
        "verificacoes": verificacoes,
        "impedimentos": impedimentos,
        "integridade_confirmada": integro,
        "extrai_arquivos": False,
        "persiste_resultado": False,
        "consulta_banco": False,
        "somente_leitura": True,
        "comunicacao_externa": False,
        "caminho_incluido_resultado": False,
    }
    payload["conteudo_sha256"] = calcular_sha256_artefato(payload)
    return payload


def verificar_dossie_piloto(caminho, *, momento=None):
    """Confere um dossiê local sem extrair entradas, consultar banco ou acessar rede."""
    momento = momento or datetime.now(timezone.utc)
    original = Path(caminho).expanduser()
    if original.is_symlink():
        raise ValueError("Links simbólicos não são aceitos para o dossiê.")
    resolvido = original.resolve(strict=True)
    if str(resolvido).startswith("\\\\"):
        raise ValueError("O dossiê deve estar em armazenamento local.")
    if not resolvido.is_file():
        raise ValueError("O caminho informado não é um arquivo.")
    tamanho = resolvido.stat().st_size
    if tamanho <= 0 or tamanho > LIMITE_DOSSIE_ZIP:
        raise ValueError("O dossiê está vazio ou excede o limite permitido.")
    sha256 = hashlib.sha256(resolvido.read_bytes()).hexdigest()
    verificacoes = {chave: False for chave in _MENSAGENS}
    manifesto = {}

    try:
        with zipfile.ZipFile(resolvido) as pacote:
            infos = pacote.infolist()
            nomes = [info.filename for info in infos]
            verificacoes["estrutura_exata"] = (
                len(nomes) == len(_NOMES_ESPERADOS)
                and set(nomes) == _NOMES_ESPERADOS
            )
            verificacoes["entradas_sem_criptografia"] = all(
                not info.flag_bits & 0x1 for info in infos
            )
            verificacoes["compressao_suportada"] = all(
                info.compress_type in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
                for info in infos
            )
            limites = {
                "ficha.json": LIMITE_ARQUIVO_JSON,
                "relatorio.json": LIMITE_ARQUIVO_JSON,
                "verificacao_integridade.json": LIMITE_ARQUIVO_JSON,
                "manifesto.json": LIMITE_MANIFESTO_JSON,
            }
            verificacoes["tamanhos_seguros"] = (
                verificacoes["estrutura_exata"]
                and all(0 < info.file_size <= limites[info.filename] for info in infos)
                and sum(info.file_size for info in infos)
                <= (3 * LIMITE_ARQUIVO_JSON) + LIMITE_MANIFESTO_JSON
            )
            base_segura = all(
                verificacoes[chave]
                for chave in (
                    "estrutura_exata",
                    "entradas_sem_criptografia",
                    "compressao_suportada",
                    "tamanhos_seguros",
                )
            )
            if base_segura:
                verificacoes["crc_integro"] = pacote.testzip() is None
            if base_segura and verificacoes["crc_integro"]:
                documentos = {}
                try:
                    for nome in _NOMES_ESPERADOS:
                        documento = json.loads(pacote.read(nome).decode("utf-8"))
                        if not isinstance(documento, dict):
                            raise ValueError
                        documentos[nome] = documento
                except (
                    KeyError,
                    RecursionError,
                    UnicodeError,
                    json.JSONDecodeError,
                    ValueError,
                ):
                    documentos = {}
                verificacoes["jsons_validos"] = len(documentos) == 4
                if documentos:
                    manifesto = documentos["manifesto.json"]
                    verificacoes["manifesto_contrato"] = (
                        manifesto.get("contrato") == CONTRATO_DOSSIE_PILOTO
                    )
                    verificacoes["manifesto_sha256_integro"] = (
                        _manifesto_sha_integro(manifesto)
                    )
                    instante = _instante_manifesto(manifesto.get("gerado_em"))
                    verificacoes["gerado_em_valido"] = instante is not None
                    if instante is not None:
                        try:
                            _, esperado = gerar_dossie_piloto(
                                ficha=documentos["ficha.json"],
                                relatorio=documentos["relatorio.json"],
                                verificacao=documentos[
                                    "verificacao_integridade.json"
                                ],
                                momento=instante,
                            )
                        except (TypeError, ValueError):
                            esperado = None
                        verificacoes["conjunto_coerente"] = esperado is not None
                        verificacoes["manifesto_corresponde_conteudo"] = (
                            esperado is not None and manifesto == esperado
                        )
    except (
        OSError,
        RecursionError,
        RuntimeError,
        zipfile.BadZipFile,
        zipfile.LargeZipFile,
    ):
        pass
    return _resultado(
        tamanho=tamanho,
        sha256=sha256,
        verificacoes=verificacoes,
        manifesto=manifesto,
        momento=momento,
    )
