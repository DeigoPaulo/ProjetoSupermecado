"""Resiliência em memória para o transporte SOAP da SEFAZ direta.

Não persiste payload, documento, CNPJ, chave de acesso, certificado ou mensagem de erro.
"""

from collections import deque
from datetime import datetime, timezone
from threading import RLock
from time import monotonic, sleep
from urllib.parse import urlparse

from ..adapters import SefazAdapterError


_SERVICOS_IDEMPOTENTES = frozenset({"consulta", "status", "cadastro"})
_ESTADO_LOCK = RLock()
_CIRCUITOS = {}
_EVENTOS = deque(maxlen=200)


class CircuitoSefazDiretaAberto(SefazAdapterError):
    """Bloqueia temporariamente novas chamadas após falhas consecutivas."""


def limpar_estado_resiliencia():
    """Uso restrito a testes e reinicializações controladas do processo."""
    with _ESTADO_LOCK:
        _CIRCUITOS.clear()
        _EVENTOS.clear()


def _host_seguro(endpoint):
    return (urlparse(endpoint).hostname or "host-invalido").lower()[:120]


def _registrar_evento(*, servico, host, resultado, tentativa, duracao_ms, erro=""):
    evento = {
        "em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "servico": str(servico or "")[:30],
        "host": str(host or "")[:120],
        "resultado": str(resultado or "")[:30],
        "tentativa": int(tentativa),
        "duracao_ms": max(0, int(duracao_ms)),
        "erro": str(erro or "")[:80],
    }
    with _ESTADO_LOCK:
        _EVENTOS.append(evento)


class ResilienciaSefazDireta:
    def __init__(
        self,
        *,
        max_tentativas=2,
        falhas_para_abrir=3,
        reabrir_apos_segundos=60,
        espera_base_ms=200,
        relogio=None,
        esperar=None,
    ):
        self.max_tentativas = max(1, min(int(max_tentativas), 5))
        self.falhas_para_abrir = max(1, min(int(falhas_para_abrir), 20))
        self.reabrir_apos_segundos = max(1, int(reabrir_apos_segundos))
        self.espera_base_ms = max(0, min(int(espera_base_ms), 5000))
        self.relogio = relogio or monotonic
        self.esperar = esperar or sleep

    def executar(self, *, servico, endpoint, operacao, erros_retornaveis):
        host = _host_seguro(endpoint)
        self._autorizar_tentativa(host=host, servico=servico)
        limite = self.max_tentativas if servico in _SERVICOS_IDEMPOTENTES else 1

        for tentativa in range(1, limite + 1):
            inicio = self.relogio()
            try:
                resultado = operacao()
            except erros_retornaveis as exc:
                duracao_ms = (self.relogio() - inicio) * 1000
                abriu = self._registrar_falha(host)
                _registrar_evento(
                    servico=servico,
                    host=host,
                    resultado="FALHA_REDE",
                    tentativa=tentativa,
                    duracao_ms=duracao_ms,
                    erro=exc.__class__.__name__,
                )
                if abriu or tentativa >= limite:
                    raise
                _registrar_evento(
                    servico=servico,
                    host=host,
                    resultado="NOVA_TENTATIVA",
                    tentativa=tentativa + 1,
                    duracao_ms=0,
                )
                self.esperar((self.espera_base_ms * (2 ** (tentativa - 1))) / 1000)
            except Exception as exc:
                self._registrar_sucesso(host)
                duracao_ms = (self.relogio() - inicio) * 1000
                _registrar_evento(
                    servico=servico,
                    host=host,
                    resultado="FALHA_NAO_RETENTAVEL",
                    tentativa=tentativa,
                    duracao_ms=duracao_ms,
                    erro=exc.__class__.__name__,
                )
                raise
            else:
                self._registrar_sucesso(host)
                duracao_ms = (self.relogio() - inicio) * 1000
                _registrar_evento(
                    servico=servico,
                    host=host,
                    resultado="SUCESSO",
                    tentativa=tentativa,
                    duracao_ms=duracao_ms,
                )
                return resultado

        raise RuntimeError("Fluxo de resiliência terminou sem resultado.")

    def _autorizar_tentativa(self, *, host, servico):
        agora = self.relogio()
        with _ESTADO_LOCK:
            estado = _CIRCUITOS.setdefault(
                host,
                {"falhas": 0, "aberto_ate": 0.0, "meia_abertura_em_teste": False},
            )
            if estado["aberto_ate"] > agora:
                bloqueado = True
            elif estado["aberto_ate"]:
                bloqueado = estado["meia_abertura_em_teste"]
                if not bloqueado:
                    estado["meia_abertura_em_teste"] = True
            else:
                bloqueado = False
        if bloqueado:
            _registrar_evento(
                servico=servico,
                host=host,
                resultado="CIRCUITO_ABERTO",
                tentativa=0,
                duracao_ms=0,
                erro="CircuitoSefazDiretaAberto",
            )
            raise CircuitoSefazDiretaAberto(
                "Comunicação direta temporariamente suspensa após falhas consecutivas."
            )

    def _registrar_falha(self, host):
        agora = self.relogio()
        with _ESTADO_LOCK:
            estado = _CIRCUITOS.setdefault(
                host,
                {"falhas": 0, "aberto_ate": 0.0, "meia_abertura_em_teste": False},
            )
            estado["falhas"] += 1
            estado["meia_abertura_em_teste"] = False
            if estado["falhas"] >= self.falhas_para_abrir:
                estado["aberto_ate"] = agora + self.reabrir_apos_segundos
                return True
            return False

    @staticmethod
    def _registrar_sucesso(host):
        with _ESTADO_LOCK:
            _CIRCUITOS[host] = {
                "falhas": 0,
                "aberto_ate": 0.0,
                "meia_abertura_em_teste": False,
            }

    def diagnosticar(self):
        agora = self.relogio()
        with _ESTADO_LOCK:
            eventos = list(_EVENTOS)
            circuitos_abertos = sum(
                1 for estado in _CIRCUITOS.values() if estado["aberto_ate"] > agora
            )
        contagem = {}
        for evento in eventos:
            resultado = evento["resultado"]
            contagem[resultado] = contagem.get(resultado, 0) + 1
        return {
            "contrato": "sefaz_direct_resilience_v1",
            "max_tentativas_consulta": self.max_tentativas,
            "tentativas_emissao_eventos": 1,
            "falhas_para_abrir_circuito": self.falhas_para_abrir,
            "reabertura_segundos": self.reabrir_apos_segundos,
            "circuitos_abertos": circuitos_abertos,
            "eventos_em_memoria": len(eventos),
            "contagem": contagem,
            "ultimo_evento": eventos[-1] if eventos else None,
        }