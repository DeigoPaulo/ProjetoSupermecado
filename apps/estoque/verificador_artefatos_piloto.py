import hashlib
import hmac
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .evidencia_piloto import CONTRATO_EVIDENCIA_PILOTO
from .ficha_execucao_piloto import CONTRATO_FICHA_EXECUCAO_PILOTO


CONTRATO_VERIFICACAO_ARTEFATOS_PILOTO = "inventory_pilot_artifact_integrity_v1"
LIMITE_ARQUIVO_JSON = 5 * 1024 * 1024
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CAMPOS_OBJETOS = {
    "entrada_id",
    "venda_id",
    "perda_id",
    "inventario_id",
    "fechamento_id",
}


def calcular_sha256_artefato(documento):
    conteudo = dict(documento)
    conteudo.pop("conteudo_sha256", None)
    return hashlib.sha256(
        json.dumps(
            conteudo, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def _hash_informado(documento):
    valor = documento.get("conteudo_sha256")
    return valor if isinstance(valor, str) and _SHA256_RE.fullmatch(valor) else None


def _hash_integro(documento):
    informado = _hash_informado(documento)
    return bool(informado) and hmac.compare_digest(
        informado, calcular_sha256_artefato(documento)
    )


def _instante_iso(valor):
    if not isinstance(valor, str):
        return None
    try:
        instante = datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except ValueError:
        return None
    if instante.tzinfo is None:
        return None
    return instante.astimezone(timezone.utc)


def _objetos_validos(objetos):
    return (
        isinstance(objetos, dict)
        and set(objetos) == _CAMPOS_OBJETOS
        and all(type(valor) is int and valor > 0 for valor in objetos.values())
    )


def carregar_artefato_json(caminho, *, limite_bytes=LIMITE_ARQUIVO_JSON):
    """Lê um JSON local e limitado, sem consultar banco ou serviço externo."""
    original = Path(caminho).expanduser()
    if original.is_symlink():
        raise ValueError("Links simbólicos não são aceitos para artefatos do piloto.")
    resolvido = original.resolve(strict=True)
    if str(resolvido).startswith("\\\\"):
        raise ValueError("O artefato deve estar em armazenamento local.")
    if not resolvido.is_file():
        raise ValueError("O caminho informado não é um arquivo.")
    tamanho = resolvido.stat().st_size
    if tamanho <= 0 or tamanho > limite_bytes:
        raise ValueError("O arquivo JSON está vazio ou excede o limite permitido.")
    with resolvido.open("r", encoding="utf-8-sig") as arquivo:
        documento = json.load(arquivo)
    if not isinstance(documento, dict):
        raise ValueError("A raiz do artefato deve ser um objeto JSON.")
    return documento


def verificar_integridade_artefatos_piloto(*, ficha, relatorio, momento=None):
    """Confere dois documentos em memória sem banco, rede, aceite ou persistência."""
    if not isinstance(ficha, dict) or not isinstance(relatorio, dict):
        raise ValueError("Ficha e relatório devem ser objetos JSON.")
    momento = momento or datetime.now(timezone.utc)
    objetos_ficha = ficha.get("objetos_selecionados_manualmente")
    objetos_relatorio = relatorio.get("objetos")
    ficha_em = _instante_iso(ficha.get("gerado_em"))
    relatorio_em = _instante_iso(relatorio.get("gerado_em"))
    responsaveis = ficha.get("responsaveis")

    verificacoes = {
        "contrato_ficha_suportado": (
            ficha.get("contrato") == CONTRATO_FICHA_EXECUCAO_PILOTO
        ),
        "contrato_relatorio_suportado": (
            relatorio.get("contrato") == CONTRATO_EVIDENCIA_PILOTO
        ),
        "sha256_ficha_integro": _hash_integro(ficha),
        "sha256_relatorio_integro": _hash_integro(relatorio),
        "ids_ficha_validos": _objetos_validos(objetos_ficha),
        "ids_relatorio_validos": _objetos_validos(objetos_relatorio),
        "mesmos_objetos": (
            _objetos_validos(objetos_ficha)
            and _objetos_validos(objetos_relatorio)
            and objetos_ficha == objetos_relatorio
        ),
        "mesma_filial": (
            type(ficha.get("filial_id")) is int
            and ficha.get("filial_id") > 0
            and ficha.get("filial_id") == relatorio.get("filial_id")
        ),
        "mesmo_produto": (
            type(ficha.get("produto_id")) is int
            and ficha.get("produto_id") > 0
            and ficha.get("produto_id") == relatorio.get("produto_id")
        ),
        "relatorio_nao_anterior_a_ficha": bool(
            ficha_em and relatorio_em and relatorio_em >= ficha_em
        ),
        "ficha_apta": ficha.get("apta_para_verificacao_final") is True,
        "relatorio_valido": relatorio.get("valida") is True,
        "responsaveis_nao_persistidos": (
            isinstance(responsaveis, dict)
            and responsaveis.get("persistidos_no_banco") is False
        ),
        "ficha_nao_registra_aceite": (
            ficha.get("aprovacao_automatica") is False
            and ficha.get("registra_aceite") is False
            and ficha.get("persiste_ficha") is False
        ),
        "artefatos_somente_leitura": (
            ficha.get("somente_leitura") is True
            and relatorio.get("somente_leitura") is True
        ),
        "artefatos_sem_comunicacao_externa": (
            ficha.get("comunicacao_externa") is False
            and relatorio.get("comunicacao_externa") is False
        ),
    }
    mensagens = {
        "contrato_ficha_suportado": "A ficha não usa o contrato v2 suportado.",
        "contrato_relatorio_suportado": "O relatório não usa o contrato v3 suportado.",
        "sha256_ficha_integro": "O conteúdo da ficha não confere com seu SHA-256.",
        "sha256_relatorio_integro": "O conteúdo do relatório não confere com seu SHA-256.",
        "ids_ficha_validos": "A ficha não contém exatamente os cinco IDs positivos esperados.",
        "ids_relatorio_validos": "O relatório não contém exatamente os cinco IDs positivos esperados.",
        "mesmos_objetos": "Ficha e relatório não se referem aos mesmos cinco registros.",
        "mesma_filial": "Ficha e relatório não identificam a mesma filial válida.",
        "mesmo_produto": "Ficha e relatório não identificam o mesmo produto válido.",
        "relatorio_nao_anterior_a_ficha": "Os horários são inválidos ou o relatório é anterior à ficha.",
        "ficha_apta": "A ficha não estava apta para a verificação final.",
        "relatorio_valido": "O relatório final não foi validado integralmente.",
        "responsaveis_nao_persistidos": "A ficha não declara a ausência de persistência dos responsáveis.",
        "ficha_nao_registra_aceite": "A ficha não declara todas as proteções contra aceite automático.",
        "artefatos_somente_leitura": "Os dois artefatos devem declarar operação somente leitura.",
        "artefatos_sem_comunicacao_externa": "Os dois artefatos devem declarar ausência de comunicação externa.",
    }
    impedimentos = [
        {"codigo": chave.upper(), "mensagem": mensagens[chave]}
        for chave, passou in verificacoes.items()
        if not passou
    ]
    vinculo_confirmado = all(
        verificacoes[chave]
        for chave in (
            "mesmos_objetos",
            "mesma_filial",
            "mesmo_produto",
            "relatorio_nao_anterior_a_ficha",
        )
    )
    payload = {
        "contrato": CONTRATO_VERIFICACAO_ARTEFATOS_PILOTO,
        "verificado_em": momento.isoformat(),
        "artefatos": {
            "ficha": {
                "contrato": ficha.get("contrato"),
                "sha256_informado": _hash_informado(ficha),
            },
            "relatorio": {
                "contrato": relatorio.get("contrato"),
                "sha256_informado": _hash_informado(relatorio),
            },
        },
        "vinculo": {
            "confirmado": vinculo_confirmado,
            "filial_id": ficha.get("filial_id") if verificacoes["mesma_filial"] else None,
            "produto_id": ficha.get("produto_id") if verificacoes["mesmo_produto"] else None,
            "objetos": objetos_ficha if verificacoes["mesmos_objetos"] else None,
        },
        "verificacoes": verificacoes,
        "impedimentos": impedimentos,
        "integridade_confirmada": all(verificacoes.values()),
        "registra_aceite": False,
        "persiste_resultado": False,
        "consulta_banco": False,
        "somente_leitura": True,
        "comunicacao_externa": False,
    }
    payload["conteudo_sha256"] = calcular_sha256_artefato(payload)
    return payload
