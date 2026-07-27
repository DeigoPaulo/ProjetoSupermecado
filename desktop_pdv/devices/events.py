from __future__ import annotations

import hashlib
import json
import threading
from functools import wraps
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


_LOG_LOCK = threading.RLock()


def _synchronized(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        with _LOG_LOCK:
            return func(*args, **kwargs)
    return wrapper


class EventLog:
    def __init__(self, caminho: Path):
        self.caminho = Path(caminho)

    @_synchronized
    def append(self, tipo: str, payload: dict) -> None:
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        evento = {
            "id": uuid4().hex,
            "em": datetime.now(timezone.utc).isoformat(),
            "tipo": str(tipo or "desconhecido"),
            "payload": dict(payload or {}),
        }
        with self.caminho.open("a", encoding="utf-8") as arquivo:
            arquivo.write(json.dumps(evento, ensure_ascii=True, sort_keys=True) + "\n")

    @_synchronized
    def linhas(self) -> list[str]:
        try:
            return self.caminho.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return []

    @staticmethod
    def decodificar(linha: str) -> dict:
        resumo = hashlib.sha256(linha.encode("utf-8", errors="replace")).hexdigest()[:24]
        try:
            evento = json.loads(linha)
        except json.JSONDecodeError:
            return {
                "id": f"corrompido-{resumo}",
                "tipo": "log_corrompido",
                "payload": {"linha": linha[:200]},
            }
        if not isinstance(evento, dict):
            return {
                "id": f"invalido-{resumo}",
                "tipo": "log_corrompido",
                "payload": {"linha": linha[:200]},
            }
        evento.setdefault("id", f"legado-{resumo}")
        return evento

    def listar(self, limite: int = 50) -> dict:
        linhas = self.linhas()
        quantidade = max(1, min(int(limite or 50), 200))
        return {
            "status": "ok",
            "eventos": [self.decodificar(linha) for linha in linhas[-quantidade:]],
            "total": len(linhas),
        }

    def pendentes(self, cursor: int, limite: int = 100) -> dict:
        linhas = self.linhas()
        total = len(linhas)
        cursor = max(0, int(cursor or 0))
        cursor_reiniciado = cursor > total
        if cursor_reiniciado:
            cursor = 0
        fim = min(total, cursor + max(1, min(int(limite or 100), 500)))
        return {
            "eventos": [self.decodificar(linha) for linha in linhas[cursor:fim]],
            "cursor": cursor,
            "proximo_cursor": fim,
            "total": total,
            "pendentes": max(total - cursor, 0),
            "cursor_reiniciado": cursor_reiniciado,
        }

    @_synchronized
    def compactar_confirmados(
        self,
        cursor: int,
        *,
        manter_confirmados: int = 200,
        minimo_confirmados: int = 500,
        max_bytes: int = 5 * 1024 * 1024,
        forcar: bool = False,
    ) -> dict:
        linhas = self.linhas()
        total = len(linhas)
        cursor = max(0, min(int(cursor or 0), total))
        try:
            tamanho = self.caminho.stat().st_size
        except FileNotFoundError:
            tamanho = 0
        if not forcar and cursor < minimo_confirmados and tamanho <= max_bytes:
            return {
                "compactado": False,
                "cursor": cursor,
                "total": total,
                "removidos": 0,
                "tamanho_bytes": tamanho,
            }

        manter = max(0, min(int(manter_confirmados or 0), cursor))
        remover = cursor - manter
        if remover <= 0:
            return {
                "compactado": False,
                "cursor": cursor,
                "total": total,
                "removidos": 0,
                "tamanho_bytes": tamanho,
            }

        restantes = linhas[remover:]
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        temporario = self.caminho.with_suffix(self.caminho.suffix + ".tmp")
        conteudo = "\n".join(restantes)
        temporario.write_text(conteudo + ("\n" if conteudo else ""), encoding="utf-8")
        temporario.replace(self.caminho)
        return {
            "compactado": True,
            "cursor": cursor - remover,
            "total": len(restantes),
            "removidos": remover,
            "tamanho_bytes": self.caminho.stat().st_size,
        }
